from datetime import datetime

import cv2
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import VideoSource, detect_camera_indexes
from valve_gui.config_store import save_app_config
from valve_gui.models import AppState, OperatorSession
from valve_gui.paths import PHOTOS_DIR
from valve_gui.permissions import ROLE_DEVELOPER, ROLE_OPERATOR, ROLE_OPTIONS, role_label
from valve_gui.widgets import CameraView


DISPLAY_MODE_OPTIONS = [
    ("auto", "自動適應目前螢幕"),
    ("custom", "指定 GUI 畫面大小"),
    ("fullscreen", "全螢幕"),
]


class LoginPage(QWidget):
    def __init__(self, state: AppState, on_login, on_display_change=None, on_exit=None):
        super().__init__()
        self.state = state
        self.on_login = on_login
        self.on_display_change = on_display_change
        self.on_exit = on_exit
        self.sources = {}
        self.views = {}
        self.last_frames = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_previews)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("輸入操作者姓名")
        self.role_input = QComboBox()
        for role, label in ROLE_OPTIONS:
            self.role_input.addItem(label, role)
        self.role_input.currentIndexChanged.connect(self.update_login_requirements)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("輸入登入密鑰")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.camera_index = QComboBox()
        self.populate_camera_indexes(state.operator_camera_index)
        self.simulation_box = QCheckBox("使用模擬影像")
        self.simulation_box.setChecked(state.use_simulation)
        self.photo_status = QLabel("尚未拍照")
        self.photo_status.setObjectName("mutedText")

        start_button = QPushButton("重新啟動全部預覽")
        start_button.clicked.connect(self.start_preview)
        scan_button = QPushButton("搜尋可用相機")
        scan_button.clicked.connect(self.scan_cameras)
        capture_button = QPushButton("拍攝登入照片")
        capture_button.clicked.connect(self.capture_photo)
        login_button = QPushButton("登入")
        login_button.setObjectName("primaryButton")
        login_button.clicked.connect(self.submit)
        exit_button = QPushButton("結束應用程式")
        exit_button.clicked.connect(self.exit_application)

        form = QFormLayout()
        form.addRow("操作者姓名", self.name_input)
        form.addRow("登入角色", self.role_input)
        form.addRow("登入密鑰", self.password_input)
        form.addRow("登入拍照相機", self.camera_index)
        form.addRow("", self.simulation_box)

        panel = QGroupBox("登入與操作者照片")
        panel_layout = QVBoxLayout(panel)
        panel_layout.addLayout(form)
        panel_layout.addWidget(self.build_display_group())
        panel_layout.addWidget(scan_button)
        panel_layout.addWidget(start_button)
        panel_layout.addWidget(capture_button)
        panel_layout.addWidget(self.photo_status)
        panel_layout.addStretch()
        panel_layout.addWidget(login_button)
        panel_layout.addWidget(exit_button)

        preview_group = QGroupBox("可用相機畫面")
        self.preview_grid = QGridLayout(preview_group)
        self.preview_grid.setSpacing(12)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(panel, 0)
        layout.addWidget(preview_group, 1)
        self.update_login_requirements()

    def build_display_group(self):
        group = QGroupBox("GUI 顯示設定")
        layout = QGridLayout(group)

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

        apply_button = QPushButton("套用顯示設定")
        apply_button.clicked.connect(self.apply_display_settings)

        layout.addWidget(QLabel("顯示模式"), 0, 0)
        layout.addWidget(self.display_mode, 0, 1, 1, 2)
        layout.addWidget(QLabel("寬度"), 1, 0)
        layout.addWidget(self.display_width, 1, 1)
        layout.addWidget(QLabel("高度"), 1, 2)
        layout.addWidget(self.display_height, 1, 3)
        layout.addWidget(apply_button, 2, 0, 1, 4)
        self.load_display_controls()
        return group

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

    def apply_display_settings(self):
        self.state.display.mode = self.display_mode.currentData()
        self.state.display.width = self.display_width.value()
        self.state.display.height = self.display_height.value()
        save_app_config(self.state)
        if self.on_display_change:
            self.on_display_change()

    def populate_camera_indexes(self, selected_index=None):
        self.camera_index.blockSignals(True)
        self.camera_index.clear()
        indexes = sorted(set(self.state.detected_cameras + list(range(31)) + [selected_index or 0]))
        for index in indexes:
            self.camera_index.addItem(str(index), index)
        if selected_index is not None:
            match = self.camera_index.findData(selected_index)
            if match >= 0:
                self.camera_index.setCurrentIndex(match)
        self.camera_index.blockSignals(False)

    def scan_cameras(self):
        self.stop()
        self.state.detected_cameras = detect_camera_indexes()
        if not self.state.detected_cameras:
            QMessageBox.information(self, "搜尋相機", "未找到可讀取的實體相機，可勾選模擬影像測試。")
        self.populate_camera_indexes(self.state.operator_camera_index)
        self.start_preview()

    def start_preview(self):
        self.stop()
        self.state.operator_camera_index = int(self.camera_index.currentData())
        self.state.use_simulation = self.simulation_box.isChecked()

        indexes = self.preview_indexes()
        self.clear_preview_grid()
        columns = 1 if len(indexes) == 1 else 2
        for idx, camera_index in enumerate(indexes):
            view = CameraView(f"Camera Device {camera_index}")
            source = VideoSource(f"CAMERA {camera_index}", camera_index, self.state.use_simulation)
            if source.has_error():
                view.set_message(source.last_error, is_error=True)
            self.views[camera_index] = view
            self.sources[camera_index] = source
            self.preview_grid.addWidget(view, idx // columns, idx % columns)
        self.timer.start(33)

    def preview_indexes(self):
        if self.state.use_simulation:
            configured = [camera.device_index for camera in self.state.inspection_cameras if camera.enabled]
            return sorted(set(configured + [self.state.operator_camera_index]))
        if self.state.detected_cameras:
            return self.state.detected_cameras
        return [self.state.operator_camera_index]

    def update_previews(self):
        for camera_index, source in self.sources.items():
            view = self.views[camera_index]
            frame = source.read()
            if frame is None:
                view.set_message(source.last_error or "沒有相機影像。", is_error=True)
                continue
            self.last_frames[camera_index] = frame
            view.set_frame(frame)

    def capture_photo(self):
        camera_index = int(self.camera_index.currentData())
        frame = self.last_frames.get(camera_index)
        if frame is None:
            self.update_previews()
            frame = self.last_frames.get(camera_index)
        if frame is None:
            QMessageBox.warning(self, "沒有相機影像", "目前沒有可用的操作者相機影像，無法拍照。")
            return
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        name = self.name_input.text().strip() or "operator"
        safe_name = "".join(ch for ch in name if ch.isalnum() or ch in ("-", "_")) or "operator"
        path = PHOTOS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{safe_name}.jpg"
        cv2.imwrite(str(path), frame)
        self.state.operator_photo_path = str(path)
        self.photo_status.setText(f"已拍照：{path.name}")

    def selected_role(self):
        return self.role_input.currentData() or ROLE_OPERATOR

    def update_login_requirements(self):
        is_developer = self.selected_role() == ROLE_DEVELOPER
        self.name_input.setEnabled(not is_developer)
        self.camera_index.setEnabled(not is_developer)
        self.simulation_box.setEnabled(not is_developer)
        self.photo_status.setText("開發者登入不需要拍照" if is_developer else "尚未拍照")

    def validate_password(self, role):
        expected = self.state.role_passwords.get(role, "")
        if expected and self.password_input.text() != expected:
            QMessageBox.warning(self, "登入密鑰錯誤", f"{role_label(role)}密鑰不正確。")
            return False
        return True

    def submit(self):
        role = self.selected_role()
        if not self.validate_password(role):
            return
        if role == ROLE_DEVELOPER:
            self.state.operator_name = self.name_input.text().strip() or "Developer"
            self.state.operator_role = role
            self.state.operator_photo_path = ""
            self.state.login_time = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
            self.state.is_logged_in = True
            self.state.settings_applied = False
            self.state.sessions.insert(
                0,
                OperatorSession(
                    operator_name=self.state.operator_name,
                    operator_role=role,
                    login_time=self.state.login_time,
                    photo_path="",
                ),
            )
            self.password_input.clear()
            self.on_login()
            return

        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "缺少資料", "請輸入操作者姓名。")
            return
        if not self.state.operator_photo_path:
            QMessageBox.warning(self, "缺少照片", "請先拍攝操作者照片後才能登入。")
            return
        self.state.operator_name = name
        self.state.operator_role = role
        self.state.login_time = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        self.state.is_logged_in = True
        self.state.settings_applied = False
        self.state.sessions.insert(
            0,
            OperatorSession(
                operator_name=name,
                operator_role=self.state.operator_role,
                login_time=self.state.login_time,
                photo_path=self.state.operator_photo_path,
            ),
        )
        self.password_input.clear()
        self.on_login()

    def reset(self):
        self.name_input.clear()
        self.password_input.clear()
        self.role_input.setCurrentIndex(0)
        self.state.operator_photo_path = ""
        self.update_login_requirements()

    def stop(self):
        self.timer.stop()
        for source in self.sources.values():
            source.release()
        self.sources = {}

    def clear_preview_grid(self):
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.views = {}
        self.last_frames = {}

    def exit_application(self):
        self.stop()
        if self.on_exit:
            self.on_exit()
