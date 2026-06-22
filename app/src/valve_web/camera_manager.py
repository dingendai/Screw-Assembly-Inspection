"""Background camera capture for the web UI.

cv2.VideoCapture is not safe to read from multiple threads, and the MJPEG
stream endpoints plus the inference endpoint all need frames concurrently.
``CameraManager`` therefore runs one background thread per enabled camera slot
that keeps the latest transformed frame in memory; every consumer just reads
the cached frame under a lock.

Reuses ``valve_gui.camera`` (VideoSource / apply_frame_transform) unchanged.
"""

import threading
import time

from valve_gui.camera import VideoSource, apply_frame_transform


class _SlotWorker:
    def __init__(self, slot: int, device_index: int, simulate: bool, transform: dict):
        self.slot = slot
        self.device_index = device_index
        self.simulate = simulate
        self.transform = transform
        self._source: VideoSource | None = None
        self._frame = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error = ""
        self.input_fps = 0.0

    def start(self):
        self._source = VideoSource(f"CAMERA {self.slot}", self.device_index, self.simulate)
        if self._source.has_error():
            self.last_error = self._source.last_error
        self._thread = threading.Thread(target=self._run, name=f"cam-slot-{self.slot}", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            source = self._source
            if source is None:
                break
            frame = source.read()
            if frame is None:
                self.last_error = source.last_error or "沒有相機影像。"
                time.sleep(0.05)
                continue
            self.last_error = ""
            self.input_fps = source.input_fps
            transformed = apply_frame_transform(
                frame,
                flip_horizontal=self.transform.get("flip_horizontal", False),
                flip_vertical=self.transform.get("flip_vertical", False),
                rotation_degrees=self.transform.get("rotation_degrees", 0),
            )
            with self._lock:
                self._frame = transformed
            time.sleep(0.01)

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._source:
            self._source.release()
            self._source = None


class OperatorPreview:
    """Single background worker for the operator camera (login-page preview).

    Keeps one device open so the live preview and the photo capture share the
    same frame source instead of fighting over the device.
    """

    def __init__(self):
        self._worker: _SlotWorker | None = None
        self._lock = threading.Lock()

    def start(self, index: int, simulate: bool):
        with self._lock:
            if self._worker and self._worker.device_index == index and self._worker.simulate == simulate:
                return
            if self._worker:
                self._worker.stop()
            self._worker = _SlotWorker(0, index, simulate, {})
            self._worker.start()

    def latest(self):
        with self._lock:
            return self._worker.latest() if self._worker else None

    def last_error(self) -> str:
        with self._lock:
            return self._worker.last_error if self._worker else ""

    def stop(self):
        with self._lock:
            if self._worker:
                self._worker.stop()
                self._worker = None


class CameraManager:
    """Owns the background capture workers for every enabled inspection slot."""

    def __init__(self):
        self._workers: dict[int, _SlotWorker] = {}
        self._lock = threading.Lock()

    def restart(self, state):
        """(Re)build workers from the current AppState camera config."""
        self.stop_all()
        with self._lock:
            for camera in state.inspection_cameras:
                if not camera.enabled:
                    continue
                worker = _SlotWorker(
                    slot=camera.slot,
                    device_index=camera.device_index,
                    simulate=state.use_simulation,
                    transform={
                        "flip_horizontal": camera.flip_horizontal,
                        "flip_vertical": camera.flip_vertical,
                        "rotation_degrees": camera.rotation_degrees,
                    },
                )
                worker.start()
                self._workers[camera.slot] = worker

    def ensure_started(self, state):
        with self._lock:
            running = bool(self._workers)
        if not running:
            self.restart(state)

    def latest_frame(self, slot: int):
        with self._lock:
            worker = self._workers.get(slot)
        return worker.latest() if worker else None

    def frames_by_slot(self) -> dict:
        frames = {}
        with self._lock:
            workers = dict(self._workers)
        for slot, worker in workers.items():
            frame = worker.latest()
            if frame is not None:
                frames[slot] = frame
        return frames

    def status(self) -> dict:
        with self._lock:
            workers = dict(self._workers)
        return {
            slot: {"error": worker.last_error, "input_fps": round(worker.input_fps, 1)}
            for slot, worker in workers.items()
        }

    def active_slots(self) -> list[int]:
        with self._lock:
            return sorted(self._workers.keys())

    def stop_all(self):
        with self._lock:
            workers = list(self._workers.values())
            self._workers = {}
        for worker in workers:
            worker.stop()
