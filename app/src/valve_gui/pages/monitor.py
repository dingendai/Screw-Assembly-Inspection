from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
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

from valve_gui.camera import VideoSource, apply_frame_transform
from valve_gui.inference_router import InferenceRouter
from valve_gui.models import AppState, InspectionRecord
from valve_gui.permissions import role_label
from valve_gui.widgets import CameraView


class MonitorPage(QWidget):
    def __init__(self, state: AppState, add_record, on_logout=None):
        super().__init__()
        self.state = state
        self.add_record = add_record
        self.on_logout = on_logout
        self.router = InferenceRouter(state)
        self.sources = []
        self.views = []
        self.last_frames = {}
        self.last_detection_time = None
        self.continuous_detection = False
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update_frames)
        self.detection_timer = QTimer(self)
        self.detection_timer.timeout.connect(self.detect_current_frames)

        self.part_id = QLineEdit()
        self.part_id.setPlaceholderText("工件序號 / 批號")
        self.result_label = QLabel("WAITING")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setObjectName("resultWaiting")
        self.confidence_label = QLabel("Confidence: --")
        self.confidence_label.setObjectName("mutedText")
        self.camera_status_label = QLabel("相機狀態：--")
        self.camera_status_label.setObjectName("mutedText")
        self.operator_label = QLabel()
        self.operator_label.setObjectName("mutedText")
        self.model_label = QLabel()
        self.model_label.setObjectName("mutedText")
        self.continuous_box = QCheckBox("連續檢測")
        self.continuous_box.stateChanged.connect(self.toggle_continuous_detection)

        self.grid_holder = QWidget()
        self.grid = QGridLayout(self.grid_holder)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)

        start_button = QPushButton("重新啟動所有相機")
        start_button.clicked.connect(self.start)
        stop_button = QPushButton("停止相機")
        stop_button.clicked.connect(self.stop)
        inspect_button = QPushButton("單次檢測")
        inspect_button.setObjectName("primaryButton")
        inspect_button.clicked.connect(self.inspect_once)
        logout_button = QPushButton("登出並釋放硬體")
        logout_button.setObjectName("logoutButton")
        logout_button.clicked.connect(self.logout)

        side = QGroupBox("檢測狀態")
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(self.operator_label)
        side_layout.addWidget(self.model_label)
        side_layout.addWidget(QLabel("目前受測物件"))
        side_layout.addWidget(self.part_id)
        side_layout.addWidget(self.result_label)
        side_layout.addWidget(self.confidence_label)
        side_layout.addWidget(self.camera_status_label)
        side_layout.addWidget(self.continuous_box)
        side_layout.addStretch()
        side_layout.addWidget(start_button)
        side_layout.addWidget(stop_button)
        side_layout.addWidget(inspect_button)
        side_layout.addWidget(logout_button)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self.grid_holder, 1)
        layout.addWidget(side, 0)

    def refresh(self):
        self.operator_label.setText(
            f"操作者：{self.state.operator_name or '--'}"
            f" / 角色：{role_label(self.state.operator_role, self.state.role_labels)}"
            f" / 登入：{self.state.login_time or '--'}"
        )
        routes = [
            f"C{camera.slot}->{camera.assigned_model_name or '--'}"
            for camera in self.state.inspection_cameras
            if camera.enabled
        ]
        self.model_label.setText("相機模型：" + (" / ".join(routes) if routes else "--"))

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.views = []
        enabled = [config for config in self.state.inspection_cameras if config.enabled]
        columns = 1 if len(enabled) == 1 else 2
        for idx, config in enumerate(enabled):
            view = CameraView(
                f"Camera {config.slot} / Device {config.device_index} / Model: {config.assigned_model_name or '--'}"
            )
            self.views.append((config, view))
            self.grid.addWidget(view, idx // columns, idx % columns)

    def start(self):
        self.stop()
        self.refresh()
        errors = []
        for config, _ in self.views:
            source = VideoSource(f"CAMERA {config.slot}", config.device_index, self.state.use_simulation)
            if source.has_error():
                errors.append(source.last_error)
            self.sources.append((config.slot, source))
        self.camera_status_label.setText("相機狀態：" + ("；".join(errors) if errors else "正常"))
        self.frame_timer.start(33)
        if self.continuous_detection:
            self.detection_timer.start(500)

    def stop(self):
        self.frame_timer.stop()
        self.detection_timer.stop()
        for _, source in self.sources:
            source.release()
        self.sources = []

    def update_frames(self):
        source_by_slot = {slot: source for slot, source in self.sources}
        for config, view in self.views:
            source = source_by_slot.get(config.slot)
            if not source:
                continue
            frame = source.read()
            if frame is None:
                view.set_message(source.last_error or "沒有相機影像。", is_error=True)
                self.camera_status_label.setText(f"相機狀態：{source.last_error or '沒有相機影像。'}")
                continue
            frame = apply_frame_transform(
                frame,
                flip_horizontal=config.flip_horizontal,
                flip_vertical=config.flip_vertical,
                rotation_degrees=config.rotation_degrees,
            )
            self.last_frames[config.slot] = frame
            if not self.continuous_detection:
                view.set_frame(frame)

    def inspect_once(self):
        self.detect_current_frames(record=True)

    def toggle_continuous_detection(self):
        self.continuous_detection = self.continuous_box.isChecked()
        if self.continuous_detection:
            if not self.sources:
                self.start()
            self.detection_timer.start(500)
        else:
            self.detection_timer.stop()

    def detect_current_frames(self, record=False):
        if not self.state.is_logged_in:
            QMessageBox.warning(self, "尚未登入", "請先登入操作者。")
            self.continuous_box.setChecked(False)
            return
        if not self.state.settings_applied:
            QMessageBox.warning(self, "尚未套用設定", "請先在相機設定畫面套用設定。")
            self.continuous_box.setChecked(False)
            return
        if not self.views:
            self.start()
        inference = self.router.run(self.last_frames)
        self.set_result(inference.result, inference.confidence)
        self.show_annotated_frames(inference.annotated_frames)
        if record or inference.result == "NG":
            self.record_detection(inference)

    def show_annotated_frames(self, annotated_frames):
        view_by_slot = {config.slot: view for config, view in self.views}
        for slot, frame in annotated_frames.items():
            view = view_by_slot.get(slot)
            if view:
                view.set_frame(frame)

    def record_detection(self, inference):
        active = ",".join(
            f"C{config.slot}:D{config.device_index}:M{config.assigned_model_name or '--'}"
            for config, _ in self.views
        )
        record = InspectionRecord(
            timestamp=f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            operator_name=self.state.operator_name,
            operator_role=self.state.operator_role,
            result=inference.result,
            part_id=self.part_id.text().strip() or f"PART-{datetime.now():%H%M%S}",
            active_cameras=active,
            confidence=f"{inference.confidence:.3f}",
            note=inference.note,
        )
        self.add_record(record)

    def set_result(self, result, confidence):
        self.result_label.setText(result)
        self.result_label.setObjectName("resultPass" if result == "PASS" else "resultNg")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.confidence_label.setText(f"Confidence: {confidence:.3f}")

    def logout(self):
        self.stop()
        if self.on_logout:
            self.on_logout()
