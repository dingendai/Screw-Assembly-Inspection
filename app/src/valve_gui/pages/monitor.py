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
from valve_gui.model_registry import format_camera_model_names
from valve_gui.models import AppState, InspectionRecord
from valve_gui.permissions import role_label
from valve_gui.utils import hex_to_bgr
from valve_gui.widgets import CameraView


MAX_GUI_FRAME_DIMENSION = 960


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
        self.continuous_detection = False
        self.detection_executor = ThreadPoolExecutor(max_workers=1)
        self.pending_detection_future = None
        self._single_worker = None
        self._last_record_time: float = 0.0
        self._last_barcode: str | None = None
        self._last_barcode_source: str = ""
        self._source_by_slot: dict = {}
        self._config_by_slot: dict = {}
        self._view_by_slot: dict = {}
        self.frame_timer = QTimer(self)
        self.frame_timer.timeout.connect(self.update_frames)
        self.detection_timer = QTimer(self)
        self.detection_timer.timeout.connect(self.detect_current_frames)
        self.result_timer = QTimer(self)
        self.result_timer.timeout.connect(self.apply_pending_detection_result)

        self.part_id = QLineEdit()
        self.part_id.setPlaceholderText("工件序號 / 批號")
        self.barcode_label = QLabel("讀到條碼：--")
        self.barcode_label.setObjectName("mutedText")
        self.result_label = QLabel("WAITING")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_label.setObjectName("resultWaiting")
        self.confidence_label = QLabel("Confidence: --")
        self.confidence_label.setObjectName("mutedText")
        self.camera_status_label = QLabel("相機狀態：--")
        self.camera_status_label.setObjectName("mutedText")
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
        self.operator_label = QLabel()
        self.operator_label.setObjectName("mutedText")
        self.operator_label.setVisible(False)
        self.model_label = QLabel()
        self.model_label.setObjectName("mutedText")
        self.model_label.setVisible(False)
        self.info_toggle_button = QPushButton("顯示資訊")
        self.info_toggle_button.setCheckable(True)
        self.info_toggle_button.toggled.connect(self.toggle_info_labels)
        self.region_overlay_box = QCheckBox("顯示指定範圍")
        self.region_overlay_box.stateChanged.connect(self.toggle_region_overlay)
        self.continuous_button = QPushButton("連續檢測")
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
        self.inspect_button.clicked.connect(self.inspect_once)

        side = QGroupBox("檢測狀態")
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(self.info_toggle_button)
        side_layout.addWidget(self.operator_label)
        side_layout.addWidget(self.model_label)
        side_layout.addWidget(self.region_overlay_box)
        side_layout.addWidget(QLabel("目前受測物件"))
        side_layout.addWidget(self.part_id)
        side_layout.addWidget(self.barcode_label)
        side_layout.addWidget(self.result_label)
        side_layout.addWidget(self.confidence_label)
        side_layout.addWidget(self.camera_status_label)
        side_layout.addWidget(QLabel("相機檢測狀態"))
        side_layout.addWidget(self.reason_list)
        side_layout.addWidget(self.roi_section)
        side_layout.addStretch()

        bottom_controls = QVBoxLayout()
        bottom_controls.setSpacing(8)

        detection_actions = QHBoxLayout()
        detection_actions.setSpacing(8)
        detection_actions.addWidget(self.inspect_button)
        detection_actions.addWidget(self.continuous_button)

        camera_actions = QHBoxLayout()
        camera_actions.setSpacing(8)
        camera_actions.addWidget(start_button)
        camera_actions.addWidget(stop_button)

        bottom_controls.addWidget(QLabel("檢測控制"))
        bottom_controls.addLayout(detection_actions)
        side_layout.addSpacing(8)
        bottom_controls.addWidget(QLabel("相機控制"))
        bottom_controls.addLayout(camera_actions)

        side_layout.addLayout(bottom_controls)
        side.setMinimumWidth(560)
        side.setMaximumWidth(680)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self.monitor_tabs, 1)
        layout.addWidget(side, 0)

    def toggle_info_labels(self, checked):
        self.operator_label.setVisible(checked)
        self.model_label.setVisible(checked)
        self.info_toggle_button.setText("隱藏資訊" if checked else "顯示資訊")

    def refresh(self):
        self.region_overlay_box.blockSignals(True)
        self.region_overlay_box.setChecked(self.state.region_overlay.show_on_monitor)
        self.region_overlay_box.blockSignals(False)
        self.operator_label.setText(
            f"操作者：{self.state.operator_name or '--'}"
            f" / 角色：{role_label(self.state.operator_role, self.state.role_labels)}"
            f" / 登入：{self.state.login_time or '--'}"
        )
        routes = [
            f"C{camera.slot}->{format_camera_model_names(camera)}"
            for camera in self.state.inspection_cameras
            if camera.enabled
        ]
        self.model_label.setText("相機模型：" + (" / ".join(routes) if routes else "--"))

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
            view = CameraView(f"Camera {config.slot}", fill_mode=True)
            single_view = CameraView(f"Camera {config.slot}", fill_mode=True)
            single_page = QWidget()
            single_layout = QVBoxLayout(single_page)
            single_layout.setContentsMargins(12, 12, 12, 12)
            single_layout.addWidget(single_view, 1)
            self.views.append((config, view))
            self.single_views[config.slot] = single_view
            self.grid.addWidget(view, idx // columns, idx % columns)
            self.monitor_tabs.addTab(single_page, f"Camera {config.slot}")

    def start(self):
        continuous_requested = self.continuous_detection
        self.stop(reset_continuous=False)
        self.detection_executor = ThreadPoolExecutor(max_workers=1)
        self.continuous_detection = continuous_requested
        self.refresh()
        errors = []
        for config, _ in self.views:
            source = VideoSource(
                f"CAMERA {config.slot}",
                config.device_index,
                self.state.use_simulation,
                getattr(config, "focus_mode", "auto"),
                getattr(config, "manual_focus_value", 120),
            )
            if source.has_error():
                errors.append(source.last_error)
            self.sources.append((config.slot, source))
        self.camera_status_label.setText("相機狀態：" + ("；".join(errors) if errors else "正常"))
        self._source_by_slot = {slot: source for slot, source in self.sources}
        self._config_by_slot = {config.slot: config for config, _ in self.views}
        self._view_by_slot = {config.slot: view for config, view in self.views}
        self.frame_timer.start(33)
        if self.continuous_detection:
            self.detection_timer.start(500)

    def stop(self, reset_continuous=True):
        self.frame_timer.stop()
        self.detection_timer.stop()
        self.result_timer.stop()
        self.pending_detection_future = None
        self.detection_executor.shutdown(wait=False)
        self.latest_annotated_frames = {}
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
                self.camera_status_label.setText(f"相機狀態：{source.last_error or '沒有相機影像。'}")
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
            display_frame = self.latest_annotated_frames.get(config.slot) if self.continuous_detection else None
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

    def toggle_region_overlay(self):
        self.state.region_overlay.show_on_monitor = self.region_overlay_box.isChecked()
        save_app_config(self.state)

    def frame_with_region_overlay(self, config, frame):
        if not self.state.region_overlay.show_on_monitor:
            return frame
        if not getattr(config, "region_detection_enabled", False):
            return frame
        if not config.detection_regions and not config.exclusion_regions:
            return frame
        annotated = frame.copy()
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
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame,
                self.format_region_label(label, index, region),
                (x1 + 6, max(18, y1 + 22)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
            )

    def format_region_label(self, label, index, region):
        roi_id = region.get("roi_id")
        if roi_id is not None:
            return f"#{roi_id}"
        return f"{label} {index}"

    def update_barcode_label(self, text, source=""):
        if text and source:
            self.barcode_label.setText(f"讀到條碼：{text}（{source}）")
        else:
            self.barcode_label.setText(f"讀到條碼：{text or '--'}")

    def inspect_once(self):
        if self._single_worker and self._single_worker.isRunning():
            return
        if not self.state.is_logged_in:
            QMessageBox.warning(self, "尚未登入", "請先登入操作者。")
            return
        if not self.state.settings_applied:
            QMessageBox.warning(self, "尚未套用設定", "請先在相機設定畫面套用設定。")
            return
        if not self.views:
            self.start()
        frames = {slot: frame.copy() for slot, frame in self.last_frames.items()}
        self.inspect_button.setEnabled(False)
        self.continuous_button.setEnabled(False)
        self.inspect_button.setObjectName("activeDetectionButton")
        self.inspect_button.style().unpolish(self.inspect_button)
        self.inspect_button.style().polish(self.inspect_button)
        self._single_worker = _DetectionWorker(self.router, frames, self)
        self._single_worker.finished.connect(self._on_single_detection_done)
        self._single_worker.errored.connect(self._on_single_detection_error)
        self._single_worker.start()

    def _on_single_detection_done(self, inference):
        self.apply_detection_result(inference, record=True)
        self._restore_inspect_button()

    def _on_single_detection_error(self, error_msg):
        self.set_result("NG", 0.0)
        self.set_reason_cards({0: {"result": "NG", "confidence": 0.0, "reasons": [f"檢測錯誤：{error_msg}"]}})
        self._restore_inspect_button()

    def _restore_inspect_button(self):
        self.inspect_button.setObjectName("primaryButton")
        self.inspect_button.style().unpolish(self.inspect_button)
        self.inspect_button.style().polish(self.inspect_button)
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
            self.detection_timer.start(500)
        else:
            self.detection_timer.stop()
            self.result_timer.stop()
            self.pending_detection_future = None
            self.latest_annotated_frames = {}

    def update_detection_controls(self):
        self.inspect_button.setVisible(not self.continuous_detection)
        self.continuous_button.setEnabled(True)
        self.continuous_button.setText("停止連續檢測" if self.continuous_detection else "連續檢測")

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
        self.set_roi_confirmations(inference.roi_confirmations)
        self.show_annotated_frames(inference.annotated_frames)
        self._last_barcode = getattr(inference, "barcode", None)
        self._last_barcode_source = self._barcode_source_label(inference)
        self.update_barcode_label(self._last_barcode, self._last_barcode_source)
        if record or self.continuous_detection:
            self.record_detection(inference)

    @staticmethod
    def _barcode_source_label(inference):
        sources = getattr(inference, "barcode_sources", None) or []
        if not sources:
            return ""
        first = sources[0]
        return first.get("class") or first.get("model") or ""

    def show_annotated_frames(self, annotated_frames):
        if self.continuous_detection:
            self.latest_annotated_frames = dict(annotated_frames)
        for slot, frame in annotated_frames.items():
            config = self._config_by_slot.get(slot)
            if config:
                self.set_monitor_frame(config, self.display_frame_for(config, frame))

    def record_detection(self, inference):
        if self.continuous_detection:
            now = time.time()
            if inference.result != "NG" and now - self._last_record_time < 5.0:
                return
            self._last_record_time = now
        active = ",".join(
            f"C{config.slot}:D{config.device_index}:M{format_camera_model_names(config)}"
            for config, _ in self.views
        )
        # 序號來源優先序：偵測到的標籤條碼 ▸ 手動輸入 ▸ 自動編號。
        barcode = getattr(inference, "barcode", None)
        if barcode:
            part_id = barcode
            source = self._barcode_source_label(inference) or "barcode"
        elif self.part_id.text().strip():
            part_id = self.part_id.text().strip()
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
        self.add_record(record)

    def set_result(self, result, confidence):
        self.result_label.setText(result)
        self.result_label.setObjectName("resultPass" if result == "PASS" else "resultNg")
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        self.confidence_label.setText(f"Confidence: {confidence:.3f}")

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
            title = "系統" if slot == 0 else f"Camera {slot}"
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
