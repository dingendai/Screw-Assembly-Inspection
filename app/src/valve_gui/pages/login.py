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

from valve_gui.camera import VideoSource, detect_camera_indexes
from valve_gui.models import AppState, OperatorSession
from valve_gui.paths import PHOTOS_DIR
from valve_gui.widgets import CameraView


class LoginPage(QWidget):
    def __init__(self, state: AppState, on_login, on_exit=None):
        super().__init__()
        self.state = state
        self.on_login = on_login
        self.on_exit = on_exit
        self.sources = {}
        self.views = {}
        self.last_frames = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_previews)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("輸入操作者姓名")
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
        form.addRow("登入拍照相機", self.camera_index)
        form.addRow("", self.simulation_box)

        panel = QGroupBox("登入與操作者照片")
        panel_layout = QVBoxLayout(panel)
        panel_layout.addLayout(form)
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

    def submit(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "缺少資料", "請輸入操作者姓名。")
            return
        if not self.state.operator_photo_path:
            QMessageBox.warning(self, "缺少照片", "請先拍攝操作者照片後才能登入。")
            return
        self.state.operator_name = name
        self.state.login_time = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        self.state.is_logged_in = True
        self.state.settings_applied = False
        self.state.sessions.insert(
            0,
            OperatorSession(
                operator_name=name,
                login_time=self.state.login_time,
                photo_path=self.state.operator_photo_path,
            ),
        )
        self.on_login()

    def reset(self):
        self.name_input.clear()
        self.state.operator_photo_path = ""
        self.photo_status.setText("尚未拍照")

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
