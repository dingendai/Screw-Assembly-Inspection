import cv2

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import VideoSource, apply_frame_transform, normalised_region_to_pixels
from valve_gui.config_store import save_app_config
from valve_gui.model_registry import camera_model_names, enabled_model_names, ensure_model_configs, set_camera_model_names
from valve_gui.models import AppState, ModelConfig
from valve_gui.paths import APP_DIR
from valve_gui.permissions import (
    PERMISSION_MANAGE_MODELS,
    PERMISSION_OPEN_SETTINGS,
    has_permission,
)
from valve_gui.utils import (
    DECISION_OPERATORS,
    decision_rule_key as _rule_key,
    hex_to_bgr,
    normalise_decision_operator,
)
from valve_gui.widgets import CameraView


MODEL_MODALITIES = [
    ("vision", "視覺"),
    ("text", "文字"),
    ("multimodal", "多模態"),
    ("ocr", "文字辨識"),
    ("classifier", "分類器"),
]


def model_modality_label(value):
    labels = dict(MODEL_MODALITIES)
    return labels.get(value, value)


ROTATION_OPTIONS = ["0", "90", "180", "270"]
DISPLAY_MODE_OPTIONS = [
    ("auto", "自動適應目前螢幕"),
    ("custom", "指定 GUI 畫面大小"),
    ("fullscreen", "全螢幕"),
]
FONT_SIZE_OPTIONS = [10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 24, 26, 28]


