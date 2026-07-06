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
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import VideoSource, apply_frame_transform
from valve_gui.config_store import save_app_config
from valve_gui.model_registry import camera_model_names, enabled_model_names, ensure_model_configs, set_camera_model_names
from valve_gui.models import AppState, ModelConfig
from valve_gui.paths import APP_DIR
from valve_gui.permissions import (
    PERMISSION_MANAGE_MODELS,
    PERMISSION_OPEN_SETTINGS,
    has_permission,
)
from valve_gui.utils import decision_rule_key as _rule_key
from valve_gui.widgets import CameraView


MODEL_MODALITIES = ["vision", "text", "multimodal", "ocr", "classifier"]
ROTATION_OPTIONS = ["0", "90", "180", "270"]
DISPLAY_MODE_OPTIONS = [
    ("auto", "自動適應目前螢幕"),
    ("custom", "指定 GUI 畫面大小"),
    ("fullscreen", "全螢幕"),
]
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
        self.preview_views = []
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_camera_previews)
        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.setInterval(400)
        self._preview_debounce.timeout.connect(self.restart_preview)

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

        for config in self.state.inspection_cameras:
            enabled = QCheckBox("啟用")
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

            barcode = QCheckBox("啟用條碼辨識")
            barcode.setChecked(config.barcode_read_enabled)

            auto_focus = QCheckBox("自動焦距")
            manual_focus_mode = QCheckBox("手動焦距")
            is_manual_focus = getattr(config, "focus_mode", "auto") == "manual"
            auto_focus.setChecked(not is_manual_focus)
            manual_focus_mode.setChecked(is_manual_focus)

            manual_focus = QSlider(Qt.Orientation.Horizontal)
            manual_focus.setRange(0, 255)
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

            def set_auto_focus(checked, auto_check=auto_focus, manual_check=manual_focus_mode):
                if checked:
                    manual_check.blockSignals(True)
                    manual_check.setChecked(False)
                    manual_check.blockSignals(False)
                elif not manual_check.isChecked():
                    auto_check.blockSignals(True)
                    auto_check.setChecked(True)
                    auto_check.blockSignals(False)
                update_focus_controls()
                self._queue_preview_restart()

            def set_manual_focus(checked, auto_check=auto_focus, manual_check=manual_focus_mode):
                if checked:
                    auto_check.blockSignals(True)
                    auto_check.setChecked(False)
                    auto_check.blockSignals(False)
                elif not auto_check.isChecked():
                    manual_check.blockSignals(True)
                    manual_check.setChecked(True)
                    manual_check.blockSignals(False)
                update_focus_controls()
                self._queue_preview_restart()

            update_focus_controls()

            index.currentIndexChanged.connect(self._queue_preview_restart)
            enabled.stateChanged.connect(self._queue_preview_restart)
            flip_h.stateChanged.connect(self._queue_preview_restart)
            flip_v.stateChanged.connect(self._queue_preview_restart)
            rotation.currentTextChanged.connect(self._queue_preview_restart)
            auto_focus.toggled.connect(set_auto_focus)
            manual_focus_mode.toggled.connect(set_manual_focus)
            manual_focus.valueChanged.connect(update_focus_controls)
            manual_focus.valueChanged.connect(self._queue_preview_restart)

            camera_box = QGroupBox(f"Camera {config.slot}")
            camera_box.setObjectName("cameraSettingsCard")
            card = QGridLayout(camera_box)
            card.setContentsMargins(12, 14, 12, 12)
            card.setHorizontalSpacing(10)
            card.setVerticalSpacing(6)

            card.addWidget(enabled, 0, 0)
            card.addWidget(QLabel("相機"), 0, 1)
            card.addWidget(index, 0, 2)

            card.addWidget(QLabel("方向"), 1, 0)
            card.addWidget(flip_h, 1, 1)
            card.addWidget(flip_v, 1, 2)
            card.addWidget(QLabel("旋轉"), 2, 0)
            card.addWidget(rotation, 2, 1, 1, 2)

            card.addWidget(QLabel("條碼"), 3, 0)
            card.addWidget(barcode, 3, 1, 1, 2)

            card.addWidget(QLabel("焦距方法"), 4, 0)
            card.addWidget(auto_focus, 4, 1)
            card.addWidget(manual_focus_mode, 4, 2)
            card.addWidget(QLabel("固定焦距"), 5, 0)
            card.addLayout(focus_value_row, 5, 1, 1, 2)

            card.setColumnStretch(2, 1)
            card.setRowStretch(6, 1)

            self.camera_tabs.addTab(camera_box, f"Camera {config.slot}")
            self.rows.append((
                enabled, index, flip_h, flip_v, rotation,
                barcode, auto_focus, manual_focus_mode, manual_focus, manual_focus_value,
            ))

        layout.addWidget(self.camera_tabs, 1)
        return group

    def build_preview_group(self):
        group = QGroupBox("相機設定即時預覽")
        group.setObjectName("cameraPreviewGroup")
        layout = QVBoxLayout(group)
        self.preview_grid = QGridLayout()

        layout.addLayout(self.preview_grid, 1)
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
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            enabled, index, flip_h, flip_v, rotation, barcode, auto_focus, manual_focus_mode, manual_focus, manual_focus_value = controls
            enabled.setChecked(config.enabled)
            self.populate_camera_index_combo(index, config.device_index)
            flip_h.setChecked(config.flip_horizontal)
            flip_v.setChecked(config.flip_vertical)
            rotation.setCurrentText(str(config.rotation_degrees))
            barcode.setChecked(config.barcode_read_enabled)
            is_manual_focus = getattr(config, "focus_mode", "auto") == "manual"
            auto_focus.setChecked(not is_manual_focus)
            manual_focus_mode.setChecked(is_manual_focus)
            manual_focus.setValue(int(getattr(config, "manual_focus_value", 120)))
            manual_focus_value.setText(str(manual_focus.value()))
            manual_focus.setEnabled(manual_focus_mode.isChecked())
            manual_focus_value.setEnabled(manual_focus_mode.isChecked())
        self.apply_role_permissions()
        self.restart_preview()

    def apply_role_permissions(self):
        pass

    def _queue_preview_restart(self):
        self._preview_debounce.start()

    def restart_preview(self):
        self.stop_preview()
        self.clear_preview_grid()
        enabled_rows = self.current_enabled_camera_rows()
        if not enabled_rows:
            return

        for idx, camera in enumerate(enabled_rows):
            view = CameraView(f"Camera {camera['slot']}")
            source = VideoSource(
                f"CAMERA {camera['slot']}",
                camera["device_index"],
                False,
                camera["focus_mode"],
                camera["manual_focus_value"],
            )
            if source.has_error():
                view.set_message(source.last_error, is_error=True)
            self.preview_views.append((camera, view))
            self.preview_sources.append((camera["slot"], source))
            self.preview_grid.addWidget(view, idx // 2, idx % 2)
        self.preview_timer.start(33)

    def stop_preview(self):
        self.preview_timer.stop()
        for _, source in self.preview_sources:
            source.release()
        self.preview_sources = []

    def clear_preview_grid(self):
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.preview_views = []

    def update_camera_previews(self):
        source_by_slot = {slot: source for slot, source in self.preview_sources}
        for camera, view in self.preview_views:
            source = source_by_slot.get(camera["slot"])
            if source:
                frame = source.read()
                if frame is None:
                    view.set_message(source.last_error or "沒有相機影像。", is_error=True)
                    continue
                frame = apply_frame_transform(
                    frame,
                    flip_horizontal=camera["flip_horizontal"],
                    flip_vertical=camera["flip_vertical"],
                    rotation_degrees=camera["rotation_degrees"],
                )
                view.set_frame(frame, input_fps=source.input_fps)

    def current_enabled_camera_rows(self):
        enabled_rows = []
        for slot, controls in enumerate(self.rows, start=1):
            enabled, index, flip_h, flip_v, rotation, barcode, _, manual_focus_mode, manual_focus, _ = controls
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
                        "barcode_read_enabled": barcode.isChecked(),
                        "focus_mode": "manual" if manual_focus_mode.isChecked() else "auto",
                        "manual_focus_value": manual_focus.value(),
                    }
                )
        return enabled_rows

    def apply(self):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能修改相機與模型設定。")
            return
        self.release_external_cameras()
        enabled_names = enabled_model_names(self.state)
        if not enabled_names:
            QMessageBox.warning(self, "模型設定", "至少需要啟用一個模型，才能指定給相機。")
            return

        enabled_count = 0
        missing_model_slots = []
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            enabled, index, flip_h, flip_v, rotation, barcode, _, manual_focus_mode, manual_focus, _ = controls
            config.enabled = enabled.isChecked()
            config.device_index = int(index.currentData())
            config.flip_horizontal = flip_h.isChecked()
            config.flip_vertical = flip_v.isChecked()
            config.rotation_degrees = int(rotation.currentText())
            config.barcode_read_enabled = barcode.isChecked()
            config.focus_mode = "manual" if manual_focus_mode.isChecked() else "auto"
            config.manual_focus_value = manual_focus.value()
            enabled_count += int(config.enabled)
            if config.enabled and not camera_model_names(config):
                missing_model_slots.append(f"Camera {config.slot}")
        if enabled_count == 0:
            QMessageBox.warning(self, "相機設定", "至少需要啟用一顆檢測相機。")
            return

        if missing_model_slots:
            QMessageBox.warning(
                self,
                "Model assignment",
                "Select at least one model for: " + ", ".join(missing_model_slots),
            )
            return

        self.state.use_simulation = False
        self.state.settings_applied = True
        save_app_config(self.state)
        self.stop_preview()
        self.on_apply()

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
        self.camera_model_tables = []
        self.camera_photo_views = {}
        self.camera_photo_source = None
        self.camera_photo_timer = QTimer(self)
        self.camera_photo_timer.timeout.connect(self.update_camera_photo_preview)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        self.model_tabs = QTabWidget()
        model_list_page = QWidget()
        model_list_layout = QVBoxLayout(model_list_page)
        model_list_layout.setContentsMargins(12, 12, 12, 12)
        model_list_layout.addWidget(self.build_model_group(), 1)
        self.model_tabs.addTab(model_list_page, "模型清單")
        for camera in self.state.inspection_cameras:
            self.model_tabs.addTab(self.build_camera_model_page(camera), f"Camera {camera.slot}")
        self.model_tabs.currentChanged.connect(self.update_model_tab_preview)

        layout.addWidget(self.model_tabs, 1)

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
        photo_view = CameraView(f"Camera {camera.slot}")
        photo_layout.addWidget(photo_view, 1)
        photo_tabs.addTab(photo_page, "照片")

        layout.addWidget(model_group, 1)
        layout.addWidget(photo_tabs, 1)
        self.camera_model_tables.append((camera, table))
        self.camera_photo_views[camera.slot] = photo_view
        return page

    def refresh(self):
        ensure_model_configs(self.state)
        self.load_model_table()
        self.load_camera_model_tabs()
        self.apply_role_permissions()
        self.update_model_tab_preview(self.model_tabs.currentIndex())

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
        for _, table in self.camera_model_tables:
            table.setEnabled(can_manage_models)

    def load_model_table(self):
        self.model_table.setRowCount(0)
        for config in self.state.model_configs:
            self.add_model_row(config)

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
                table.setItem(row, 2, QTableWidgetItem(model.modality))
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
        if index <= 0:
            return
        camera_index = index - 1
        if camera_index >= len(self.state.inspection_cameras):
            return
        camera = self.state.inspection_cameras[camera_index]
        view = self.camera_photo_views.get(camera.slot)
        if not view:
            return
        source = VideoSource(
            f"CAMERA {camera.slot}",
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
        modality.addItems(MODEL_MODALITIES)
        if config.modality in MODEL_MODALITIES:
            modality.setCurrentText(config.modality)
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
        self.load_camera_model_tabs()

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
                    modality=modality_widget.currentText() if modality_widget else "vision",
                    file_path=path,
                    enabled=enabled_widget.isChecked() if enabled_widget else True,
                )
            )
        return configs

    def save(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能修改模型清單。")
            return
        self.state.model_configs = self.collect_model_configs()
        ensure_model_configs(self.state)
        self.collect_camera_model_assignments()
        self.load_camera_model_tabs()
        save_app_config(self.state)
        if self.on_saved:
            self.on_saved()

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

        header = QHBoxLayout()
        title = QLabel("GUI 顯示設定")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        layout.addLayout(header)
        layout.addWidget(self.build_display_group())
        layout.addStretch()

    def build_display_group(self):
        group = QGroupBox("GUI 顯示設定")
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

        self.display_font_size = QSpinBox()
        self.display_font_size.setRange(10, 28)
        self.display_font_size.setSingleStep(1)
        self.display_font_size.setSuffix(" px")

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
        self.state.display.font_size = self.display_font_size.value()
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
        self.display_font_size.setValue(self.state.display.font_size)
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
        self.state = state
        self.on_logout = on_logout
        self.rule_rows = []
        self.overview_rows = {}
        self.loading_rules = False
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

        layout.addLayout(header)
        layout.addWidget(self.build_decision_group(), 1)

    def build_decision_group(self):
        group = QGroupBox("PASS / NG 條件")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        global_row = QHBoxLayout()
        global_row.addWidget(QLabel("全域 PASS 信心值門檻"))
        self.global_threshold = QDoubleSpinBox()
        self.global_threshold.setRange(0.0, 1.0)
        self.global_threshold.setSingleStep(0.05)
        self.global_threshold.setDecimals(3)
        self.global_threshold.valueChanged.connect(self.queue_auto_save)
        global_row.addWidget(self.global_threshold)
        global_row.addStretch()

        self.model_tabs = QTabWidget()

        layout.addLayout(global_row)
        layout.addWidget(self.model_tabs, 1)
        return group

    def refresh(self):
        ensure_model_configs(self.state)
        self.loading_rules = True
        self.global_threshold.setValue(self.state.decision.pass_confidence_threshold)
        self.load_rule_table()
        self.loading_rules = False

    def load_rule_table(self):
        self.rule_rows = []
        self.overview_rows = {}
        self.model_tabs.clear()
        grouped_rules = {}
        all_rules = []
        for camera in self.state.inspection_cameras:
            if not camera.enabled:
                continue
            for model_name in camera_model_names(camera):
                grouped_rules.setdefault(model_name, []).append(camera.slot)
                all_rules.append((camera.slot, model_name))

        if not grouped_rules:
            empty_page = QWidget()
            empty_layout = QVBoxLayout(empty_page)
            empty_label = QLabel("目前沒有啟用的 Camera / 模型判定規則。")
            empty_label.setObjectName("mutedText")
            empty_layout.addWidget(empty_label)
            empty_layout.addStretch()
            self.model_tabs.addTab(empty_page, "未設定")
            return

        overview_page = QWidget()
        overview_layout = QVBoxLayout(overview_page)
        overview_table = self.create_overview_table()
        overview_layout.addWidget(overview_table)
        for slot, model_name in sorted(all_rules, key=lambda item: (item[0], item[1])):
            self.add_overview_row(overview_table, slot, model_name)
        self.model_tabs.addTab(overview_page, "一覽表")

        for model_name in sorted(grouped_rules):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            table = self.create_rule_table()
            page_layout.addWidget(table)
            for slot in sorted(grouped_rules[model_name]):
                self.add_rule_row(table, slot, model_name)
            self.model_tabs.addTab(page, model_name)

    def create_rule_table(self, show_model=False):
        table = QTableWidget(0, 4 if show_model else 3)
        if show_model:
            table.setHorizontalHeaderLabels(["畫面", "模型", "信心值閥值", "必須偵測標籤框數"])
        else:
            table.setHorizontalHeaderLabels(["畫面", "信心值閥值", "必須偵測標籤框數"])
        table.verticalHeader().setDefaultSectionSize(self.RULE_ROW_HEIGHT)
        table.verticalHeader().setMinimumSectionSize(self.RULE_ROW_HEIGHT)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        if show_model:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        else:
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        return table

    def create_overview_table(self):
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["畫面", "模型", "信心值閥值", "必須偵測標籤框數"])
        table.verticalHeader().setDefaultSectionSize(self.RULE_ROW_HEIGHT)
        table.verticalHeader().setMinimumSectionSize(self.RULE_ROW_HEIGHT)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return table

    def add_overview_row(self, table, slot, model_name):
        row = table.rowCount()
        table.insertRow(row)
        table.setRowHeight(row, self.RULE_ROW_HEIGHT)
        rule = self.state.decision.model_rules.get(_rule_key(slot, model_name), {})
        confidence = float(rule.get("confidence_threshold", self.state.decision.pass_confidence_threshold))
        required_count = int(rule.get("required_object_count", 1))
        table.setItem(row, 0, QTableWidgetItem(f"Camera {slot}"))
        table.setItem(row, 1, QTableWidgetItem(model_name))
        table.setItem(row, 2, QTableWidgetItem(f"{confidence:.3f}"))
        table.setItem(row, 3, QTableWidgetItem(str(required_count)))
        self.overview_rows[_rule_key(slot, model_name)] = {
            "confidence": table.item(row, 2),
            "count": table.item(row, 3),
        }

    def add_rule_row(self, table, slot, model_name, show_model=False):
        row = table.rowCount()
        table.insertRow(row)
        table.setRowHeight(row, self.RULE_ROW_HEIGHT)

        rule_key = _rule_key(slot, model_name)
        rule = self.state.decision.model_rules.get(rule_key, {})

        table.setItem(row, 0, QTableWidgetItem(f"Camera {slot}"))
        confidence_column = 1
        count_column = 2
        if show_model:
            table.setItem(row, 1, QTableWidgetItem(model_name))
            confidence_column = 2
            count_column = 3

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
        table.setCellWidget(row, count_column, count)

        self.rule_rows.append(
            {
                "slot": slot,
                "model_name": model_name,
                "confidence": confidence,
                "count": count,
            }
        )

    def queue_auto_save(self):
        if self.loading_rules:
            return
        self.sync_overview_table()
        self.autosave_timer.start(300)

    def autosave_decision_settings(self):
        self.persist_decision_settings()

    def save_decision_settings(self):
        self.persist_decision_settings()
        QMessageBox.information(self, "儲存完成", "PASS / NG 判定設定已儲存。")

    def persist_decision_settings(self):
        self.state.decision.pass_confidence_threshold = self.global_threshold.value()
        rules = {}
        for row in self.rule_rows:
            rules[_rule_key(row["slot"], row["model_name"])] = {
                "confidence_threshold": row["confidence"].value(),
                "required_object_count": int(row["count"].currentData()),
            }
        self.state.decision.model_rules = rules
        self.sync_overview_table()
        save_app_config(self.state)

    def sync_overview_table(self):
        for row in self.rule_rows:
            overview = self.overview_rows.get(_rule_key(row["slot"], row["model_name"]))
            if not overview:
                continue
            overview["confidence"].setText(f"{row['confidence'].value():.3f}")
            overview["count"].setText(str(int(row["count"].currentData())))

    def logout(self):
        if self.on_logout:
            self.on_logout()
