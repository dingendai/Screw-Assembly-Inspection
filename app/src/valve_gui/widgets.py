import time

import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class CameraView(QFrame):
    def __init__(self, title: str, show_info: bool = True):
        super().__init__()
        self.setObjectName("cameraCard")
        self.base_title = title
        self.show_info = show_info
        self.input_fps = 0.0
        self.gui_fps = 0.0
        self._last_gui_frame_time = None
        self.title = QLabel(title)
        self.title.setObjectName("cameraTitle")
        self.image = QLabel("No Signal")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(280, 180)
        self.image.setObjectName("cameraImage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        if show_info:
            layout.addWidget(self.title)
        layout.addWidget(self.image, 1)

    def set_frame(self, frame, input_fps=None):
        if input_fps is not None:
            self.input_fps = input_fps
        self._mark_gui_frame_displayed()
        if self.show_info:
            self.update_fps_label()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        self.image.setPixmap(
            pixmap.scaled(
                self.image.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _mark_gui_frame_displayed(self):
        now = time.perf_counter()
        if self._last_gui_frame_time is not None:
            elapsed = now - self._last_gui_frame_time
            if elapsed > 0:
                current_fps = 1.0 / elapsed
                self.gui_fps = current_fps if self.gui_fps <= 0 else (self.gui_fps * 0.85 + current_fps * 0.15)
        self._last_gui_frame_time = now

    def update_fps_label(self):
        input_text = f"{self.input_fps:.1f}" if self.input_fps > 0 else "--"
        self.title.setText(f"{self.base_title}  FPS: {input_text}")

    def set_message(self, message: str, is_error: bool = False):
        self.image.clear()
        self.image.setText(message)
        self.image.setObjectName("cameraError" if is_error else "cameraImage")
        self.image.style().unpolish(self.image)
        self.image.style().polish(self.image)