class SettingsPage(QWidget):
    def __init__(self, state: AppState, on_apply, before_camera_scan=None, on_display_change=None, on_logout=None):
        super().__init__()
        self.state = state
        self.on_apply = on_apply
        self.before_camera_scan = before_camera_scan
        self.on_display_change = on_display_change
        self.on_logout = on_logout
        self.rows = []
        self.preview_sources = []
        self.preview_cameras = {}
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_camera_previews)
        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.setInterval(400)
        self._preview_debounce.timeout.connect(self.restart_preview)
        self._camera_autosave_timer = QTimer(self)
        self._camera_autosave_timer.setSingleShot(True)
        self._camera_autosave_timer.setInterval(0)
        self._camera_autosave_timer.timeout.connect(self.persist_camera_settings)
        self._loading_camera_controls = False

        ensure_model_configs(self.state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        content = QHBoxLayout()
        content.setSpacing(12)
        content.addWidget(self.build_camera_group(), 1)
        content.addWidget(self.build_preview_group(), 1)
        content.setStretch(0, 1)
        content.setStretch(1, 1)

        layout.addLayout(content, 1)

    def build_camera_group(self):
        group = QGroupBox("相機、方向與焦距設定")
        group.setObjectName("cameraSettingsGroup")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        self.camera_tabs = QTabWidget()
        self.camera_tabs.currentChanged.connect(lambda _index: self.update_camera_previews())

        for config in self.state.inspection_cameras:
            enabled = QCheckBox("啟用相機")
            enabled.setChecked(config.enabled)

            index = QComboBox()
            self.populate_camera_index_combo(index, config.device_index)

            flip_h = QCheckBox("左右翻轉")
            flip_h.setChecked(config.flip_horizontal)
            flip_v = QCheckBox("上下翻轉")
            flip_v.setChecked(config.flip_vertical)

            rotation = QComboBox()
            rotation.addItems(ROTATION_OPTIONS)
            rotation.setCurrentText(str(config.rotation_degrees))

            barcode_enabled = QCheckBox("啟動")
            barcode_disabled = QCheckBox("停用")
            barcode_enabled.setChecked(config.barcode_read_enabled)
            barcode_disabled.setChecked(not config.barcode_read_enabled)

            auto_focus = QCheckBox("自動焦距")
            manual_focus_mode = QCheckBox("手動焦距")
            is_manual_focus = getattr(config, "focus_mode", "auto") == "manual"
            auto_focus.setChecked(not is_manual_focus)
            manual_focus_mode.setChecked(is_manual_focus)

            manual_focus = QSlider(Qt.Orientation.Horizontal)
            manual_focus.setRange(0, 1023)
            manual_focus.setSingleStep(1)
            manual_focus.setPageStep(10)
            manual_focus.setValue(int(getattr(config, "manual_focus_value", 120)))
            manual_focus_value = QLabel(str(manual_focus.value()))
            manual_focus_value.setMinimumWidth(36)
            manual_focus_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            focus_value_row = QHBoxLayout()
            focus_value_row.addWidget(manual_focus, 1)
            focus_value_row.addWidget(manual_focus_value)

            def update_focus_controls(_value=None, mode_check=manual_focus_mode, slider=manual_focus, value_label=manual_focus_value):
                enabled_manual = mode_check.isChecked()
                slider.setEnabled(enabled_manual)
                value_label.setEnabled(enabled_manual)
                value_label.setText(str(slider.value()))

            def set_auto_focus(
                checked,
                auto_check=auto_focus,
                manual_check=manual_focus_mode,
                focus_updater=update_focus_controls,
                slot=config.slot,
            ):
                if checked:
                    manual_check.blockSignals(True)
                    manual_check.setChecked(False)
                    manual_check.blockSignals(False)
                elif not manual_check.isChecked():
                    auto_check.blockSignals(True)
                    auto_check.setChecked(True)
                    auto_check.blockSignals(False)
                focus_updater()
                self._apply_focus_change_immediately(slot)

            def set_manual_focus(
                checked,
                auto_check=auto_focus,
                manual_check=manual_focus_mode,
                focus_updater=update_focus_controls,
                slot=config.slot,
            ):
                if checked:
                    auto_check.blockSignals(True)
                    auto_check.setChecked(False)
                    auto_check.blockSignals(False)
                elif not auto_check.isChecked():
                    manual_check.blockSignals(True)
                    manual_check.setChecked(True)
                    manual_check.blockSignals(False)
                focus_updater()
                self._apply_focus_change_immediately(slot)

            def set_barcode_enabled(checked, enable_check=barcode_enabled, disable_check=barcode_disabled):
                if checked:
                    disable_check.blockSignals(True)
                    disable_check.setChecked(False)
                    disable_check.blockSignals(False)
                elif not disable_check.isChecked():
                    enable_check.blockSignals(True)
                    enable_check.setChecked(True)
                    enable_check.blockSignals(False)
                self._queue_preview_restart()

            def set_barcode_disabled(checked, enable_check=barcode_enabled, disable_check=barcode_disabled):
                if checked:
                    enable_check.blockSignals(True)
                    enable_check.setChecked(False)
                    enable_check.blockSignals(False)
                elif not enable_check.isChecked():
                    disable_check.blockSignals(True)
                    disable_check.setChecked(True)
                    disable_check.blockSignals(False)
                self._queue_preview_restart()

            update_focus_controls()

            index.currentIndexChanged.connect(self._queue_preview_restart)
            enabled.stateChanged.connect(self._queue_preview_restart)
            flip_h.stateChanged.connect(self._queue_preview_restart)
            flip_v.stateChanged.connect(self._queue_preview_restart)
            rotation.currentTextChanged.connect(self._queue_preview_restart)
            barcode_enabled.toggled.connect(set_barcode_enabled)
            barcode_disabled.toggled.connect(set_barcode_disabled)
            auto_focus.toggled.connect(set_auto_focus)
            manual_focus_mode.toggled.connect(set_manual_focus)
            manual_focus.valueChanged.connect(update_focus_controls)
            manual_focus.valueChanged.connect(lambda _value, slot=config.slot: self._apply_focus_change_immediately(slot))

            camera_box = QGroupBox()
            camera_box.setObjectName("cameraSettingsCard")
            card = QGridLayout(camera_box)
            card.setContentsMargins(12, 14, 12, 12)
            card.setHorizontalSpacing(10)
            card.setVerticalSpacing(6)

            card.addWidget(enabled, 0, 0, 1, 3)
            card.addWidget(QLabel("相機機號"), 1, 0)
            card.addWidget(index, 1, 1, 1, 2)

            card.addWidget(QLabel("影像方向"), 2, 0)
            card.addWidget(flip_h, 2, 1)
            card.addWidget(flip_v, 2, 2)
            card.addWidget(QLabel("影像旋轉"), 3, 0)
            card.addWidget(rotation, 3, 1, 1, 2)

            card.addWidget(QLabel("條碼辨識"), 4, 0)
            card.addWidget(barcode_enabled, 4, 1)
            card.addWidget(barcode_disabled, 4, 2)

            card.addWidget(QLabel("焦距方法"), 5, 0)
            card.addWidget(auto_focus, 5, 1)
            card.addWidget(manual_focus_mode, 5, 2)
            card.addWidget(QLabel("固定焦距"), 6, 0)
            card.addLayout(focus_value_row, 6, 1, 1, 2)

            card.setColumnStretch(2, 1)
            card.setRowStretch(7, 1)

            self.camera_tabs.addTab(camera_box, f"相機 {config.slot}")
            self.rows.append((
                enabled, index, flip_h, flip_v, rotation,
                barcode_enabled, barcode_disabled, auto_focus, manual_focus_mode, manual_focus, manual_focus_value,
            ))

        layout.addWidget(self.camera_tabs, 1)
        return group

    def build_preview_group(self):
        group = QGroupBox("相機設定即時預覽")
        group.setObjectName("cameraPreviewGroup")
        layout = QVBoxLayout(group)
        self.preview_view = CameraView("相機")

        layout.addWidget(self.preview_view, 1)
        return group

    def camera_index_options(self, selected_index=None):
        values = set(range(31))
        values.update(self.state.detected_cameras)
        if selected_index is not None:
            values.add(selected_index)
        return sorted(values)

    def populate_camera_index_combo(self, combo, selected_index=None):
        combo.blockSignals(True)
        combo.clear()
        for index in self.camera_index_options(selected_index):
            combo.addItem(str(index), index)
        if selected_index is not None:
            match = combo.findData(selected_index)
            if match >= 0:
                combo.setCurrentIndex(match)
        combo.blockSignals(False)

    def refresh_camera_index_combos(self):
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            index_combo = controls[1]
            selected = int(index_combo.currentData() if index_combo.currentData() is not None else config.device_index)
            self.populate_camera_index_combo(index_combo, selected)

    def refresh_camera_model_combos(self):
        pass

    def refresh(self):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            return
        ensure_model_configs(self.state)
        self.state.use_simulation = False
        self.refresh_camera_index_combos()
        self._loading_camera_controls = True
        try:
            for config, controls in zip(self.state.inspection_cameras, self.rows):
                (
                    enabled, index, flip_h, flip_v, rotation, barcode_enabled, barcode_disabled,
                    auto_focus, manual_focus_mode, manual_focus, manual_focus_value,
                ) = controls
                enabled.setChecked(config.enabled)
                self.populate_camera_index_combo(index, config.device_index)
                flip_h.setChecked(config.flip_horizontal)
                flip_v.setChecked(config.flip_vertical)
                rotation.setCurrentText(str(config.rotation_degrees))
                barcode_enabled.setChecked(config.barcode_read_enabled)
                barcode_disabled.setChecked(not config.barcode_read_enabled)
                is_manual_focus = getattr(config, "focus_mode", "auto") == "manual"
                auto_focus.setChecked(not is_manual_focus)
                manual_focus_mode.setChecked(is_manual_focus)
                manual_focus.setValue(int(getattr(config, "manual_focus_value", 120)))
                manual_focus_value.setText(str(manual_focus.value()))
                manual_focus.setEnabled(manual_focus_mode.isChecked())
                manual_focus_value.setEnabled(manual_focus_mode.isChecked())
        finally:
            self._loading_camera_controls = False
        self.apply_role_permissions()
        self.restart_preview()

    def apply_role_permissions(self):
        pass

    def _queue_preview_restart(self):
        if self._loading_camera_controls:
            return
        self._preview_debounce.start()
        self._camera_autosave_timer.start()

    def _apply_focus_change_immediately(self, slot):
        if self._loading_camera_controls:
            return
        if slot < 1 or slot > len(self.rows):
            return
        self.persist_camera_settings()
        controls = self.rows[slot - 1]
        _, _, _, _, _, _, _, auto_focus, manual_focus_mode, manual_focus, _ = controls
        focus_mode = "manual" if manual_focus_mode.isChecked() else "auto"
        manual_focus_value = manual_focus.value()
        for source_slot, source in self.preview_sources:
            if source_slot == slot:
                source.apply_focus_settings(focus_mode, manual_focus_value)
                break
        self.update_camera_previews()

    def restart_preview(self):
        self.stop_preview()
        self.clear_preview_grid()
        enabled_rows = self.current_enabled_camera_rows()
        if not enabled_rows:
            self.preview_view.set_message("目前沒有啟用的相機。", is_error=True)
            return

        self.preview_cameras = {camera["slot"]: camera for camera in enabled_rows}
        for camera in enabled_rows:
            source = VideoSource(
                f"相機 {camera['slot']}",
                camera["device_index"],
                False,
                camera["focus_mode"],
                camera["manual_focus_value"],
            )
            if source.has_error():
                self.preview_view.set_message(source.last_error, is_error=True)
            self.preview_sources.append((camera["slot"], source))
        self.preview_timer.start(33)

    def stop_preview(self):
        self.preview_timer.stop()
        for _, source in self.preview_sources:
            source.release()
        self.preview_sources = []

    def clear_preview_grid(self):
        self.preview_cameras = {}
        self.preview_view.set_message("No Signal")

    def update_camera_previews(self):
        if not hasattr(self, "preview_view"):
            return
        slot = self.camera_tabs.currentIndex() + 1
        camera = self.preview_cameras.get(slot)
        if not camera:
            self.preview_view.base_title = f"相機 {slot}"
            self.preview_view.set_extra_info("")
            self.preview_view.update_fps_label()
            self.preview_view.set_message("此相機未啟用。")
            return
        source_by_slot = {slot: source for slot, source in self.preview_sources}
        source = source_by_slot.get(slot)
        if not source:
            self.preview_view.set_message("沒有相機來源。", is_error=True)
            return
        frame = source.read()
        if frame is None:
            self.preview_view.set_message(source.last_error or "沒有相機影像。", is_error=True)
            return
        frame = apply_frame_transform(
            frame,
            flip_horizontal=camera["flip_horizontal"],
            flip_vertical=camera["flip_vertical"],
            rotation_degrees=camera["rotation_degrees"],
        )
        self.preview_view.base_title = f"相機 {slot}"
        self.preview_view.set_extra_info(self.format_focus_info(camera, source))
        self.preview_view.set_frame(frame, input_fps=source.input_fps)

    def format_focus_info(self, camera, source=None):
        current_focus = source.current_focus_value() if source else None
        current_text = "--" if current_focus is None else f"{current_focus:.0f}"
        if camera["focus_mode"] == "manual":
            return f"焦距: {camera['manual_focus_value']} / 目前 {current_text}"
        return f"焦距: 自動 / 目前 {current_text}"

    def current_enabled_camera_rows(self):
        enabled_rows = []
        for slot, controls in enumerate(self.rows, start=1):
            (
                enabled, index, flip_h, flip_v, rotation, barcode_enabled, _,
                _, manual_focus_mode, manual_focus, _,
            ) = controls
            if enabled.isChecked():
                model_names = camera_model_names(self.state.inspection_cameras[slot - 1])
                enabled_rows.append(
                    {
                        "slot": slot,
                        "device_index": int(index.currentData()),
                        "model_name": ", ".join(model_names),
                        "model_names": model_names,
                        "flip_horizontal": flip_h.isChecked(),
                        "flip_vertical": flip_v.isChecked(),
                        "rotation_degrees": int(rotation.currentText()),
                        "barcode_read_enabled": barcode_enabled.isChecked(),
                        "focus_mode": "manual" if manual_focus_mode.isChecked() else "auto",
                        "manual_focus_value": manual_focus.value(),
                    }
                )
        return enabled_rows

    def apply(self, enter_monitor=True):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能修改相機與模型設定。")
            return False
        if enter_monitor:
            self.release_external_cameras()
        enabled_names = enabled_model_names(self.state)
        if not enabled_names:
            QMessageBox.warning(self, "模型設定", "至少需要啟用一個模型，才能指定給相機。")
            return False

        enabled_count = 0
        missing_model_slots = []
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            (
                enabled, index, flip_h, flip_v, rotation, barcode_enabled, _,
                _, manual_focus_mode, manual_focus, _,
            ) = controls
            config.enabled = enabled.isChecked()
            config.device_index = int(index.currentData())
            config.flip_horizontal = flip_h.isChecked()
            config.flip_vertical = flip_v.isChecked()
            config.rotation_degrees = int(rotation.currentText())
            config.barcode_read_enabled = barcode_enabled.isChecked()
            config.focus_mode = "manual" if manual_focus_mode.isChecked() else "auto"
            config.manual_focus_value = manual_focus.value()
            enabled_count += int(config.enabled)
            if config.enabled and not camera_model_names(config):
                missing_model_slots.append(f"相機 {config.slot}")
        if enabled_count == 0:
            QMessageBox.warning(self, "相機設定", "至少需要啟用一顆檢測相機。")
            return False

        if missing_model_slots:
            QMessageBox.warning(
                self,
                "Model assignment",
                "Select at least one model for: " + ", ".join(missing_model_slots),
            )
            return False

        self.state.use_simulation = False
        self.state.settings_applied = True
        save_app_config(self.state)
        if enter_monitor:
            self.stop_preview()
            self.on_apply()
        return True

    def persist_camera_settings(self):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            return
        self.write_camera_controls_to_state()
        self.state.use_simulation = False
        save_app_config(self.state)

    def write_camera_controls_to_state(self):
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            (
                enabled, index, flip_h, flip_v, rotation, barcode_enabled, _,
                _, manual_focus_mode, manual_focus, _,
            ) = controls
            config.enabled = enabled.isChecked()
            config.device_index = int(index.currentData())
            config.flip_horizontal = flip_h.isChecked()
            config.flip_vertical = flip_v.isChecked()
            config.rotation_degrees = int(rotation.currentText())
            config.barcode_read_enabled = barcode_enabled.isChecked()
            config.focus_mode = "manual" if manual_focus_mode.isChecked() else "auto"
            config.manual_focus_value = manual_focus.value()

    def release_external_cameras(self):
        self.stop_preview()
        if self.before_camera_scan:
            self.before_camera_scan()

    def logout(self):
        self.stop_preview()
        if self.on_logout:
            self.on_logout()


class ModelSettingsPage(QWidget):
    def __init__(self, state: AppState, on_saved=None, on_logout=None):
        super().__init__()
        self.state = state
        self.on_saved = on_saved
        self.on_logout = on_logout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(self.build_model_group(), 1)

    def build_model_group(self):
        group = QGroupBox()
        layout = QVBoxLayout(group)
        self.model_table = QTableWidget(0, 4)
        self.model_table.setHorizontalHeaderLabels(["啟用", "模型名稱", "模態", "模型檔案"])
        self.model_table.setColumnWidth(0, 54)
        self.model_table.setColumnWidth(1, 180)
        self.model_table.setColumnWidth(2, 120)
        self.model_table.setColumnWidth(3, 520)

        self.add_model_button = QPushButton("新增模型")
        self.add_model_button.clicked.connect(self.add_model_row)
        self.remove_model_button = QPushButton("移除選取模型")
        self.remove_model_button.clicked.connect(self.remove_selected_model)
        self.browse_model_button = QPushButton("選取模型檔案")
        self.browse_model_button.clicked.connect(self.browse_selected_model)
        self.rescan_models_button = QPushButton("重新掃描 models 模型")
        self.rescan_models_button.clicked.connect(self.rescan_models)

        actions = QHBoxLayout()
        actions.addWidget(self.add_model_button)
        actions.addWidget(self.remove_model_button)
        actions.addWidget(self.browse_model_button)
        actions.addWidget(self.rescan_models_button)
        actions.addStretch()

        layout.addWidget(self.model_table)
        layout.addLayout(actions)
        return group

    def refresh(self):
        ensure_model_configs(self.state)
        self.load_model_table()
        self.apply_role_permissions()

    def apply_role_permissions(self):
        can_manage_models = has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions)
        self.model_table.setEditTriggers(
            QAbstractItemView.EditTrigger.AllEditTriggers
            if can_manage_models
            else QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.model_table.setEnabled(can_manage_models)
        self.add_model_button.setVisible(can_manage_models)
        self.remove_model_button.setVisible(can_manage_models)
        self.browse_model_button.setVisible(can_manage_models)
        self.rescan_models_button.setVisible(can_manage_models)

    def load_model_table(self):
        self.model_table.setRowCount(0)
        for config in self.state.model_configs:
            self.add_model_row(config)

    def add_model_row(self, config=None):
        if config is None and not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能新增模型。")
            return
        config = config or ModelConfig(name=f"Model {self.model_table.rowCount() + 1}")
        row = self.model_table.rowCount()
        self.model_table.insertRow(row)

        enabled = QCheckBox()
        enabled.setChecked(config.enabled)
        self.model_table.setCellWidget(row, 0, enabled)

        self.model_table.setItem(row, 1, QTableWidgetItem(config.name))

        modality = QComboBox()
        for value, label in MODEL_MODALITIES:
            modality.addItem(label, value)
        match = modality.findData(config.modality)
        modality.setCurrentIndex(match if match >= 0 else 0)
        self.model_table.setCellWidget(row, 2, modality)

        self.model_table.setItem(row, 3, QTableWidgetItem(config.file_path))

    def remove_selected_model(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能移除模型。")
            return
        row = self.model_table.currentRow()
        if row >= 0:
            self.model_table.removeRow(row)

    def browse_selected_model(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能選取模型檔案。")
            return
        row = self.model_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "選擇模型", "請先選取一列模型設定。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "選擇模型檔案",
            str(APP_DIR),
            "Model Files (*.pt *.onnx *.engine *.weights *.bin *.json);;All Files (*)",
        )
        if path:
            self.model_table.setItem(row, 3, QTableWidgetItem(path))

    def rescan_models(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能重新掃描模型。")
            return
        ensure_model_configs(self.state)
        self.load_model_table()

    def collect_model_configs(self):
        configs = []
        for row in range(self.model_table.rowCount()):
            enabled_widget = self.model_table.cellWidget(row, 0)
            modality_widget = self.model_table.cellWidget(row, 2)
            name_item = self.model_table.item(row, 1)
            path_item = self.model_table.item(row, 3)
            name = name_item.text().strip() if name_item else f"Model {row + 1}"
            path = path_item.text().strip() if path_item else ""
            configs.append(
                ModelConfig(
                    name=name or f"Model {row + 1}",
                    modality=modality_widget.currentData() if modality_widget else "vision",
                    file_path=path,
                    enabled=enabled_widget.isChecked() if enabled_widget else True,
                )
            )
        return configs

    def save(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能修改模型清單。")
            return False
        self.state.model_configs = self.collect_model_configs()
        ensure_model_configs(self.state)
        save_app_config(self.state)
        if self.on_saved:
            self.on_saved()
        return True

    def logout(self):
        if self.on_logout:
            self.on_logout()


class CameraModelSettingsPage(QWidget):
    def __init__(self, state: AppState, on_saved=None, on_logout=None):
        super().__init__()
        self.state = state
        self.on_saved = on_saved
        self.on_logout = on_logout
        self.camera_model_tables = []
        self.camera_photo_views = {}
        self.camera_photo_source = None
        self.camera_photo_timer = QTimer(self)
        self.camera_photo_timer.timeout.connect(self.update_camera_photo_preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.camera_model_tabs = QTabWidget()
        for camera in self.state.inspection_cameras:
            self.camera_model_tabs.addTab(self.build_camera_model_page(camera), f"相機 {camera.slot}")
        self.camera_model_tabs.currentChanged.connect(self.update_model_tab_preview)
        layout.addWidget(self.camera_model_tabs, 1)

    def build_camera_model_page(self, camera):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        model_group = QGroupBox("選項模型")
        model_layout = QVBoxLayout(model_group)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["指定", "模型名稱", "模態", "模型檔案"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 54)
        table.setColumnWidth(1, 180)
        table.setColumnWidth(2, 120)
        model_layout.addWidget(table, 1)

        photo_tabs = QTabWidget()
        photo_page = QWidget()
        photo_layout = QVBoxLayout(photo_page)
        photo_layout.setContentsMargins(12, 12, 12, 12)
        photo_view = CameraView(f"相機 {camera.slot}")
        photo_layout.addWidget(photo_view, 1)
        photo_tabs.addTab(photo_page, "照片")

        layout.addWidget(model_group, 1)
        layout.addWidget(photo_tabs, 1)
        self.camera_model_tables.append((camera, table))
        self.camera_photo_views[camera.slot] = photo_view
        return page

    def refresh(self):
        ensure_model_configs(self.state)
        self.load_camera_model_tabs()
        self.apply_role_permissions()
        self.update_model_tab_preview(self.camera_model_tabs.currentIndex())

    def apply_role_permissions(self):
        can_manage_models = has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions)
        for _, table in self.camera_model_tables:
            table.setEnabled(can_manage_models)

    def load_camera_model_tabs(self):
        for camera, table in self.camera_model_tables:
            table.setRowCount(0)
            selected_names = set(camera_model_names(camera))
            for model in self.state.model_configs:
                if not model.enabled:
                    continue
                row = table.rowCount()
                table.insertRow(row)
                assigned = QCheckBox()
                assigned.setChecked(model.name in selected_names)
                table.setCellWidget(row, 0, assigned)
                table.setItem(row, 1, QTableWidgetItem(model.name))
                table.setItem(row, 2, QTableWidgetItem(model_modality_label(model.modality)))
                table.setItem(row, 3, QTableWidgetItem(model.file_path))

    def collect_camera_model_assignments(self):
        valid_names = set(enabled_model_names(self.state))
        for camera, table in self.camera_model_tables:
            selected_names = []
            for row in range(table.rowCount()):
                assigned = table.cellWidget(row, 0)
                name_item = table.item(row, 1)
                model_name = name_item.text().strip() if name_item else ""
                if assigned and assigned.isChecked() and model_name in valid_names:
                    selected_names.append(model_name)
            set_camera_model_names(camera, selected_names)

    def update_model_tab_preview(self, index):
        self.stop_camera_photo_preview()
        if index < 0 or index >= len(self.state.inspection_cameras):
            return
        camera = self.state.inspection_cameras[index]
        view = self.camera_photo_views.get(camera.slot)
        if not view:
            return
        source = VideoSource(
            f"相機 {camera.slot}",
            camera.device_index,
            False,
            getattr(camera, "focus_mode", "auto"),
            getattr(camera, "manual_focus_value", 120),
        )
        self.camera_photo_source = (camera, source)
        if source.has_error():
            view.set_message(source.last_error, is_error=True)
        self.camera_photo_timer.start(33)

    def update_camera_photo_preview(self):
        if not self.camera_photo_source:
            return
        camera, source = self.camera_photo_source
        view = self.camera_photo_views.get(camera.slot)
        if not view:
            return
        frame = source.read()
        if frame is None:
            view.set_message(source.last_error or "沒有相機影像。", is_error=True)
            return
        frame = apply_frame_transform(
            frame,
            flip_horizontal=camera.flip_horizontal,
            flip_vertical=camera.flip_vertical,
            rotation_degrees=camera.rotation_degrees,
        )
        view.set_frame(frame, input_fps=source.input_fps)

    def stop_camera_photo_preview(self):
        self.camera_photo_timer.stop()
        if self.camera_photo_source:
            _, source = self.camera_photo_source
            source.release()
            self.camera_photo_source = None

    def save(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能修改相機模型設定。")
            return False
        self.collect_camera_model_assignments()
        save_app_config(self.state)
        if self.on_saved:
            self.on_saved()
        return True

    def logout(self):
        self.stop_camera_photo_preview()
        if self.on_logout:
            self.on_logout()


class DisplaySettingsPage(QWidget):
    def __init__(self, state: AppState, on_display_change=None, on_logout=None):
        super().__init__()
        self.state = state
        self.on_display_change = on_display_change
        self.on_logout = on_logout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        layout.addWidget(self.build_display_group())
        layout.addStretch()

    def build_display_group(self):
        group = QGroupBox()
        group.setObjectName("displaySettingsGroup")
        form = QGridLayout(group)

        self.display_mode = QComboBox()
        for mode, label in DISPLAY_MODE_OPTIONS:
            self.display_mode.addItem(label, mode)
        self.display_mode.currentIndexChanged.connect(self.update_display_size_controls)

        self.display_width = QSpinBox()
        self.display_width.setRange(640, 7680)
        self.display_width.setSingleStep(20)
        self.display_width.setSuffix(" px")

        self.display_height = QSpinBox()
        self.display_height.setRange(480, 4320)
        self.display_height.setSingleStep(20)
        self.display_height.setSuffix(" px")

        self.display_font_size = QComboBox()
        for size in FONT_SIZE_OPTIONS:
            self.display_font_size.addItem(f"{size} px", size)

        hint = QLabel("全螢幕會自動使用目前螢幕；非全螢幕可自動最大化或指定寬高。")
        hint.setObjectName("mutedText")

        form.addWidget(QLabel("顯示模式"), 0, 0)
        form.addWidget(self.display_mode, 0, 1, 1, 2)
        form.addWidget(QLabel("寬度"), 1, 0)
        form.addWidget(self.display_width, 1, 1)
        form.addWidget(QLabel("高度"), 1, 2)
        form.addWidget(self.display_height, 1, 3)
        form.addWidget(QLabel("字體大小"), 2, 0)
        form.addWidget(self.display_font_size, 2, 1)
        form.addWidget(hint, 3, 0, 1, 4)
        self.load_display_controls()
        return group

    def refresh(self):
        self.load_display_controls()

    def save_display_settings(self):
        self.state.display.mode = self.display_mode.currentData()
        self.state.display.width = self.display_width.value()
        self.state.display.height = self.display_height.value()
        self.state.display.font_size = int(self.display_font_size.currentData())
        save_app_config(self.state)
        if self.on_display_change:
            self.on_display_change()
        QMessageBox.information(self, "保存完成", "GUI 顯示設定已更新。")

    def load_display_controls(self):
        if not hasattr(self, "display_mode"):
            return
        self.display_mode.blockSignals(True)
        match = self.display_mode.findData(self.state.display.mode)
        self.display_mode.setCurrentIndex(match if match >= 0 else 0)
        self.display_mode.blockSignals(False)
        self.display_width.setValue(self.state.display.width)
        self.display_height.setValue(self.state.display.height)
        font_size = int(self.state.display.font_size)
        font_match = self.display_font_size.findData(font_size)
        if font_match < 0:
            self.display_font_size.addItem(f"{font_size} px", font_size)
            font_match = self.display_font_size.findData(font_size)
        self.display_font_size.setCurrentIndex(font_match)
        self.update_display_size_controls()

    def update_display_size_controls(self):
        custom = self.display_mode.currentData() == "custom"
        self.display_width.setEnabled(custom)
        self.display_height.setEnabled(custom)

    def logout(self):
        if self.on_logout:
            self.on_logout()


class DecisionSettingsPage(QWidget):
    RULE_ROW_HEIGHT = 45

    def __init__(self, state: AppState, on_logout=None):
        super().__init__()
        self.setObjectName("decisionSettingsPage")
        self.state = state
        self.on_logout = on_logout
        self.rule_rows = []
        self.rule_tab_slots = []
        self.loading_rules = False
        self.camera_preview_view = None
        self.camera_preview_source = None
        self.camera_preview_timer = QTimer(self)
        self.camera_preview_timer.timeout.connect(self.update_camera_preview)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self.autosave_decision_settings)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("判定設定")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        content = QHBoxLayout()
        content.setSpacing(12)
        content.addWidget(self.build_decision_group(), 1)
        content.addWidget(self.build_camera_preview_group(), 1)

        layout.addLayout(header)
        layout.addLayout(content, 1)

    def build_decision_group(self):
        group = QGroupBox("PASS / NG 條件")
        group.setObjectName("decisionRulesGroup")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        global_row = QHBoxLayout()
        global_row.addWidget(QLabel("全域 PASS 信心值門檻"))
        self.global_threshold = QDoubleSpinBox()
        self.global_threshold.setRange(0.0, 1.0)
        self.global_threshold.setSingleStep(0.05)
        self.global_threshold.setDecimals(3)
        self.global_threshold.valueChanged.connect(self.queue_auto_save)
        self.global_threshold.valueChanged.connect(self.update_threshold_mode_controls)
        global_row.addWidget(self.global_threshold)
        self.global_threshold_mode = QRadioButton("使用全域")
        self.custom_threshold_mode = QRadioButton("自訂")
        self.global_threshold_mode.toggled.connect(self.update_threshold_mode_controls)
        self.custom_threshold_mode.toggled.connect(self.update_threshold_mode_controls)
        self.global_threshold_mode.toggled.connect(self.queue_auto_save)
        self.custom_threshold_mode.toggled.connect(self.queue_auto_save)
        global_row.addWidget(self.global_threshold_mode)
        global_row.addWidget(self.custom_threshold_mode)
        global_row.addStretch()

        self.model_tabs = QTabWidget()
        self.model_tabs.currentChanged.connect(self.sync_camera_preview_to_rule_tab)

        layout.addLayout(global_row)
        layout.addWidget(self.model_tabs, 1)
        return group

    def build_camera_preview_group(self):
        group = QGroupBox("相機影像")
        group.setObjectName("decisionCameraPreviewGroup")
        layout = QVBoxLayout(group)
        self.camera_preview_view = CameraView("相機")
        layout.addWidget(self.camera_preview_view, 1)
        return group

    def refresh(self):
        ensure_model_configs(self.state)
        self.loading_rules = True
        self.global_threshold.setValue(self.state.decision.pass_confidence_threshold)
        use_global = getattr(self.state.decision, "confidence_threshold_mode", "custom") == "global"
        self.global_threshold_mode.setChecked(use_global)
        self.custom_threshold_mode.setChecked(not use_global)
        self.load_rule_table()
        self.loading_rules = False
        self.update_threshold_mode_controls()
        self.update_camera_preview_tab(self.model_tabs.currentIndex())

    def load_rule_table(self):
        self.rule_rows = []
        self.rule_tab_slots = []
        self.model_tabs.clear()
        for camera in self.state.inspection_cameras:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            model_names = camera_model_names(camera) if camera.enabled else []
            if model_names:
                table = self.create_rule_table(show_model=True)
                page_layout.addWidget(table)
                for model_name in model_names:
                    self.add_rule_row(table, camera.slot, model_name, show_model=True)
            else:
                empty_label = QLabel("此相機目前沒有啟用的模型判定規則。")
                empty_label.setObjectName("mutedText")
                page_layout.addWidget(empty_label)
                page_layout.addStretch()
            self.model_tabs.addTab(page, f"相機 {camera.slot}")
            self.rule_tab_slots.append(camera.slot)

    def create_rule_table(self, show_model=False):
        table = QTableWidget(0, 6 if show_model else 5)
        if show_model:
            table.setHorizontalHeaderLabels(["畫面", "模型", "信心值比較", "信心值", "數量比較", "必須偵測標籤框數"])
        else:
            table.setHorizontalHeaderLabels(["畫面", "信心值比較", "信心值", "數量比較", "必須偵測標籤框數"])
        table.verticalHeader().setDefaultSectionSize(self.RULE_ROW_HEIGHT)
        table.verticalHeader().setMinimumSectionSize(self.RULE_ROW_HEIGHT)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        if show_model:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        else:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    def create_operator_combo(self, value, fallback):
        combo = QComboBox()
        for operator in DECISION_OPERATORS:
            combo.addItem(operator, operator)
        selected = normalise_decision_operator(value, fallback)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        combo.currentIndexChanged.connect(self.queue_auto_save)
        return combo

    def add_rule_row(self, table, slot, model_name, show_model=False):
        row = table.rowCount()
        table.insertRow(row)
        table.setRowHeight(row, self.RULE_ROW_HEIGHT)

        rule_key = _rule_key(slot, model_name)
        rule = self.state.decision.model_rules.get(rule_key, {})

        table.setItem(row, 0, QTableWidgetItem(f"相機 {slot}"))
        confidence_operator_column = 1
        confidence_column = 2
        count_operator_column = 3
        count_column = 4
        if show_model:
            table.setItem(row, 1, QTableWidgetItem(model_name))
            confidence_operator_column = 2
            confidence_column = 3
            count_operator_column = 4
            count_column = 5

        confidence_operator = self.create_operator_combo(rule.get("confidence_operator", ">="), ">=")
        table.setCellWidget(row, confidence_operator_column, confidence_operator)

        confidence = QDoubleSpinBox()
        confidence.setRange(0.0, 1.0)
        confidence.setSingleStep(0.05)
        confidence.setDecimals(3)
        confidence.setValue(float(rule.get("confidence_threshold", self.state.decision.pass_confidence_threshold)))
        confidence.valueChanged.connect(self.queue_auto_save)
        table.setCellWidget(row, confidence_column, confidence)

        count = QComboBox()
        for value in range(0, 21):
            count.addItem(str(value), value)
        required_count = int(rule.get("required_object_count", 1))
        if count.findData(required_count) < 0:
            count.addItem(str(required_count), required_count)
        count.setCurrentIndex(count.findData(required_count))
        count.currentIndexChanged.connect(self.queue_auto_save)
        count_operator = self.create_operator_combo(rule.get("required_object_count_operator", "="), "=")
        table.setCellWidget(row, count_operator_column, count_operator)
        table.setCellWidget(row, count_column, count)

        self.rule_rows.append(
            {
                "slot": slot,
                "model_name": model_name,
                "confidence_operator": confidence_operator,
                "confidence": confidence,
                "count_operator": count_operator,
                "count": count,
            }
        )

    def queue_auto_save(self):
        if self.loading_rules:
            return
        self.autosave_timer.start(300)

    def autosave_decision_settings(self):
        self.persist_decision_settings()

    def update_threshold_mode_controls(self):
        use_global = self.global_threshold_mode.isChecked()
        for row in self.rule_rows:
            row["confidence_operator"].setEnabled(not use_global)
            row["confidence"].setEnabled(not use_global)
            if use_global:
                row["confidence_operator"].setCurrentIndex(row["confidence_operator"].findData(">="))
                row["confidence"].setValue(self.global_threshold.value())

    def save_decision_settings(self):
        self.persist_decision_settings()
        QMessageBox.information(self, "儲存完成", "PASS / NG 判定設定已儲存。")
        return True

    def persist_decision_settings(self):
        self.state.decision.pass_confidence_threshold = self.global_threshold.value()
        self.state.decision.confidence_threshold_mode = (
            "global" if self.global_threshold_mode.isChecked() else "custom"
        )
        rules = {}
        for row in self.rule_rows:
            confidence_operator = ">=" if self.global_threshold_mode.isChecked() else row["confidence_operator"].currentData()
            confidence_threshold = (
                self.global_threshold.value()
                if self.global_threshold_mode.isChecked()
                else row["confidence"].value()
            )
            rules[_rule_key(row["slot"], row["model_name"])] = {
                "confidence_operator": confidence_operator,
                "confidence_threshold": confidence_threshold,
                "required_object_count_operator": row["count_operator"].currentData(),
                "required_object_count": int(row["count"].currentData()),
            }
        self.state.decision.model_rules = rules
        save_app_config(self.state)

    def sync_camera_preview_to_rule_tab(self, index):
        self.update_camera_preview_tab(index)

    def update_camera_preview_tab(self, index):
        self.stop_camera_preview()
        if index < 0 or index >= len(self.rule_tab_slots):
            return
        slot = self.rule_tab_slots[index]
        camera = next((config for config in self.state.inspection_cameras if config.slot == slot), None)
        view = self.camera_preview_view
        if camera is None:
            if view:
                view.set_message("沒有相機設定。", is_error=True)
            return
        if not view:
            return
        view.base_title = f"相機 {camera.slot}"
        if view.show_info:
            view.update_fps_label()
        source = VideoSource(
            f"相機 {camera.slot}",
            camera.device_index,
            False,
            getattr(camera, "focus_mode", "auto"),
            getattr(camera, "manual_focus_value", 120),
        )
        self.camera_preview_source = (camera, source)
        if source.has_error():
            view.set_message(source.last_error, is_error=True)
        self.camera_preview_timer.start(33)

    def update_camera_preview(self):
        if not self.camera_preview_source:
            return
        camera, source = self.camera_preview_source
        view = self.camera_preview_view
        if not view:
            return
        frame = source.read()
        if frame is None:
            view.set_message(source.last_error or "沒有相機影像。", is_error=True)
            return
        frame = apply_frame_transform(
            frame,
            flip_horizontal=camera.flip_horizontal,
            flip_vertical=camera.flip_vertical,
            rotation_degrees=camera.rotation_degrees,
        )
        frame = self.frame_with_region_overlay(camera, frame)
        view.set_frame(frame, input_fps=source.input_fps)

    def frame_with_region_overlay(self, camera, frame):
        if not getattr(camera, "region_detection_enabled", False):
            return frame
        if not camera.detection_regions and not camera.exclusion_regions:
            return frame
        annotated = frame.copy()
        height, width = annotated.shape[:2]
        self.draw_region_list(
            annotated,
            camera.detection_regions,
            hex_to_bgr(self.state.region_overlay.detection_color),
            "ROI",
            width,
            height,
        )
        self.draw_region_list(
            annotated,
            camera.exclusion_regions,
            hex_to_bgr(self.state.region_overlay.exclusion_color),
            "EX",
            width,
            height,
        )
        return annotated

    def draw_region_list(self, frame, regions, color, label, width, height):
        for index, region in enumerate(regions, start=1):
            x1, y1, x2, y2 = normalised_region_to_pixels(region, width, height)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
            cv2.putText(
                frame,
                self.format_region_label(label, index, region),
                (x1 + 3, max(10, y1 + 11)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.28,
                color,
                1,
            )

    def format_region_label(self, label, index, region):
        roi_id = region.get("roi_id")
        if roi_id is not None:
            return f"#{roi_id}"
        return f"{label} {index}"

    def stop_camera_preview(self):
        self.camera_preview_timer.stop()
        if self.camera_preview_source:
            _, source = self.camera_preview_source
            source.release()
            self.camera_preview_source = None

    def logout(self):
        self.stop_camera_preview()
        if self.on_logout:
            self.on_logout()
