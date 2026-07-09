import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.camera import VideoSource, apply_frame_transform, normalised_region_to_pixels
from valve_gui.config_store import save_app_config
from valve_gui.inference_router import InferenceRouter
from valve_gui.lock_geometry import draw_lock_geometry_config_overlay
from valve_gui.model_registry import format_camera_model_names
from valve_gui.models import AppState, InspectionRecord, InspectionTransaction
from valve_gui.utils import hex_to_bgr, process_barcode_text
from valve_gui.widgets import CameraView


MAX_GUI_FRAME_DIMENSION = 960
SINGLE_INSPECTION_COUNTDOWN_SEC = 2


class _DetectionWorker(QThread):
    finished = pyqtSignal(object)
    errored = pyqtSignal(str)

    def __init__(self, router, frames, parent=None):
        super().__init__(parent)
        self.router = router
        self.frames = frames

    def run(self):
        try:
            result = self.router.run(self.frames)
            self.finished.emit(result)
        except Exception as exc:
            self.errored.emit(str(exc))


class MonitorPage(QWidget):
    def __init__(self, state: AppState, add_record, on_logout=None):
        super().__init__()
        self.state = state
        self.add_record = add_record
        self.on_logout = on_logout
        self.router = InferenceRouter(state)
        self.sources = []
        self.views = []
        self.single_views = {}
        self.last_frames = {}
        self.latest_annotated_frames = {}
        self.latest_yolo_annotated_frames = {}
        self.latest_geometry_annotated_frames = {}
        self.continuous_detection = False
        self.detection_executor = ThreadPoolExecutor(max_workers=1)
        self.pending_detection_future = None
        self._single_worker = None
        self.current_transaction: InspectionTransaction | None = None
        self._single_countdown_remaining = 0
        self._last_record_time: float = 0.0
        self._workflow_last_barcode = ""
        self._workflow_confirm_dialog_open = False
        self._source_by_slot: dict = {}
        self._config_by_slot: dict = {}
        self._view_by_slot: dict = {}
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update_frames)
        self.detection_timer = QTimer(self)
        self.detection_timer.timeout.connect(self.detect_current_frames)
        self.result_timer = QTimer(self)
        self.result_timer.timeout.connect(self.apply_pending_detection_result)
        self.single_countdown_timer = QTimer(self)
        self.single_countdown_timer.timeout.connect(self._advance_single_countdown)
        self.part_id_normalize_timer = QTimer(self)
        self.part_id_normalize_timer.setSingleShot(True)
        self.part_id_normalize_timer.setInterval(180)
        self.part_id_normalize_timer.timeout.connect(self.normalize_part_id_display)

        self.part_id = QLineEdit()
        self.part_id.setPlaceholderText("工件序號 / 批號")
        self.part_id.textChanged.connect(self.queue_part_id_normalization)
        self.processed_part_id = QLineEdit()
        self.processed_part_id.setPlaceholderText("S7 處理後條碼")
        self.processed_part_id.setReadOnly(True)
        self.result_label = QLabel("WAITING")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setObjectName("resultWaiting")
        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setObjectName("resultWaiting")
        self.reason_cards = {}
        self.reason_list = QWidget()
        self.reason_layout = QVBoxLayout(self.reason_list)
        self.reason_layout.setContentsMargins(0, 0, 0, 0)
        self.reason_layout.setSpacing(8)
        self.roi_section = QGroupBox("ROI 物件確認狀態")
        self.roi_section_layout = QVBoxLayout(self.roi_section)
        self.roi_section_layout.setContentsMargins(8, 8, 8, 8)
        self.roi_section_layout.setSpacing(4)
        self.roi_section.setVisible(False)
        self.region_overlay_box = QCheckBox("顯示指定範圍")
        self.region_overlay_box.stateChanged.connect(self.toggle_region_overlay)
        self.yolo_overlay_box = QCheckBox("顯示影像辨識框選")
        self.yolo_overlay_box.stateChanged.connect(self.toggle_yolo_overlay)
        self.geometry_overlay_box = QCheckBox("顯示幾何框選")
        self.geometry_overlay_box.stateChanged.connect(self.toggle_geometry_overlay)
        self.continuous_button = QPushButton("開始檢測")
        self.continuous_button.setCheckable(True)
        self.continuous_button.setObjectName("continuousButton")
        self.continuous_button.toggled.connect(self.toggle_continuous_detection)

        self.grid_holder = QWidget()
        self.grid = QGridLayout(self.grid_holder)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.monitor_tabs = QTabWidget()
        self.monitor_tabs.addTab(self.grid_holder, "總覽")

        start_button = QPushButton("重新啟動所有相機")
        start_button.clicked.connect(self.start)
        stop_button = QPushButton("停止相機")
        stop_button.clicked.connect(lambda: self.stop())
        self.start_button = start_button
        self.stop_button = stop_button
        self.inspect_button = QPushButton("單次檢測")
        self._inspect_button_default_text = self.inspect_button.text()
        self.inspect_button.clicked.connect(self.inspect_once)
        self.inspect_button.setVisible(False)

        side = QGroupBox("檢測狀態")
        side_layout = QVBoxLayout(side)
        result_row = QHBoxLayout()
        result_row.setSpacing(8)
        result_row.addWidget(self.result_label, 8)
        result_row.addWidget(self.countdown_label, 2)
        side_layout.addLayout(result_row)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.continuous_button)
        action_row.addWidget(start_button)
        action_row.addWidget(stop_button)
        side_layout.addLayout(action_row)
        overlay_row = QHBoxLayout()
        overlay_row.setSpacing(8)
        overlay_row.addWidget(self.region_overlay_box)
        overlay_row.addWidget(self.yolo_overlay_box)
        overlay_row.addWidget(self.geometry_overlay_box)
        side_layout.addLayout(overlay_row)
        side_layout.addWidget(QLabel("目前受測物件"))
        barcode_row = QHBoxLayout()
        barcode_row.setSpacing(8)
        barcode_row.addWidget(self.part_id, 1)
        barcode_row.addWidget(self.processed_part_id, 1)
        side_layout.addLayout(barcode_row)
        side_layout.addWidget(QLabel("相機檢測狀態"))
        side_layout.addWidget(self.reason_list)
        side_layout.addWidget(self.roi_section)
        side_layout.addStretch()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self.monitor_tabs, 3)
        layout.addWidget(side, 7)

    def refresh(self):
        self.normalize_part_id_display()
        self.region_overlay_box.blockSignals(True)
        self.region_overlay_box.setChecked(self.state.region_overlay.show_on_monitor)
        self.region_overlay_box.blockSignals(False)
        self.yolo_overlay_box.blockSignals(True)
        self.yolo_overlay_box.setChecked(getattr(self.state.region_overlay, "show_yolo_on_monitor", True))
        self.yolo_overlay_box.blockSignals(False)
        self.geometry_overlay_box.blockSignals(True)
        self.geometry_overlay_box.setChecked(getattr(self.state.region_overlay, "show_geometry_on_monitor", True))
        self.geometry_overlay_box.blockSignals(False)
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.monitor_tabs.clear()
        self.monitor_tabs.addTab(self.grid_holder, "總覽")
        self.views = []
        self.single_views = {}
        enabled = [config for config in self.state.inspection_cameras if config.enabled]
        columns = 1 if len(enabled) == 1 else 2
        for idx, config in enumerate(enabled):
            view = CameraView(f"相機 {config.slot}")
            single_view = CameraView(f"相機 {config.slot}")
            single_page = QWidget()
            single_layout = QVBoxLayout(single_page)
            single_layout.setContentsMargins(12, 12, 12, 12)
            single_layout.addWidget(single_view, 1)
            self.views.append((config, view))
            self.single_views[config.slot] = single_view
            self.grid.addWidget(view, idx // columns, idx % columns)
            self.monitor_tabs.addTab(single_page, f"相機 {config.slot}")

    def start(self):
        continuous_requested = self.continuous_detection
        self.stop(reset_continuous=False)
        self.detection_executor = ThreadPoolExecutor(max_workers=1)
        self.continuous_detection = continuous_requested
        self.refresh()
        for config, _ in self.views:
            source = VideoSource(
                f"相機 {config.slot}",
                config.device_index,
                self.state.use_simulation,
                getattr(config, "focus_mode", "auto"),
                getattr(config, "manual_focus_value", 120),
            )
            self.sources.append((config.slot, source))
        self._source_by_slot = {slot: source for slot, source in self.sources}
        self._config_by_slot = {config.slot: config for config, _ in self.views}
        self._view_by_slot = {config.slot: view for config, view in self.views}
        self.frame_timer.start(33)
        if self.continuous_detection:
            workflow_mode = getattr(self.state.inspection_workflow, "mode", "delay")
            if workflow_mode == "instant":
                self.detection_timer.start(500)

    def stop(self, reset_continuous=True):
        was_counting_down = self.single_countdown_timer.isActive() or (
            self.current_transaction is not None
            and self.current_transaction.state == "counting_down"
        )
        self.frame_timer.stop()
        self.detection_timer.stop()
        self.result_timer.stop()
        self.single_countdown_timer.stop()
        self.part_id_normalize_timer.stop()
        self._single_countdown_remaining = 0
        self._workflow_confirm_dialog_open = False
        self.pending_detection_future = None
        if self.current_transaction and self.current_transaction.state == "counting_down":
            self.current_transaction.state = "error"
            self.current_transaction.error_message = "camera stopped"
            self.current_transaction = None
        if was_counting_down:
            self.set_status("WAITING")
            self.set_countdown_text("")
            self._restore_inspect_button()
        self.detection_executor.shutdown(wait=False)
        self.latest_annotated_frames = {}
        self.latest_yolo_annotated_frames = {}
        self.latest_geometry_annotated_frames = {}
        self._last_record_time = 0.0
        if reset_continuous:
            self.continuous_button.blockSignals(True)
            self.continuous_button.setChecked(False)
            self.continuous_button.blockSignals(False)
            self.continuous_detection = False
            self.update_detection_controls()
        for _, source in self.sources:
            source.release()
        self.sources = []
        self._source_by_slot = {}
        self._config_by_slot = {}
        self._view_by_slot = {}

    def update_frames(self):
        for config, view in self.views:
            source = self._source_by_slot.get(config.slot)
            if not source:
                continue
            frame = source.read()
            if frame is None:
                view.set_message(source.last_error or "沒有相機影像。", is_error=True)
                single_view = self.single_views.get(config.slot)
                if single_view:
                    single_view.set_message(source.last_error or "沒有相機影像。", is_error=True)
                continue
            model_frame = apply_frame_transform(
                frame,
                flip_horizontal=config.flip_horizontal,
                flip_vertical=config.flip_vertical,
                rotation_degrees=config.rotation_degrees,
            )
            # Model input keeps the camera-provided resolution. GUI compression
            # happens only after inference/overlay rendering.
            self.last_frames[config.slot] = model_frame
            display_frame = self.compose_detection_display_frame(config.slot, model_frame) if self.continuous_detection else None
            self.set_monitor_frame(
                config,
                self.display_frame_for(config, display_frame if display_frame is not None else model_frame),
                input_fps=source.input_fps,
            )

    def set_monitor_frame(self, config, frame, input_fps=None):
        overview_view = self._view_by_slot.get(config.slot)
        if overview_view:
            overview_view.set_frame(frame, input_fps=input_fps)
        single_view = self.single_views.get(config.slot)
        if single_view:
            single_view.set_frame(frame, input_fps=input_fps)

    def display_frame_for(self, config, frame):
        return self.compress_frame_for_gui(self.frame_with_region_overlay(config, frame))

    def compress_frame_for_gui(self, frame):
        height, width = frame.shape[:2]
        longest_edge = max(width, height)
        if longest_edge <= MAX_GUI_FRAME_DIMENSION:
            return frame
        scale = MAX_GUI_FRAME_DIMENSION / longest_edge
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)

    def queue_part_id_normalization(self):
        self.part_id_normalize_timer.start()

    def normalize_part_id_display(self):
        raw_text = self.part_id.text().strip()
        if not raw_text:
            self.processed_part_id.clear()
            self._workflow_last_barcode = ""
            return
        processed_text = process_barcode_text(raw_text, self.state.barcode_processing) or raw_text
        self.processed_part_id.setText(processed_text)
        self.maybe_start_workflow(processed_text)

    def clear_barcode_fields(self):
        self.part_id_normalize_timer.stop()
        self.part_id.blockSignals(True)
        self.part_id.clear()
        self.part_id.blockSignals(False)
        self.processed_part_id.clear()
        self._workflow_last_barcode = ""

    def maybe_start_workflow(self, processed_text):
        if not self.continuous_detection or not processed_text:
            return
        if self.current_transaction and self.current_transaction.state in {"counting_down", "capturing", "inferencing"}:
            return
        if processed_text == self._workflow_last_barcode:
            return
        self._workflow_last_barcode = processed_text
        workflow_mode = getattr(self.state.inspection_workflow, "mode", "delay")
        if workflow_mode == "instant":
            return
        if workflow_mode == "confirm":
            self.prompt_confirm_detection()
            return
        self.begin_workflow_countdown(max(1, int(getattr(self.state.inspection_workflow, "delay_seconds", 3))))

    def prompt_confirm_detection(self):
        if self._workflow_confirm_dialog_open:
            return
        self._workflow_confirm_dialog_open = True
        try:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("\u78ba\u8a8d\u6aa2\u6e2c")
            dialog.setText(
                "\u689d\u78bc\u5df2\u5c31\u7dd2\uff0c\u8acb\u653e\u597d\u88ab\u6aa2\u6e2c\u7269\u4ef6\u5f8c\u6309\u4e0b"
                "\u78ba\u8a8d\u6aa2\u6e2c\u3002"
            )
            confirm_button = dialog.addButton(
                "\u78ba\u8a8d\u6aa2\u6e2c", QMessageBox.ButtonRole.AcceptRole
            )
            cancel_button = dialog.addButton("\u53d6\u6d88", QMessageBox.ButtonRole.RejectRole)
            confirm_button.setAutoDefault(False)
            confirm_button.setDefault(False)
            cancel_button.setAutoDefault(False)
            cancel_button.setDefault(False)
            dialog.setDefaultButton(cancel_button)
            dialog.exec()
            if dialog.clickedButton() == confirm_button and self.continuous_detection:
                self.begin_workflow_capture()
            else:
                self._workflow_last_barcode = ""
        finally:
            self._workflow_confirm_dialog_open = False

    def begin_workflow_countdown(self, seconds):
        self.current_transaction = self._create_single_transaction()
        self.current_transaction.state = "counting_down"
        self._single_countdown_remaining = max(1, int(seconds))
        self.set_status("WAITING")
        self._show_single_countdown()
        self.single_countdown_timer.start(1000)

    def begin_workflow_capture(self):
        self.current_transaction = self._create_single_transaction()
        self.set_countdown_text("")
        self._capture_single_transaction_frames()

    def set_countdown_text(self, text):
        self.countdown_label.setText(text)

    def toggle_region_overlay(self):
        self.state.region_overlay.show_on_monitor = self.region_overlay_box.isChecked()
        save_app_config(self.state)

    def toggle_yolo_overlay(self):
        self.state.region_overlay.show_yolo_on_monitor = self.yolo_overlay_box.isChecked()
        save_app_config(self.state)

    def toggle_geometry_overlay(self):
        self.state.region_overlay.show_geometry_on_monitor = self.geometry_overlay_box.isChecked()
        save_app_config(self.state)

    def compose_detection_display_frame(self, slot, fallback_frame):
        show_yolo = getattr(self.state.region_overlay, "show_yolo_on_monitor", True)
        show_geometry = getattr(self.state.region_overlay, "show_geometry_on_monitor", True)
        if show_yolo and show_geometry:
            return self.latest_annotated_frames.get(slot, fallback_frame)
        if show_yolo:
            return self.latest_yolo_annotated_frames.get(slot, fallback_frame)
        if show_geometry:
            return self.latest_geometry_annotated_frames.get(slot, fallback_frame)
        return fallback_frame

    def frame_with_region_overlay(self, config, frame):
        annotated = frame
        if (
            not self.continuous_detection
            and getattr(self.state.region_overlay, "show_geometry_on_monitor", True)
            and
            getattr(config, "lock_geometry_enabled", False)
            and getattr(config, "lock_geometry_regions", None)
        ):
            annotated = draw_lock_geometry_config_overlay(annotated.copy(), config.lock_geometry_regions)
        if not self.state.region_overlay.show_on_monitor:
            return annotated
        if not getattr(config, "region_detection_enabled", False):
            return annotated
        if not config.detection_regions and not config.exclusion_regions:
            return annotated
        annotated = annotated.copy()
        height, width = annotated.shape[:2]
        self.draw_region_list(
            annotated,
            config.detection_regions,
            hex_to_bgr(self.state.region_overlay.detection_color),
            "ROI",
            width,
            height,
        )
        self.draw_region_list(
            annotated,
            config.exclusion_regions,
            hex_to_bgr(self.state.region_overlay.exclusion_color),
            "EX",
            width,
            height,
        )
        return annotated

    def draw_region_list(self, frame, regions, color, label, width, height):
        for index, region in enumerate(regions, start=1):
            x1, y1, x2, y2 = normalised_region_to_pixels(region, width, height)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
            cv2.putText(
                frame,
                self.format_region_label(label, index, region),
                (x1 + 3, max(10, y1 + 11)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.28,
                color,
                1,
            )

    def format_region_label(self, label, index, region):
        roi_id = region.get("roi_id")
        if roi_id is not None:
            return f"#{roi_id}"
        return f"{label} {index}"

    def set_status(self, text):
        self.result_label.setText(text)
        self.result_label.setObjectName("resultWaiting")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        if text in {"PASS", "NG", "ERROR", "WAITING"}:
            self.set_countdown_text("")

    def inspect_once(self):
        if self.single_countdown_timer.isActive():
            self._cancel_single_countdown()
            return
        if self._single_worker and self._single_worker.isRunning():
            return
        if self.current_transaction and self.current_transaction.state in {"capturing", "inferencing"}:
            return
        if not self.state.is_logged_in:
            QMessageBox.warning(self, "尚未登入", "請先登入操作者。")
            return
        if not self.state.settings_applied:
            QMessageBox.warning(self, "尚未套用設定", "請先在相機設定畫面套用設定。")
            return
        if not self.views:
            self.start()
        if not self.views:
            QMessageBox.warning(self, "Inspection unavailable", "No active inspection cameras.")
            return
        self._begin_single_countdown()

    def _begin_single_countdown(self):
        self.current_transaction = self._create_single_transaction()
        self.current_transaction.state = "counting_down"
        self._single_countdown_remaining = SINGLE_INSPECTION_COUNTDOWN_SEC
        self.inspect_button.setEnabled(True)
        self.inspect_button.setText("取消倒數")
        self.continuous_button.setEnabled(False)
        self.inspect_button.setObjectName("activeDetectionButton")
        self.inspect_button.style().unpolish(self.inspect_button)
        self.inspect_button.style().polish(self.inspect_button)
        self._show_single_countdown()
        self.single_countdown_timer.start(1000)

    def _create_single_transaction(self):
        manual_part_id = self.part_id.text().strip()
        processed_part_id = process_barcode_text(manual_part_id, self.state.barcode_processing) or manual_part_id
        return InspectionTransaction(
            transaction_id=f"TX-{datetime.now():%Y%m%d%H%M%S%f}",
            state="idle",
            operator_name=self.state.operator_name,
            operator_role=self.state.operator_role,
            session_id=self.state.current_work_session_id,
            primary_barcode=processed_part_id,
            barcode_source="manual" if manual_part_id else "",
            active_cameras=self._active_camera_summary(),
        )

    def _show_single_countdown(self):
        self.set_countdown_text(str(self._single_countdown_remaining))

    def _advance_single_countdown(self):
        self._single_countdown_remaining -= 1
        if self._single_countdown_remaining > 0:
            self._show_single_countdown()
            return
        self.single_countdown_timer.stop()
        self._capture_single_transaction_frames()

    def _cancel_single_countdown(self):
        self.single_countdown_timer.stop()
        if self.current_transaction:
            self.current_transaction.state = "error"
            self.current_transaction.error_message = "cancelled"
        self.current_transaction = None
        self._single_countdown_remaining = 0
        self.set_status("WAITING")
        self.set_countdown_text("")
        self._workflow_last_barcode = ""
        self._restore_inspect_button()

    def _capture_single_transaction_frames(self):
        transaction = self.current_transaction
        if not transaction:
            self._restore_inspect_button()
            return
        transaction.state = "capturing"
        transaction.captured_at = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        self.set_status("拍照中")
        frames, missing_slots = self._copy_active_frames()
        if missing_slots:
            missing_text = ", ".join(f"C{slot}" for slot in missing_slots)
            transaction.state = "error"
            transaction.error_message = f"Missing camera frames: {missing_text}"
            self.set_status("ERROR")
            self.set_countdown_text("")
            QMessageBox.warning(self, "Inspection frame unavailable", transaction.error_message)
            self.current_transaction = None
            self.clear_barcode_fields()
            self._restore_inspect_button()
            return
        transaction.raw_frames = frames
        transaction.state = "inferencing"
        self.set_countdown_text("")
        self.set_status("檢測中")
        self.inspect_button.setText("檢測中")
        self.inspect_button.setEnabled(False)
        self._single_worker = _DetectionWorker(self.router, transaction.raw_frames, self)
        self._single_worker.finished.connect(self._on_single_detection_done)
        self._single_worker.errored.connect(self._on_single_detection_error)
        self._single_worker.start()

    def _copy_active_frames(self):
        frames = {}
        missing_slots = []
        for config, _ in self.views:
            frame = self.last_frames.get(config.slot)
            if frame is None:
                missing_slots.append(config.slot)
                continue
            frames[config.slot] = frame.copy()
        return frames, missing_slots

    def _active_camera_summary(self):
        return ",".join(
            f"C{config.slot}:D{config.device_index}:M{format_camera_model_names(config)}"
            for config, _ in self.views
        )

    def _on_single_detection_done(self, inference):
        if self.current_transaction:
            self.current_transaction.state = "reviewing"
            self.current_transaction.inference_result = inference
        self.apply_detection_result(inference, record=True)
        if self.current_transaction:
            self.current_transaction.state = "completed"
            self.current_transaction = None
        self.clear_barcode_fields()
        self.set_countdown_text("")
        self._restore_inspect_button()

    def _on_single_detection_error(self, error_msg):
        if self.current_transaction:
            self.current_transaction.state = "error"
            self.current_transaction.error_message = error_msg
            self.current_transaction = None
        self.set_result("NG", 0.0)
        self.set_countdown_text("")
        self.clear_barcode_fields()
        self.set_reason_cards({0: {"result": "NG", "confidence": 0.0, "reasons": [f"檢測錯誤：{error_msg}"]}})
        self._restore_inspect_button()

    def _restore_inspect_button(self):
        self.inspect_button.setObjectName("primaryButton")
        self.inspect_button.style().unpolish(self.inspect_button)
        self.inspect_button.style().polish(self.inspect_button)
        self.inspect_button.setText(self._inspect_button_default_text)
        self.inspect_button.setEnabled(True)
        if not self.continuous_detection:
            self.continuous_button.setEnabled(True)

    def toggle_continuous_detection(self, checked):
        self.continuous_detection = checked
        self.update_detection_controls()
        if self.continuous_detection:
            if not self.sources:
                self.start()
            self.latest_annotated_frames = {}
            self.latest_yolo_annotated_frames = {}
            self.latest_geometry_annotated_frames = {}
            workflow_mode = getattr(self.state.inspection_workflow, "mode", "delay")
            if workflow_mode == "instant":
                self.detection_timer.start(500)
        else:
            self.detection_timer.stop()
            self.result_timer.stop()
            self.pending_detection_future = None
            self.latest_annotated_frames = {}
            self.latest_yolo_annotated_frames = {}
            self.latest_geometry_annotated_frames = {}
            self._workflow_last_barcode = ""
            self.set_countdown_text("")

    def update_detection_controls(self):
        self.continuous_button.setEnabled(True)
        self.continuous_button.setText("停止連續檢測" if self.continuous_detection else "開始檢測")

    def detect_current_frames(self):
        if not self.state.is_logged_in:
            QMessageBox.warning(self, "尚未登入", "請先登入操作者。")
            self.continuous_button.setChecked(False)
            return
        if not self.state.settings_applied:
            QMessageBox.warning(self, "尚未套用設定", "請先在相機設定畫面套用設定。")
            self.continuous_button.setChecked(False)
            return
        if not self.views:
            self.start()
        frames = {slot: frame.copy() for slot, frame in self.last_frames.items()}
        if self.pending_detection_future and not self.pending_detection_future.done():
            return
        self.pending_detection_future = self.detection_executor.submit(self.router.run, frames)
        self.result_timer.start(30)

    def apply_pending_detection_result(self):
        if not self.pending_detection_future or not self.pending_detection_future.done():
            return
        future = self.pending_detection_future
        self.pending_detection_future = None
        self.result_timer.stop()
        try:
            inference = future.result()
        except Exception as exc:
            self.set_result("NG", 0.0)
            self.set_reason_cards(
                {
                    0: {
                        "result": "NG",
                        "confidence": 0.0,
                        "reasons": [f"背景檢測錯誤：{exc}"],
                    }
                }
            )
            return
        self.apply_detection_result(inference, record=False)

    def apply_detection_result(self, inference, record=False):
        self.set_result(inference.result, inference.confidence)
        self.set_ng_reason(inference)
        self.set_roi_confirmations(getattr(inference, "group_results", {}) or inference.roi_confirmations)
        self.show_annotated_frames(inference)
        if record or self.continuous_detection:
            self.record_detection(inference)

    def show_annotated_frames(self, inference):
        annotated_frames = getattr(inference, "annotated_frames", {})
        if self.continuous_detection:
            self.latest_annotated_frames = dict(annotated_frames)
            self.latest_yolo_annotated_frames = dict(getattr(inference, "yolo_annotated_frames", {}))
            self.latest_geometry_annotated_frames = dict(getattr(inference, "geometry_annotated_frames", {}))
        for slot, frame in annotated_frames.items():
            config = self._config_by_slot.get(slot)
            if config:
                display_frame = self.compose_detection_display_frame(slot, frame) if self.continuous_detection else frame
                self.set_monitor_frame(config, self.display_frame_for(config, display_frame))

    def record_detection(self, inference):
        if self.continuous_detection:
            now = time.time()
            if inference.result != "NG" and now - self._last_record_time < 5.0:
                return
            self._last_record_time = now
        active = self._active_camera_summary()
        # 序號來源優先序：手動輸入 ▸ 自動編號。
        if self.part_id.text().strip():
            raw_part_id = self.part_id.text().strip()
            part_id = process_barcode_text(raw_part_id, self.state.barcode_processing) or raw_part_id
            source = "manual"
        else:
            part_id = f"PART-{datetime.now():%H%M%S}"
            source = "auto"
        record = InspectionRecord(
            timestamp=f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            operator_name=self.state.operator_name,
            operator_role=self.state.operator_role,
            result=inference.result,
            part_id=part_id,
            active_cameras=active,
            confidence=f"{inference.confidence:.3f}",
            note=inference.note,
            barcode_source=source,
        )
        self.add_record(
            record,
            raw_frames=getattr(inference, "raw_frames", {}),
            annotated_frames=getattr(inference, "annotated_frames", {}),
            camera_results=getattr(inference, "camera_results", {}),
            roi_confirmations=getattr(inference, "roi_confirmations", {}),
        )

    def set_result(self, result, confidence):
        self.result_label.setText(result)
        self.result_label.setObjectName("resultPass" if result == "PASS" else "resultNg")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)

    def set_ng_reason(self, inference):
        self.set_reason_cards(inference.camera_results)

    def set_roi_confirmations(self, roi_confirmations):
        while self.roi_section_layout.count():
            item = self.roi_section_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        if not roi_confirmations:
            self.roi_section.setVisible(False)
            return
        self.roi_section.setVisible(True)
        for rid in sorted(roi_confirmations):
            info = roi_confirmations[rid]
            confirmed = info["confirmed"]
            votes = info["votes"]
            total = info["total"]
            card = QFrame()
            card.setObjectName("reasonPassBox" if confirmed else "reasonNgBox")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 4, 8, 4)
            icon = "✓" if confirmed else "✗"
            status = "確認" if confirmed else "未確認"
            label = QLabel(f"ROI #{rid}  {icon} {status}  ( {votes} / {total} )")
            label.setObjectName("reasonTitle")
            card_layout.addWidget(label)
            self.roi_section_layout.addWidget(card)

    def set_reason_cards(self, camera_results):
        self.clear_reason_cards()
        if not camera_results:
            self.add_reason_card("尚未檢測", "WAITING", ["尚未取得檢測結果"], 0.0)
            return

        for slot in sorted(camera_results):
            result_info = camera_results[slot]
            title = "系統" if slot == 0 else f"相機 {slot}"
            self.add_reason_card(
                title,
                result_info.get("result", "NG"),
                result_info.get("reasons", []),
                float(result_info.get("confidence", 0.0)),
            )

    def clear_reason_cards(self):
        while self.reason_layout.count():
            item = self.reason_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.reason_cards = {}

    def add_reason_card(self, title, result, reasons, confidence):
        card = QFrame()
        card.setObjectName("reasonPassBox" if result == "PASS" else "reasonNgBox")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QLabel(f"{title}: {result}  Confidence: {confidence:.3f}")
        header.setObjectName("reasonTitle")
        layout.addWidget(header)

        bullet_text = "\n".join(f"- {reason}" for reason in reasons) if reasons else "- 無詳細原因"
        detail = QLabel(bullet_text)
        detail.setWordWrap(True)
        layout.addWidget(detail)

        self.reason_layout.addWidget(card)

    def logout(self):
        self.stop()
        if self.on_logout:
            self.on_logout()
