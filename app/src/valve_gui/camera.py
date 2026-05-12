import cv2
import numpy as np


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


class VideoSource:
    def __init__(self, label: str, index: int, simulate: bool):
        self.label = label
        self.index = index
        self.requested_simulation = simulate
        self.simulate = simulate
        self.capture = None
        self.counter = 0
        self.last_error = ""
        if not simulate:
            self.capture = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if not self.capture.isOpened():
                if self.capture:
                    self.capture.release()
                self.capture = None
                self.last_error = (
                    f"{label} / Device {index}: 無法開啟相機。"
                    "請確認相機已連接、未被其他程式占用，或改用模擬影像。"
                )

    def read(self):
        if self.capture and self.capture.isOpened():
            ok, frame = self.capture.read()
            if ok:
                self.last_error = ""
                return frame
            self.last_error = f"{self.label} / Device {self.index}: 相機已開啟但讀不到影像。"
        if self.simulate:
            return self._simulated_frame()
        return None

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
        cv2.putText(frame, "SIMULATED CAMERA", (40, 700), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (165, 176, 180), 2)
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
