from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import VideoSource, apply_frame_transform, detect_camera_indexes
from valve_gui.config_store import save_app_config
from valve_gui.model_registry import enabled_model_names, ensure_model_configs
from valve_gui.models import AppState, ModelConfig
from valve_gui.paths import APP_DIR
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    PERMISSION_LABELS,
    PERMISSION_MANAGE_MODELS,
    PERMISSION_OPEN_SETTINGS,
    PERMISSION_USE_SIMULATION,
    ROLE_DEVELOPER,
    ROLE_MANAGER,
    ROLE_OPTIONS,
    has_permission,
    role_label,
)
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

        ensure_model_configs(self.state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("相機與模型配置")
        title.setObjectName("pageTitle")
        logout_button = QPushButton("登出並釋放硬體")
        logout_button.clicked.connect(self.logout)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(logout_button)

        self.tabs = QTabWidget()

        camera_tab = QWidget()
        content = QHBoxLayout(camera_tab)
        left = QVBoxLayout()
        right = QVBoxLayout()
        left.addWidget(self.build_camera_group())
        left.addWidget(self.build_model_group())
        left.addStretch()
        right.addWidget(self.build_preview_group(), 1)
        content.addLayout(left, 0)
        content.addLayout(right, 1)

        display_tab = QWidget()
        display_layout = QVBoxLayout(display_tab)
        display_layout.addWidget(self.build_display_group())
        display_apply_button = QPushButton("保存 GUI 顯示設定")
        display_apply_button.setObjectName("primaryButton")
        display_apply_button.clicked.connect(self.save_display_settings)
        display_layout.addWidget(display_apply_button)
        display_layout.addStretch()

        access_tab = QWidget()
        access_layout = QVBoxLayout(access_tab)
        access_layout.addWidget(self.build_access_group())
        access_layout.addStretch()

        self.camera_tab_index = self.tabs.addTab(camera_tab, "相機與模型")
        self.display_tab_index = self.tabs.addTab(display_tab, "GUI 顯示設定")
        self.access_tab_index = self.tabs.addTab(access_tab, "登入密鑰管理")

        action_row = QHBoxLayout()
        apply_button = QPushButton("套用並保存設定")
        apply_button.setObjectName("primaryButton")
        apply_button.clicked.connect(self.apply)
        action_row.addStretch()
        action_row.addWidget(apply_button)

        layout.addLayout(header)
        layout.addWidget(self.tabs, 1)
        layout.addLayout(action_row)

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

        hint = QLabel("全螢幕會自動使用目前螢幕；非全螢幕可自動最大化或指定寬高。")
        hint.setObjectName("mutedText")

        form.addWidget(QLabel("顯示模式"), 0, 0)
        form.addWidget(self.display_mode, 0, 1, 1, 2)
        form.addWidget(QLabel("寬度"), 1, 0)
        form.addWidget(self.display_width, 1, 1)
        form.addWidget(QLabel("高度"), 1, 2)
        form.addWidget(self.display_height, 1, 3)
        form.addWidget(hint, 2, 0, 1, 4)
        self.load_display_controls()
        return group

    def build_camera_group(self):
        group = QGroupBox("相機、方向與指定模型")
        form = QGridLayout(group)
        headers = ["啟用", "位置", "相機索引", "指定模型", "左右鏡像", "上下翻轉", "旋轉"]
        for column, text in enumerate(headers):
            form.addWidget(QLabel(text), 0, column)

        for row, config in enumerate(self.state.inspection_cameras, start=1):
            enabled = QCheckBox("使用")
            enabled.setChecked(config.enabled)
            slot = QLabel(f"Camera {config.slot}")
            index = QComboBox()
            self.populate_camera_index_combo(index, config.device_index)
            model_combo = QComboBox()
            self.populate_model_combo(model_combo, config.assigned_model_name)
            flip_h = QCheckBox("左右")
            flip_h.setChecked(config.flip_horizontal)
            flip_v = QCheckBox("上下")
            flip_v.setChecked(config.flip_vertical)
            rotation = QComboBox()
            rotation.addItems(ROTATION_OPTIONS)
            rotation.setCurrentText(str(config.rotation_degrees))

            index.currentIndexChanged.connect(self.restart_preview)
            enabled.stateChanged.connect(self.restart_preview)
            flip_h.stateChanged.connect(self.restart_preview)
            flip_v.stateChanged.connect(self.restart_preview)
            rotation.currentTextChanged.connect(self.restart_preview)
            model_combo.currentTextChanged.connect(self.restart_preview)

            form.addWidget(enabled, row, 0)
            form.addWidget(slot, row, 1)
            form.addWidget(index, row, 2)
            form.addWidget(model_combo, row, 3)
            form.addWidget(flip_h, row, 4)
            form.addWidget(flip_v, row, 5)
            form.addWidget(rotation, row, 6)
            self.rows.append((enabled, index, model_combo, flip_h, flip_v, rotation))

        self.simulation_box = QCheckBox("無相機或測試時使用模擬影像")
        self.simulation_box.setChecked(self.state.use_simulation)
        self.simulation_box.stateChanged.connect(self.restart_preview)
        search_button = QPushButton("搜尋現有相機設備")
        search_button.clicked.connect(self.search_cameras)
        self.rescan_models_button = QPushButton("重新掃描 modles 模型")
        self.rescan_models_button.clicked.connect(self.rescan_models)
        self.detected_label = QLabel("尚未搜尋相機")
        self.detected_label.setObjectName("mutedText")

        form.addWidget(search_button, 5, 0, 1, 2)
        form.addWidget(self.rescan_models_button, 5, 2, 1, 2)
        form.addWidget(self.simulation_box, 6, 0, 1, 7)
        form.addWidget(self.detected_label, 7, 0, 1, 7)
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

        actions = QHBoxLayout()
        actions.addWidget(self.add_model_button)
        actions.addWidget(self.remove_model_button)
        actions.addWidget(self.browse_model_button)
        actions.addStretch()

        layout.addWidget(self.model_table)
        layout.addLayout(actions)
        return group

    def build_access_group(self):
        self.access_group = QGroupBox("登入密鑰管理")
        layout = QGridLayout(self.access_group)
        self.password_inputs = {}
        self.permission_checks = {}

        for row, (role, label) in enumerate(ROLE_OPTIONS):
            input_box = QLineEdit()
            input_box.setEchoMode(QLineEdit.EchoMode.Password)
            input_box.setPlaceholderText(f"{label}登入密鑰")
            self.password_inputs[role] = input_box
            layout.addWidget(QLabel(label), row, 0)
            layout.addWidget(input_box, row, 1)

        permission_start_row = len(ROLE_OPTIONS) + 1
        layout.addWidget(QLabel("GUI 介面權限"), permission_start_row, 0, 1, 2)
        current_row = permission_start_row + 1
        for role, label in ROLE_OPTIONS:
            if role == ROLE_DEVELOPER:
                continue
            layout.addWidget(QLabel(label), current_row, 0)
            permission_box = QVBoxLayout()
            role_checks = {}
            for permission in CONFIGURABLE_PERMISSIONS:
                checkbox = QCheckBox(PERMISSION_LABELS.get(permission, permission))
                role_checks[permission] = checkbox
                permission_box.addWidget(checkbox)
            self.permission_checks[role] = role_checks
            layout.addLayout(permission_box, current_row, 1)
            current_row += 1

        hint = QLabel("開發者可管理所有角色密鑰；操作員密鑰可留空，代表不需要密鑰。")
        hint.setObjectName("mutedText")
        save_button = QPushButton("保存登入密鑰與權限")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save_access_passwords)

        layout.addWidget(hint, current_row, 0, 1, 2)
        layout.addWidget(save_button, current_row + 1, 0, 1, 2)
        return self.access_group

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

    def populate_model_combo(self, combo, selected_name=""):
        combo.blockSignals(True)
        combo.clear()
        names = enabled_model_names(self.state)
        combo.addItems(names)
        if selected_name and selected_name in names:
            combo.setCurrentText(selected_name)
        elif names:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def refresh_camera_model_combos(self):
        for controls in self.rows:
            model_combo = controls[2]
            selected = model_combo.currentText()
            self.populate_model_combo(model_combo, selected)

    def refresh(self):
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            return
        ensure_model_configs(self.state)
        self.load_display_controls()
        self.simulation_box.setChecked(self.state.use_simulation)
        self.refresh_camera_index_combos()
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            enabled, index, model_combo, flip_h, flip_v, rotation = controls
            enabled.setChecked(config.enabled)
            self.populate_camera_index_combo(index, config.device_index)
            self.populate_model_combo(model_combo, config.assigned_model_name)
            flip_h.setChecked(config.flip_horizontal)
            flip_v.setChecked(config.flip_vertical)
            rotation.setCurrentText(str(config.rotation_degrees))
        self.load_model_table()
        self.load_access_controls()
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
        can_manage_access = self.state.operator_role == ROLE_DEVELOPER
        self.tabs.setTabVisible(self.access_tab_index, can_manage_access)
        if not can_manage_access and self.tabs.currentIndex() == self.access_tab_index:
            self.tabs.setCurrentIndex(self.camera_tab_index)

    def load_access_controls(self):
        if not hasattr(self, "password_inputs"):
            return
        for role, input_box in self.password_inputs.items():
            input_box.setText(self.state.role_passwords.get(role, ""))
        for role, role_checks in self.permission_checks.items():
            permissions = self.state.role_permissions.get(role, set())
            for permission, checkbox in role_checks.items():
                checkbox.setChecked(permission in permissions)

    def save_access_passwords(self):
        if self.state.operator_role != ROLE_DEVELOPER:
            QMessageBox.warning(self, "權限不足", "只有開發者可以管理登入密鑰。")
            return

        updated = {
            role: input_box.text()
            for role, input_box in self.password_inputs.items()
        }
        for role in (ROLE_DEVELOPER, ROLE_MANAGER):
            if not updated.get(role):
                QMessageBox.warning(self, "密鑰不可空白", f"{role_label(role)}密鑰不可空白。")
                return

        self.state.role_passwords.update(updated)
        for role, role_checks in self.permission_checks.items():
            self.state.role_permissions[role] = {
                permission
                for permission, checkbox in role_checks.items()
                if checkbox.isChecked()
            }
        save_app_config(self.state)
        QMessageBox.information(self, "保存完成", "登入密鑰與 GUI 權限已更新。")

    def save_display_settings(self):
        self.state.display.mode = self.display_mode.currentData()
        self.state.display.width = self.display_width.value()
        self.state.display.height = self.display_height.value()
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
        self.update_display_size_controls()

    def update_display_size_controls(self):
        custom = self.display_mode.currentData() == "custom"
        self.display_width.setEnabled(custom)
        self.display_height.setEnabled(custom)

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

    def search_cameras(self):
        self.release_external_cameras()
        previous_simulation = self.simulation_box.isChecked()
        self.simulation_box.setChecked(False)
        found = detect_camera_indexes()
        self.state.detected_cameras = found
        if found:
            self.detected_label.setText("已找到相機索引：" + ", ".join(str(index) for index in found))
        else:
            self.detected_label.setText("未找到可讀取的相機，已保留目前設定。")
            self.simulation_box.setChecked(previous_simulation)
        self.refresh_camera_index_combos()
        self.restart_preview()

    def restart_preview(self):
        self.stop_preview()
        self.clear_preview_grid()
        enabled_rows = self.current_enabled_camera_rows()
        if not enabled_rows:
            self.preview_status.setText("目前沒有啟用的檢測相機。")
            return

        columns = 1 if len(enabled_rows) == 1 else 2
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
            self.preview_grid.addWidget(view, idx // columns, idx % columns)
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
                view.set_frame(frame)

    def current_enabled_camera_rows(self):
        enabled_rows = []
        for slot, controls in enumerate(self.rows, start=1):
            enabled, index, model_combo, flip_h, flip_v, rotation = controls
            if enabled.isChecked():
                enabled_rows.append(
                    {
                        "slot": slot,
                        "device_index": int(index.currentData()),
                        "model_name": model_combo.currentText(),
                        "flip_horizontal": flip_h.isChecked(),
                        "flip_vertical": flip_v.isChecked(),
                        "rotation_degrees": int(rotation.currentText()),
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
        for config, controls in zip(self.state.inspection_cameras, self.rows):
            enabled, index, model_combo, flip_h, flip_v, rotation = controls
            config.enabled = enabled.isChecked()
            config.device_index = int(index.currentData())
            config.assigned_model_name = model_combo.currentText()
            config.flip_horizontal = flip_h.isChecked()
            config.flip_vertical = flip_v.isChecked()
            config.rotation_degrees = int(rotation.currentText())
            enabled_count += int(config.enabled)
        if enabled_count == 0:
            QMessageBox.warning(self, "相機設定", "至少需要啟用一顆檢測相機。")
            return

        self.state.use_simulation = self.simulation_box.isChecked()
        self.state.display.mode = self.display_mode.currentData()
        self.state.display.width = self.display_width.value()
        self.state.display.height = self.display_height.value()
        first_enabled = next((model for model in self.state.model_configs if model.enabled), None)
        self.state.yolo_model_path = first_enabled.file_path if first_enabled else ""
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
