import time

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal


def apply_frame_transform(frame, flip_horizontal=False, flip_vertical=False, rotation_degrees=0):
    if flip_horizontal and flip_vertical:
        frame = cv2.flip(frame, -1)
    elif flip_horizontal:
        frame = cv2.flip(frame, 1)
    elif flip_vertical:
        frame = cv2.flip(frame, 0)

    rotation = rotation_degrees % 360
    if rotation == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)
    elif rotation == 270:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def apply_region_mask(frame, detection_regions=None, exclusion_regions=None):
    detection_regions = detection_regions or []
    exclusion_regions = exclusion_regions or []
    if not detection_regions and not exclusion_regions:
        return frame

    height, width = frame.shape[:2]
    if detection_regions:
        masked = np.zeros_like(frame)
        for region in detection_regions:
            x1, y1, x2, y2 = normalised_region_to_pixels(region, width, height)
            masked[y1:y2, x1:x2] = frame[y1:y2, x1:x2]
    else:
        masked = frame.copy()

    for region in exclusion_regions:
        x1, y1, x2, y2 = normalised_region_to_pixels(region, width, height)
        masked[y1:y2, x1:x2] = 0
    return masked


def region_applies_to_model(region, model_name):
    model_names = region.get("model_names", [])
    if not model_names:
        return True
    return model_name in model_names


def regions_for_model(regions, model_name):
    return [region for region in regions if region_applies_to_model(region, model_name)]


def normalised_region_to_pixels(region, width, height):
    x = float(region.get("x", 0.0))
    y = float(region.get("y", 0.0))
    w = float(region.get("w", 0.0))
    h = float(region.get("h", 0.0))
    x1 = max(0, min(width, int(x * width)))
    y1 = max(0, min(height, int(y * height)))
    x2 = max(x1, min(width, int((x + w) * width)))
    y2 = max(y1, min(height, int((y + h) * height)))
    return x1, y1, x2, y2


def bbox_center_in_region(bbox_xyxy, region, frame_w, frame_h) -> bool:
    cx = (bbox_xyxy[0] + bbox_xyxy[2]) / 2
    cy = (bbox_xyxy[1] + bbox_xyxy[3]) / 2
    x1, y1, x2, y2 = normalised_region_to_pixels(region, frame_w, frame_h)
    return x1 <= cx <= x2 and y1 <= cy <= y2


def roi_id_detections(detection_regions, yolo_boxes_xyxy, frame_w, frame_h) -> dict:
    """
    For each roi_id found in detection_regions, return whether any YOLO bbox
    center falls within any region bearing that roi_id.
    Regions without roi_id are skipped.
    """
    result: dict[int, bool] = {}
    for region in detection_regions:
        rid = region.get("roi_id")
        if rid is None:
            continue
        if rid not in result:
            result[rid] = False
        if result[rid]:
            continue
        for box in yolo_boxes_xyxy:
            if bbox_center_in_region(box, region, frame_w, frame_h):
                result[rid] = True
                break
    return result


class VideoSource:
    def __init__(self, label: str, index: int, simulate: bool, focus_mode="auto", manual_focus_value=120):
        self.label = label
        self.index = index
        self.requested_simulation = simulate
        self.simulate = simulate
        self.capture = None
        self.counter = 0
        self.last_error = ""
        self.focus_status = ""
        self.input_fps = 0.0
        self._last_frame_time = None
        if not simulate:
            self.capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not self.capture.isOpened():
                if self.capture:
                    self.capture.release()
                self.capture = None
                self.last_error = (
                    f"{label} / Device {index}: 無法開啟相機。"
                    "請確認相機已連接，且未被其他程式占用。"
                )
            else:
                self.apply_focus_settings(focus_mode, manual_focus_value)

    def apply_focus_settings(self, focus_mode, manual_focus_value):
        if not self.capture or not self.capture.isOpened():
            return
        if focus_mode != "manual":
            try:
                set_auto = self.capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                self.focus_status = f"auto focus set_auto={set_auto}"
            except Exception as exc:
                self.focus_status = f"auto focus error={exc}"
            return
        try:
            value = max(0, min(1023, int(manual_focus_value)))
        except (TypeError, ValueError):
            value = 120
        try:
            set_auto = self.capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
            set_focus = self.capture.set(cv2.CAP_PROP_FOCUS, value)
            readback = self.capture.get(cv2.CAP_PROP_FOCUS)
            self.focus_status = (
                f"manual focus requested={value} "
                f"set_auto={set_auto} set_focus={set_focus} readback={readback}"
            )
        except Exception as exc:
            self.focus_status = f"manual focus requested={value} error={exc}"

    def current_focus_value(self):
        if not self.capture or not self.capture.isOpened():
            return None
        try:
            value = self.capture.get(cv2.CAP_PROP_FOCUS)
        except Exception:
            return None
        if value < 0:
            return None
        return value

    def read(self):
        if self.capture and self.capture.isOpened():
            ok, frame = self.capture.read()
            if ok:
                self.last_error = ""
                self._mark_frame_received()
                return frame
            self.last_error = f"{self.label} / Device {self.index}: 相機已開啟但讀不到影像。"
        if self.simulate:
            frame = self._simulated_frame()
            self._mark_frame_received()
            return frame
        return None

    def _mark_frame_received(self):
        now = time.perf_counter()
        if self._last_frame_time is not None:
            elapsed = now - self._last_frame_time
            if elapsed > 0:
                current_fps = 1.0 / elapsed
                self.input_fps = current_fps if self.input_fps <= 0 else (self.input_fps * 0.85 + current_fps * 0.15)
        self._last_frame_time = now

    def has_error(self):
        return bool(self.last_error)

    def release(self):
        if self.capture:
            self.capture.release()
            self.capture = None

    def _simulated_frame(self):
        self.counter += 1
        frame = np.zeros((720, 960, 3), dtype=np.uint8)
        frame[:] = (28, 34, 43)
        pulse = int(40 + 25 * np.sin(self.counter / 12))
        cv2.rectangle(frame, (70, 80), (890, 640), (54 + pulse, 76, 86), -1)
        cv2.rectangle(frame, (235, 205), (725, 515), (120, 132, 138), -1)
        cv2.circle(frame, (480, 360), 118, (58, 72, 78), -1)
        cv2.circle(frame, (480, 360), 70, (34, 40, 44), -1)
        cv2.line(frame, (310, 360), (650, 360), (164, 176, 180), 24)
        cv2.putText(frame, self.label, (40, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.25, (235, 239, 241), 2)
        cv2.putText(frame, "SIMULATED", (40, 700), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (165, 176, 180), 2)
        return frame


def detect_camera_indexes(max_index=12):
    found = []
    for index in range(max_index + 1):
        capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if capture.isOpened():
            ok, _ = capture.read()
            if ok:
                found.append(index)
        capture.release()
    return found


class CameraScanWorker(QThread):
    """Runs detect_camera_indexes on a background thread to avoid blocking the UI."""
    finished = pyqtSignal(list)

    def __init__(self, max_index=12, parent=None):
        super().__init__(parent)
        self.max_index = max_index

    def run(self):
        found = detect_camera_indexes(self.max_index)
        self.finished.emit(found)
