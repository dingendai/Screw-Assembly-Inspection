import random
from dataclasses import dataclass, field

import cv2

from valve_gui.model_registry import camera_model_names, model_by_name


@dataclass
class InferenceResult:
    result: str
    confidence: float
    note: str
    annotated_frames: dict[int, object] = field(default_factory=dict)
    camera_results: dict[int, dict] = field(default_factory=dict)


class InferenceRouter:
    """Routes each camera frame to every model assigned to that camera."""

    def __init__(self, state):
        self.state = state
        self.loaded_models = {}
        self.ultralytics_available = None

    def run(self, frames_by_slot):
        if not frames_by_slot:
            return InferenceResult("NG", 0.0, "No frame available")

        annotated_frames = {}
        camera_results = {}
        confidences = []
        notes = []
        missing = []
        rule_failures = []

        for camera in self.state.inspection_cameras:
            if not camera.enabled or camera.slot not in frames_by_slot:
                continue
            model_names = camera_model_names(camera)
            if not model_names:
                missing.append(f"Camera {camera.slot}")
                camera_results[camera.slot] = {
                    "result": "NG",
                    "confidence": 0.0,
                    "reasons": ["未指定模型"],
                }
                continue

            frame = frames_by_slot[camera.slot]
            annotated = frame
            camera_confidences = []
            camera_reasons = []
            for model_name in model_names:
                model = model_by_name(self.state, model_name)
                if not model or not model.enabled:
                    missing.append(f"Camera {camera.slot}->{model_name}")
                    camera_confidences.append(0.0)
                    camera_reasons.append(f"{model_name}: 模型未啟用或不存在")
                    continue
                annotated, confidence, object_count, note = self.run_single_model(annotated, camera.slot, model)
                rule = self.decision_rule_for(camera.slot, model.name)
                threshold = float(rule.get("confidence_threshold", 0.5))
                required_count = int(rule.get("required_object_count", 1))
                model_pass = confidence >= threshold and object_count == required_count
                confidences.append(confidence)
                notes.append(note)
                camera_confidences.append(confidence)
                camera_reasons.append(
                    f"{model.name}: {'PASS' if model_pass else 'NG'} / "
                    f"confidence {confidence:.3f} (門檻 >= {threshold:.3f}) / "
                    f"標籤框 {object_count} (需求 = {required_count})"
                )
                if not model_pass:
                    rule_failures.append(f"Camera {camera.slot}->{model.name}")
            annotated_frames[camera.slot] = annotated
            camera_confidence = min(camera_confidences) if camera_confidences else 0.0
            camera_results[camera.slot] = {
                "result": "NG" if any(item.startswith(f"Camera {camera.slot}->") for item in rule_failures) else "PASS",
                "confidence": camera_confidence,
                "reasons": camera_reasons or ["沒有可用的模型結果"],
            }

        if missing:
            return InferenceResult(
                "NG",
                0.0,
                "Missing model assignment: " + ", ".join(missing),
                annotated_frames,
                camera_results,
            )

        confidence = min(confidences) if confidences else 0.0
        result = "NG" if rule_failures or not confidences else "PASS"
        return InferenceResult(result, confidence, "；".join(notes), annotated_frames, camera_results)

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
                    return annotated, confidence, count, f"C{slot}->{model_config.name}: {count} object(s)"
                return annotated, 0.0, 0, f"C{slot}->{model_config.name}: no object"
            except Exception as exc:
                annotated = self.draw_placeholder_annotation(frame.copy(), slot, model_config.name, f"YOLO error: {exc}")
                return annotated, 0.0, 0, f"C{slot}->{model_config.name}: YOLO error"

        confidence = random.uniform(0.82, 0.96)
        annotated = self.draw_placeholder_annotation(frame.copy(), slot, model_config.name, f"placeholder {confidence:.2f}")
        return annotated, confidence, 1, f"C{slot}->{model_config.name}: placeholder"

    def decision_rule_for(self, slot, model_name):
        default_threshold = getattr(self.state.decision, "pass_confidence_threshold", 0.5)
        default_rule = {
            "confidence_threshold": default_threshold,
            "required_object_count": 1,
        }
        rules = getattr(self.state.decision, "model_rules", {})
        if not isinstance(rules, dict):
            return default_rule
        rule = rules.get(self.decision_rule_key(slot, model_name), {})
        if not isinstance(rule, dict):
            return default_rule
        return {
            "confidence_threshold": rule.get("confidence_threshold", default_threshold),
            "required_object_count": rule.get("required_object_count", 1),
        }

    def decision_rule_key(self, slot, model_name):
        return f"{slot}::{model_name}"

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
