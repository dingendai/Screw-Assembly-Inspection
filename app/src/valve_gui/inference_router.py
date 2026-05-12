import random
from dataclasses import dataclass, field

import cv2

from valve_gui.model_registry import model_by_name


@dataclass
class InferenceResult:
    result: str
    confidence: float
    note: str
    annotated_frames: dict[int, object] = field(default_factory=dict)


class InferenceRouter:
    """Routes each camera frame to the model assigned to that camera."""

    def __init__(self, state):
        self.state = state
        self.loaded_models = {}
        self.ultralytics_available = None

    def run(self, frames_by_slot):
        if not frames_by_slot:
            return InferenceResult("NG", 0.0, "No frame available")

        annotated_frames = {}
        confidences = []
        notes = []
        missing = []

        for camera in self.state.inspection_cameras:
            if not camera.enabled or camera.slot not in frames_by_slot:
                continue
            model = model_by_name(self.state, camera.assigned_model_name)
            if not model or not model.enabled:
                missing.append(f"Camera {camera.slot}")
                continue

            frame = frames_by_slot[camera.slot]
            annotated, confidence, note = self.run_single_model(frame, camera.slot, model)
            annotated_frames[camera.slot] = annotated
            confidences.append(confidence)
            notes.append(note)

        if missing:
            return InferenceResult("NG", 0.0, "Missing model assignment: " + ", ".join(missing), annotated_frames)

        confidence = min(confidences) if confidences else 0.0
        result = "PASS" if confidence >= 0.5 else "NG"
        return InferenceResult(result, confidence, "；".join(notes), annotated_frames)

    def run_single_model(self, frame, slot, model_config):
        yolo_model = self.load_yolo_model(model_config.file_path)
        if yolo_model is not None:
            try:
                results = yolo_model(frame, verbose=False)
                result = results[0]
                annotated = result.plot()
                boxes = getattr(result, "boxes", None)
                if boxes is not None and len(boxes) > 0:
                    confidence = float(boxes.conf.max().item())
                    count = len(boxes)
                    return annotated, confidence, f"C{slot}->{model_config.name}: {count} object(s)"
                return annotated, 0.0, f"C{slot}->{model_config.name}: no object"
            except Exception as exc:
                annotated = self.draw_placeholder_annotation(frame.copy(), slot, model_config.name, f"YOLO error: {exc}")
                return annotated, 0.0, f"C{slot}->{model_config.name}: YOLO error"

        confidence = random.uniform(0.82, 0.96)
        annotated = self.draw_placeholder_annotation(frame.copy(), slot, model_config.name, f"placeholder {confidence:.2f}")
        return annotated, confidence, f"C{slot}->{model_config.name}: placeholder"

    def load_yolo_model(self, path):
        if not path:
            return None
        if path in self.loaded_models:
            return self.loaded_models[path]
        if self.ultralytics_available is False:
            return None
        try:
            from ultralytics import YOLO

            self.ultralytics_available = True
            self.loaded_models[path] = YOLO(path)
            return self.loaded_models[path]
        except Exception:
            self.ultralytics_available = False
            return None

    def draw_placeholder_annotation(self, frame, slot, model_name, label):
        height, width = frame.shape[:2]
        x1 = max(20, width // 5)
        y1 = max(20, height // 5)
        x2 = min(width - 20, x1 + width // 2)
        y2 = min(height - 20, y1 + height // 3)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (32, 190, 92), 3)
        cv2.putText(
            frame,
            f"C{slot} {model_name}",
            (x1, max(24, y1 - 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (32, 190, 92),
            2,
        )
        cv2.putText(
            frame,
            label,
            (x1, min(height - 18, y2 + 30)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (32, 190, 92),
            2,
        )
        return frame
