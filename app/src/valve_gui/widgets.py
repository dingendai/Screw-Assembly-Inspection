import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class CameraView(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("cameraCard")
        self.title = QLabel(title)
        self.title.setObjectName("cameraTitle")
        self.image = QLabel("No Signal")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(280, 180)
        self.image.setObjectName("cameraImage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.title)
        layout.addWidget(self.image, 1)

    def set_frame(self, frame):
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

    def set_message(self, message: str, is_error: bool = False):
        self.image.clear()
        self.image.setText(message)
        self.image.setObjectName("cameraError" if is_error else "cameraImage")
        self.image.style().unpolish(self.image)
        self.image.style().polish(self.image)
