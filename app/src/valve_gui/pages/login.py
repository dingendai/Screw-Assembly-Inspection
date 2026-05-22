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
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import CameraScanWorker, VideoSource
from valve_gui.models import AppState, OperatorSession
from valve_gui.paths import PHOTOS_DIR
from valve_gui.permissions import ROLE_DEVELOPER, ROLE_OPERATOR, role_label, role_options
from valve_gui.utils import verify_password
from valve_gui.widgets import CameraView


class LoginPage(QWidget):
    def __init__(self, state: AppState, on_login, on_display_change=None, on_exit=None, on_release_cameras=None):
        super().__init__()
        self.state = state
        self.on_login = on_login
        self.on_display_change = on_display_change
        self.on_exit = on_exit
        self.on_release_cameras = on_release_cameras
        self.sources = {}
        self.views = {}
        self.last_frames = {}
        self.camera_visibility_checks = {}
        self.visible_camera_indexes = set()
        self._scan_worker = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_previews)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("輸入操作者姓名")
        self.role_input = QComboBox()
        self.refresh_role_options()
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
        self.camera_visibility_group = QGroupBox("相機顯示")
        self.camera_visibility_layout = QVBoxLayout(self.camera_visibility_group)

        start_button = QPushButton("重新啟動全部預覽")
        start_button.clicked.connect(self.start_preview)
        scan_button = QPushButton("搜尋可用相機")
        scan_button.clicked.connect(self.scan_cameras)
        release_button = QPushButton("強制釋放相機")
        release_button.clicked.connect(self.force_release_cameras)
        capture_button = QPushButton("拍攝登入照片")
        capture_button.clicked.connect(self.capture_photo)
        self.start_button = start_button
        self.scan_button = scan_button
        self.release_button = release_button
        self.capture_button = capture_button
        login_button = QPushButton("登入")
        login_button.setObjectName("primaryButton")
        login_button.clicked.connect(self.submit)
        exit_button = QPushButton("結束應用程式")
        exit_button.clicked.connect(self.exit_application)
        self.login_button = login_button
        self.exit_button = exit_button

        form = QFormLayout()
        self.form = form
        form.addRow("操作者姓名", self.name_input)
        form.addRow("登入角色", self.role_input)
        form.addRow("登入密鑰", self.password_input)
        form.addRow("登入拍照相機", self.camera_index)
        form.addRow("", self.simulation_box)

        panel = QGroupBox("登入與操作者照片")
        panel_layout = QVBoxLayout(panel)
        panel_layout.addLayout(form)
        panel_layout.addWidget(scan_button)
        panel_layout.addWidget(start_button)
        panel_layout.addWidget(release_button)
        panel_layout.addWidget(self.camera_visibility_group)
        panel_layout.addWidget(capture_button)
        panel_layout.addWidget(self.photo_status)
        panel_layout.addStretch()
        panel_layout.addWidget(login_button)

        preview_group = QGroupBox("可用相機畫面")
        self.preview_group = preview_group
        self.preview_grid = QGridLayout(preview_group)
        self.preview_grid.setSpacing(12)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(panel, 0)
        layout.addWidget(preview_group, 1)
        self.update_login_requirements()

    def refresh_role_options(self):
        current_role = self.role_input.currentData() if hasattr(self, "role_input") else None
        self.role_input.blockSignals(True)
        self.role_input.clear()
        for role, label in role_options(self.state.role_labels):
            self.role_input.addItem(label, role)
        if current_role:
            match = self.role_input.findData(current_role)
            if match >= 0:
                self.role_input.setCurrentIndex(match)
        self.role_input.blockSignals(False)

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
        self.scan_button.setEnabled(False)
        self.scan_button.setText("搜尋中…")
        self._scan_worker = CameraScanWorker(parent=self)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_scan_done(self, found):
        self.scan_button.setEnabled(True)
        self.scan_button.setText("搜尋可用相機")
        self.state.detected_cameras = found
        if not found:
            QMessageBox.information(self, "搜尋相機", "未找到可讀取的實體相機，可勾選模擬影像測試。")
        self.populate_camera_indexes(self.state.operator_camera_index)
        self.start_preview()

    def start_preview(self):
        self.stop()
        self.state.operator_camera_index = int(self.camera_index.currentData())
        self.state.use_simulation = self.simulation_box.isChecked()

        indexes = self.preview_indexes()
        self.clear_preview_grid()
        self.build_camera_visibility_controls(indexes)
        for camera_index in indexes:
            view = CameraView(f"Camera Device {camera_index}")
            source = VideoSource(f"CAMERA {camera_index}", camera_index, self.state.use_simulation)
            if source.has_error():
                view.set_message(source.last_error, is_error=True)
            self.views[camera_index] = view
            self.sources[camera_index] = source
        self.arrange_visible_previews()
        self.timer.start(33)

    def build_camera_visibility_controls(self, indexes):
        while self.camera_visibility_layout.count():
            item = self.camera_visibility_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.camera_visibility_checks = {}

        if not self.visible_camera_indexes:
            self.visible_camera_indexes = set(indexes)
        else:
            self.visible_camera_indexes = {index for index in self.visible_camera_indexes if index in indexes}
            if not self.visible_camera_indexes:
                self.visible_camera_indexes = set(indexes)

        for camera_index in indexes:
            checkbox = QCheckBox(f"Camera Device {camera_index}")
            checkbox.setChecked(camera_index in self.visible_camera_indexes)
            checkbox.stateChanged.connect(self.update_camera_visibility)
            self.camera_visibility_layout.addWidget(checkbox)
            self.camera_visibility_checks[camera_index] = checkbox

    def update_camera_visibility(self):
        self.visible_camera_indexes = {
            camera_index
            for camera_index, checkbox in self.camera_visibility_checks.items()
            if checkbox.isChecked()
        }
        self.arrange_visible_previews()

    def arrange_visible_previews(self):
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        visible_indexes = [index for index in sorted(self.views) if index in self.visible_camera_indexes]
        columns = 1 if len(visible_indexes) <= 1 else 2
        for idx, camera_index in enumerate(visible_indexes):
            view = self.views[camera_index]
            self.preview_grid.addWidget(view, idx // columns, idx % columns)
            view.show()

        for camera_index, view in self.views.items():
            view.setVisible(camera_index in self.visible_camera_indexes)

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
            view.set_frame(frame, input_fps=source.input_fps)

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
        role = self.selected_role()
        is_developer = role == ROLE_DEVELOPER
        needs_name = not is_developer
        needs_password = bool(self.state.role_passwords.get(role, ""))
        needs_photo = not is_developer

        self.set_form_row_visible(self.name_input, needs_name)
        self.set_form_row_visible(self.password_input, needs_password)
        self.set_form_row_visible(self.camera_index, needs_photo)
        self.set_form_row_visible(self.simulation_box, needs_photo)

        self.scan_button.setVisible(needs_photo)
        self.start_button.setVisible(needs_photo)
        self.release_button.setVisible(needs_photo)
        self.capture_button.setVisible(needs_photo)
        self.photo_status.setVisible(needs_photo)
        self.preview_group.setVisible(needs_photo)
        self.camera_visibility_group.setVisible(needs_photo)

        if not needs_name:
            self.name_input.clear()
        if not needs_password:
            self.password_input.clear()
        if is_developer:
            self.stop()
            self.state.operator_photo_path = ""
        else:
            self.photo_status.setText("尚未拍照")

    def set_form_row_visible(self, field, visible):
        label = self.form.labelForField(field)
        if label:
            label.setVisible(visible)
        field.setVisible(visible)

    def validate_password(self, role):
        stored = self.state.role_passwords.get(role, "")
        if stored and not verify_password(self.password_input.text(), stored):
            QMessageBox.warning(self, "登入密鑰錯誤", f"{role_label(role, self.state.role_labels)}密鑰不正確。")
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
        self.name_input.setReadOnly(False)
        self.password_input.clear()
        self.refresh_role_options()
        self.role_input.setEnabled(True)
        self.role_input.setCurrentIndex(0)
        self.state.operator_photo_path = ""
        self.update_login_requirements()

    def stop(self):
        self.timer.stop()
        for source in self.sources.values():
            source.release()
        self.sources = {}

    def force_release_cameras(self):
        self.stop()
        self.clear_preview_grid()
        if self.on_release_cameras:
            self.on_release_cameras()
        self.photo_status.setText("已強制釋放相機，需重新啟動預覽後才能拍照。")

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
