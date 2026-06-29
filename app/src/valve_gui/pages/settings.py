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
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import CameraScanWorker, VideoSource, apply_frame_transform
from valve_gui.config_store import save_app_config
from valve_gui.model_registry import camera_model_names, enabled_model_names, ensure_model_configs, set_camera_model_names
from valve_gui.models import AppState, ModelConfig
from valve_gui.paths import APP_DIR
from valve_gui.permissions import (
    PERMISSION_MANAGE_MODELS,
    PERMISSION_OPEN_SETTINGS,
    PERMISSION_USE_SIMULATION,
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
        self._scan_worker = None

        ensure_model_configs(self.state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("相機與模型配置")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self.tabs = QTabWidget()

        camera_tab = QWidget()
        content = QHBoxLayout(camera_tab)
        content.setSpacing(12)
        content.addWidget(self.build_camera_group(), 1)
        content.addWidget(self.build_preview_group(), 1)
        content.setStretch(0, 1)
        content.setStretch(1, 1)

        model_tab = QWidget()
        model_layout = QVBoxLayout(model_tab)
        model_layout.addWidget(self.build_model_group())

        self.camera_tab_index = self.tabs.addTab(camera_tab, "相機設定")
        self.model_tab_index = self.tabs.addTab(model_tab, "模型清單")

        layout.addLayout(header)
        layout.addWidget(self.tabs, 1)

    def build_camera_group(self):
        group = QGroupBox("相機、方向與指定模型")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        camera_grid = QGridLayout()
        camera_grid.setSpacing(10)

        for row, config in enumerate(self.state.inspection_cameras):
            enabled = QCheckBox("啟用")
            enabled.setChecked(config.enabled)

            index = QComboBox()
            self.populate_camera_index_combo(index, config.device_index)

            model_list = QListWidget()
            model_list.setMinimumHeight(88)
            model_list.setMaximumHeight(120)
            self.populate_model_list(model_list, camera_model_names(config))

            flip_h = QCheckBox("左右翻轉")
            flip_h.setChecked(config.flip_horizontal)
            flip_v = QCheckBox("上下翻轉")
            flip_v.setChecked(config.flip_vertical)

            rotation = QComboBox()
            rotation.addItems(ROTATION_OPTIONS)
            rotation.setCurrentText(str(config.rotation_degrees))

            barcode = QCheckBox("啟用條碼辨識")
            barcode.setChecked(config.barcode_read_enabled)

            index.currentIndexChanged.connect(self._queue_preview_restart)
            enabled.stateChanged.connect(self._queue_preview_restart)
            flip_h.stateChanged.connect(self._queue_preview_restart)
            flip_v.stateChanged.connect(self._queue_preview_restart)
            rotation.currentTextChanged.connect(self._queue_preview_restart)
            model_list.itemChanged.connect(self._queue_preview_restart)

            camera_box = QGroupBox(f"Camera {config.slot}")
            card = QGridLayout(camera_box)
            card.setHorizontalSpacing(10)
            card.setVerticalSpacing(8)

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

            card.addWidget(QLabel("指定模型"), 4, 0, 1, 3)
            card.addWidget(model_list, 5, 0, 1, 3)
            card.setColumnStretch(2, 1)

            camera_grid.addWidget(camera_box, row // 2, row % 2)
            self.rows.append((enabled, index, model_list, flip_h, flip_v, rotation, barcode))

        self.simulation_box = QCheckBox("無相機或測試時使用模擬影像")
        self.simulation_box.setChecked(self.state.use_simulation)
        self.simulation_box.stateChanged.connect(self._queue_preview_restart)

        search_button = QPushButton("搜尋相機")
        search_button.clicked.connect(self.search_cameras)
        self.search_camera_button = search_button
        self.detected_label = QLabel("尚未搜尋相機")
        self.detected_label.setObjectName("mutedText")

        # 需要條碼辨識的標籤類別（逗號分隔）：偵測到這些 YOLO 類別才裁框解碼。
        self.barcode_classes_input = QLineEdit(", ".join(self.state.barcode_label_classes))
        self.barcode_classes_input.setPlaceholderText("例如：label, barcode（留空＝整張畫面解碼）")
        barcode_row = QHBoxLayout()
        barcode_row.addWidget(QLabel("需條碼辨識的標籤類別"))
        barcode_row.addWidget(self.barcode_classes_input, 1)

        action_row = QHBoxLayout()
        action_row.addWidget(search_button)
        action_row.addStretch()

        layout.addLayout(camera_grid)
        layout.addLayout(action_row)
        layout.addWidget(self.simulation_box)
        layout.addLayout(barcode_row)
        layout.addWidget(self.detected_label)
        return group

    def build_model_group(self):
        group = QGroupBox("模型清單")
        layout = QVBoxLayout(group)
        self.model_table = QTableWidget(0, 4)
        self.model_table.setHorizontalHeaderLabels(["啟用", "模型名稱", "模態", "模型檔案"])
        self.model_table.setColumnWidth(0, 54)
        self.model_table.setColumnWidth(1, 180)
        self.model_table.setColumnWidth(2, 120)
        self.model_table.setColumnWidth(3, 340)

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

    def build_preview_group(self):
        group = QGroupBox("相機設定即時預覽")
        layout = QVBoxLayout(group)
        self.preview_grid = QGridLayout()
        self.preview_status = QLabel("每個預覽格會顯示該相機目前指定的模型。")
        self.preview_status.setObjectName("mutedText")

        restart_button = QPushButton("重新整理預覽")
        restart_button.clicked.connect(self.restart_preview)
        stop_button = QPushButton("停止預覽並釋放相機")
        stop_button.clicked.connect(self.stop_preview)
        self.restart_preview_button = restart_button
        self.stop_preview_button = stop_button

        actions = QHBoxLayout()
        actions.addWidget(restart_button)
        actions.addWidget(stop_button)
        actions.addStretch()

        layout.addLayout(self.preview_grid, 1)
        layout.addWidget(self.preview_status)
        layout.addLayout(actions)
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

    def populate_model_list(self, model_list, selected_names=None):
        selected_names = set(selected_names or [])
        model_list.blockSignals(True)
        model_list.clear()
        names = enabled_model_names(self.state)
        if not selected_names and names:
            selected_names.add(names[0])
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name in selected_names else Qt.CheckState.Unchecked)
            model_list.addItem(item)
        model_list.blockSignals(False)

    def refresh_camera_model_combos(self):
        for controls in self.rows:
            model_list = controls[2]
            selected = self.checked_model_names(model_list)
            self.populate_model_list(model_list, selected)

    def checked_model_names(self, model_list):
        return [
            model_list.item(index).text()
            for index in range(model_list.count())
            if model_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def refresh(self):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            return
        ensure_model_configs(self.state)
        self.simulation_box.setChecked(self.state.use_simulation)
        self.refresh_camera_index_combos()
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            enabled, index, model_list, flip_h, flip_v, rotation, barcode = controls
            enabled.setChecked(config.enabled)
            self.populate_camera_index_combo(index, config.device_index)
            self.populate_model_list(model_list, camera_model_names(config))
            flip_h.setChecked(config.flip_horizontal)
            flip_v.setChecked(config.flip_vertical)
            rotation.setCurrentText(str(config.rotation_degrees))
            barcode.setChecked(config.barcode_read_enabled)
        self.barcode_classes_input.setText(", ".join(self.state.barcode_label_classes))
        self.load_model_table()
        self.apply_role_permissions()
        self.restart_preview()

    def apply_role_permissions(self):
        can_manage_models = has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions)
        can_use_simulation = has_permission(self.state.operator_role, PERMISSION_USE_SIMULATION, self.state.role_permissions)
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
        self.simulation_box.setEnabled(can_use_simulation)

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
        enabled.stateChanged.connect(self.sync_models_from_table)
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
            self.sync_models_from_table()

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
            self.sync_models_from_table()

    def rescan_models(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能重新掃描模型。")
            return
        ensure_model_configs(self.state)
        self.load_model_table()
        self.refresh_camera_model_combos()
        self.restart_preview()

    def sync_models_from_table(self):
        if not has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            return
        self.state.model_configs = self.collect_model_configs()
        self.refresh_camera_model_combos()

    def _queue_preview_restart(self):
        self._preview_debounce.start()

    def search_cameras(self):
        self.release_external_cameras()
        self._previous_simulation = self.simulation_box.isChecked()
        self.simulation_box.setChecked(False)
        self.search_camera_button.setEnabled(False)
        self.search_camera_button.setText("搜尋中…")
        self._scan_worker = CameraScanWorker(parent=self)
        self._scan_worker.finished.connect(self._on_camera_scan_done)
        self._scan_worker.start()

    def _on_camera_scan_done(self, found):
        self.search_camera_button.setEnabled(True)
        self.search_camera_button.setText("搜尋相機")
        self.state.detected_cameras = found
        if found:
            self.detected_label.setText("已找到相機索引：" + ", ".join(str(index) for index in found))
        else:
            self.detected_label.setText("未找到可讀取的相機，已保留目前設定。")
            self.simulation_box.setChecked(self._previous_simulation)
        self.refresh_camera_index_combos()
        self.restart_preview()

    def restart_preview(self):
        self.stop_preview()
        self.clear_preview_grid()
        enabled_rows = self.current_enabled_camera_rows()
        if not enabled_rows:
            self.preview_status.setText("目前沒有啟用的檢測相機。")
            return

        errors = []
        for idx, camera in enumerate(enabled_rows):
            view = CameraView(
                f"Camera {camera['slot']} / Device {camera['device_index']} / Model: {camera['model_name'] or '--'}"
            )
            source = VideoSource(f"CAMERA {camera['slot']}", camera["device_index"], self.simulation_box.isChecked())
            if source.has_error():
                view.set_message(source.last_error, is_error=True)
                errors.append(source.last_error)
            self.preview_views.append((camera, view))
            self.preview_sources.append((camera["slot"], source))
            self.preview_grid.addWidget(view, idx // 2, idx % 2)
        self.preview_status.setText("；".join(errors) if errors else "正在預覽目前相機配置、方向與指定模型。")
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
                    self.preview_status.setText(source.last_error or "沒有相機影像。")
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
            enabled, index, model_list, flip_h, flip_v, rotation, barcode = controls
            if enabled.isChecked():
                model_names = self.checked_model_names(model_list)
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
                    }
                )
        return enabled_rows

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

    def apply(self):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能修改相機與模型設定。")
            return
        self.release_external_cameras()
        if has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions):
            self.state.model_configs = self.collect_model_configs()
        enabled_names = enabled_model_names(self.state)
        if not enabled_names:
            QMessageBox.warning(self, "模型設定", "至少需要啟用一個模型，才能指定給相機。")
            return

        enabled_count = 0
        missing_model_slots = []
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            enabled, index, model_list, flip_h, flip_v, rotation, barcode = controls
            config.enabled = enabled.isChecked()
            config.device_index = int(index.currentData())
            selected_models = self.checked_model_names(model_list)
            set_camera_model_names(config, selected_models)
            config.flip_horizontal = flip_h.isChecked()
            config.flip_vertical = flip_v.isChecked()
            config.rotation_degrees = int(rotation.currentText())
            config.barcode_read_enabled = barcode.isChecked()
            enabled_count += int(config.enabled)
            if config.enabled and not selected_models:
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

        self.state.use_simulation = self.simulation_box.isChecked()
        self.state.barcode_label_classes = [
            name.strip() for name in self.barcode_classes_input.text().split(",") if name.strip()
        ]
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
