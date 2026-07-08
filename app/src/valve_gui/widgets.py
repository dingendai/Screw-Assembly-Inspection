import time

import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout


class CameraView(QFrame):
    def __init__(self, title: str, show_info: bool = True, fill_mode: bool = False):
        super().__init__()
        self.setObjectName("cameraCard")
        self.base_title = title
        self.show_info = show_info
        self.fill_mode = fill_mode
        self.extra_info = ""
        self.input_fps = 0.0
        self.gui_fps = 0.0
        self._last_gui_frame_time = None
        self.title = QLabel(title)
        self.title.setObjectName("cameraTitle")
        self.image = QLabel("No Signal")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(280, 180)
        self.image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        aspect_mode = (
            Qt.AspectRatioMode.KeepAspectRatioByExpanding
            if self.fill_mode
            else Qt.AspectRatioMode.KeepAspectRatio
        )
        scaled = pixmap.scaled(
            self.image.size(),
            aspect_mode,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self.fill_mode:
            x = max(0, (scaled.width() - self.image.width()) // 2)
            y = max(0, (scaled.height() - self.image.height()) // 2)
            scaled = scaled.copy(x, y, self.image.width(), self.image.height())
        self.image.setPixmap(scaled)

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
        suffix = f"  {self.extra_info}" if self.extra_info else ""
        self.title.setText(f"{self.base_title}  每秒顯示影格數: {input_text}{suffix}")

    def set_extra_info(self, text: str):
        self.extra_info = text.strip()
        if self.show_info:
            self.update_fps_label()

    def set_message(self, message: str, is_error: bool = False):
        self.image.clear()
        self.image.setText(message)
        self.image.setObjectName("cameraError" if is_error else "cameraImage")
        self.image.style().unpolish(self.image)
        self.image.style().polish(self.image)
