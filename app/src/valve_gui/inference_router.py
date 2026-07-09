import random
from dataclasses import dataclass, field

import cv2

from valve_gui.camera import apply_region_mask, regions_for_model, summarise_region_detections
from valve_gui.lock_geometry import (
    analyze_lock_geometry_regions,
    draw_lock_geometry_overlay,
    geometry_summary,
)
from valve_gui.model_registry import camera_model_names
from valve_gui.utils import (
    compare_decision_value,
    decision_rule_key as _rule_key,
    hex_to_bgr,
    normalise_decision_operator,
)


@dataclass
class InferenceResult:
    result: str
    confidence: float
    note: str
    annotated_frames: dict[int, object] = field(default_factory=dict)
    yolo_annotated_frames: dict[int, object] = field(default_factory=dict)
    geometry_annotated_frames: dict[int, object] = field(default_factory=dict)
    camera_results: dict[int, dict] = field(default_factory=dict)
    roi_confirmations: dict[int, dict] = field(default_factory=dict)
    group_results: dict[int, dict] = field(default_factory=dict)
    # Compatibility fields kept for older callers; automatic barcode decoding is disabled.
    barcode: str | None = None
    barcode_sources: list[dict] = field(default_factory=list)
    raw_frames: dict[int, object] = field(default_factory=dict)


class InferenceRouter:
    """Routes each camera frame to every model assigned to that camera."""

    def __init__(self, state):
        self.state = state
        self.loaded_models = {}
        self.ultralytics_available = None
        self._load_errors = set()

    def run(self, frames_by_slot):
        if not frames_by_slot:
            return InferenceResult("NG", 0.0, "No frame available")

        raw_frames = {
            slot: frame.copy()
            for slot, frame in frames_by_slot.items()
            if frame is not None
        }
        annotated_frames = {}
        yolo_annotated_frames = {}
        geometry_annotated_frames = {}
        camera_results = {}
        confidences = []
        notes = []
        missing = []
        failed_slots: set[int] = set()
        all_roi_votes: dict[int, dict] = {}
        group_results: dict[int, dict] = {}
        models_by_name = {model.name: model for model in self.state.model_configs}

        for camera in self.state.inspection_cameras:
            if not camera.enabled or camera.slot not in frames_by_slot:
                continue
            model_names = camera_model_names(camera)
            if not model_names:
                missing.append(f"相機 {camera.slot}")
                camera_results[camera.slot] = {
                    "result": "NG",
                    "confidence": 0.0,
                    "reasons": ["未指定模型"],
                }
                continue

            display_frame = frames_by_slot[camera.slot]
            yolo_annotated = display_frame.copy()
            camera_confidences = []
            camera_reasons = []
            camera_roi_detected: dict[int, bool] = {}
            for model_name in model_names:
                model = models_by_name.get(model_name)
                if not model or not model.enabled:
                    missing.append(f"相機 {camera.slot}->{model_name}")
                    camera_confidences.append(0.0)
                    camera_reasons.append(f"{model_name}: 模型未啟用或不存在")
                    continue
                inference_frame = display_frame
                model_detection_regions = []
                if getattr(camera, "region_detection_enabled", False):
                    model_detection_regions = regions_for_model(camera.detection_regions, model.name)
                    inference_frame = apply_region_mask(
                        display_frame,
                        model_detection_regions,
                        regions_for_model(camera.exclusion_regions, model.name),
                    )
                yolo_annotated, confidence, object_count, note, yolo_boxes_xyxy, _ = self.run_single_model(
                    inference_frame,
                    camera.slot,
                    model,
                    display_frame=yolo_annotated,
                )
                counted_object_count = object_count
                if getattr(camera, "region_detection_enabled", False) and model_detection_regions:
                    h, w = display_frame.shape[:2]
                    counted_object_count, per_group = summarise_region_detections(
                        model_detection_regions, yolo_boxes_xyxy, w, h
                    )
                    for rid, detected in per_group.items():
                        camera_roi_detected[rid] = camera_roi_detected.get(rid, False) or detected
                rule = self.decision_rule_for(camera.slot, model.name)
                confidence_operator = normalise_decision_operator(rule.get("confidence_operator", ">="), ">=")
                threshold = float(rule.get("confidence_threshold", 0.5))
                count_operator = normalise_decision_operator(rule.get("required_object_count_operator", "="), "=")
                required_count = int(rule.get("required_object_count", 1))
                confidence_pass = compare_decision_value(confidence, confidence_operator, threshold)
                count_pass = compare_decision_value(counted_object_count, count_operator, required_count)
                model_pass = confidence_pass and count_pass
                confidences.append(confidence)
                notes.append(note)
                camera_confidences.append(confidence)
                camera_reasons.append(
                    f"{model.name}: {'PASS' if model_pass else 'NG'} / "
                    f"confidence {confidence:.3f} (門檻 {confidence_operator} {threshold:.3f}) / "
                    f"標籤框 {object_count} (需求 {count_operator} {required_count})"
                )
                if not model_pass:
                    failed_slots.add(camera.slot)

            for rid, detected in camera_roi_detected.items():
                if rid not in all_roi_votes:
                    all_roi_votes[rid] = {"votes": 0, "total": 0, "camera_slots": []}
                all_roi_votes[rid]["total"] += 1
                all_roi_votes[rid]["camera_slots"].append(camera.slot)
                if detected:
                    all_roi_votes[rid]["votes"] += 1

            geometry_annotated = display_frame.copy()
            geometry_regions = [
                region
                for region in getattr(camera, "lock_geometry_regions", [])
                if bool(region.get("enabled", True))
            ]
            if getattr(camera, "lock_geometry_enabled", False):
                if geometry_regions:
                    geometry_analyses = analyze_lock_geometry_regions(display_frame, geometry_regions)
                    geometry_annotated = draw_lock_geometry_overlay(
                        geometry_annotated, geometry_analyses, show_result=True
                    )
                    geometry_failed = False
                    for analysis in geometry_analyses:
                        result = analysis.result
                        camera_reasons.append(geometry_summary(analysis.region_config, result))
                        if result.prediction in {"separated", "unknown"}:
                            geometry_failed = True
                    if geometry_failed:
                        failed_slots.add(camera.slot)
                else:
                    camera_reasons.append("幾何檢測已啟用，但尚未設定啟用中的幾何 ROI")

            annotated = yolo_annotated.copy()
            if getattr(camera, "lock_geometry_enabled", False) and geometry_regions:
                geometry_analyses = analyze_lock_geometry_regions(display_frame, geometry_regions)
                annotated = draw_lock_geometry_overlay(annotated, geometry_analyses, show_result=True)
            annotated_frames[camera.slot] = annotated
            yolo_annotated_frames[camera.slot] = yolo_annotated
            geometry_annotated_frames[camera.slot] = geometry_annotated
            camera_confidence = min(camera_confidences) if camera_confidences else 0.0
            camera_results[camera.slot] = {
                "result": "NG" if camera.slot in failed_slots else "PASS",
                "confidence": camera_confidence,
                "reasons": camera_reasons or ["沒有可用的模型結果"],
            }

        roi_confirmations = {
            rid: {
                "confirmed": info["votes"] > info["total"] / 2,
                "votes": info["votes"],
                "total": info["total"],
                "camera_slots": info["camera_slots"],
            }
            for rid, info in all_roi_votes.items()
        }

        configured_group_ids = {
            rid
            for camera in self.state.inspection_cameras
            for region in getattr(camera, "detection_regions", [])
            for rid in [region.get("roi_id")]
            if isinstance(rid, int) and rid > 0
        }
        configured_group_ids.update(
            int(key)
            for key in getattr(self.state.decision, "group_rules", {}).keys()
            if str(key).isdigit()
        )
        for rid in sorted(configured_group_ids):
            info = all_roi_votes.get(rid, {"votes": 0, "total": 0, "camera_slots": []})
            rule = self.group_rule_for(rid)
            detected = info["votes"] > 0
            passed = detected if rule.get("required", True) else True
            group_results[rid] = {
                "confirmed": passed,
                "detected": detected,
                "votes": info["votes"],
                "total": info["total"],
                "camera_slots": info["camera_slots"],
                "required": bool(rule.get("required", True)),
                "mode": "any",
            }

        if missing:
            return InferenceResult(
                "NG",
                0.0,
                "Missing model assignment: " + ", ".join(missing),
                annotated_frames,
                yolo_annotated_frames,
                geometry_annotated_frames,
                camera_results,
                roi_confirmations,
                group_results,
                raw_frames=raw_frames,
            )

        confidence = min(confidences) if confidences else 0.0
        group_failed = any(
            result_info.get("required", True) and not result_info.get("detected", False)
            for result_info in group_results.values()
        )
        result = "NG" if failed_slots or group_failed or not confidences else "PASS"
        return InferenceResult(
            result,
            confidence,
            "；".join(notes),
            annotated_frames,
            yolo_annotated_frames,
            geometry_annotated_frames,
            camera_results,
            roi_confirmations,
            group_results,
            raw_frames=raw_frames,
        )

    def run_single_model(self, frame, slot, model_config, display_frame=None):
        display_frame = frame if display_frame is None else display_frame
        yolo_model = self.load_yolo_model(model_config.file_path)
        if yolo_model is not None:
            try:
                results = yolo_model(frame, verbose=False)
                result = results[0]
                annotated = self.draw_yolo_annotations(display_frame.copy(), result, model_config.name)
                boxes = getattr(result, "boxes", None)
                if boxes is not None and len(boxes) > 0:
                    confidence = float(boxes.conf.max().item())
                    count = len(boxes)
                    names = getattr(result, "names", {}) or {}
                    yolo_boxes_xyxy = [box.xyxy[0].detach().cpu().tolist() for box in boxes]
                    yolo_box_classes = [self._box_class_name(box, names) for box in boxes]
                    return (
                        annotated, confidence, count,
                        f"C{slot}->{model_config.name}: {count} object(s)",
                        yolo_boxes_xyxy, yolo_box_classes,
                    )
                return annotated, 0.0, 0, f"C{slot}->{model_config.name}: no object", [], []
            except Exception as exc:
                annotated = self.draw_placeholder_annotation(display_frame.copy(), slot, model_config.name, f"YOLO error: {exc}")
                return annotated, 0.0, 0, f"C{slot}->{model_config.name}: YOLO error", [], []

        confidence = random.uniform(0.82, 0.96)
        annotated = self.draw_placeholder_annotation(display_frame.copy(), slot, model_config.name, f"placeholder {confidence:.2f}")
        return annotated, confidence, 1, f"C{slot}->{model_config.name}: placeholder", [], []

    @staticmethod
    def _box_class_name(box, names):
        if getattr(box, "cls", None) is None:
            return ""
        try:
            class_id = int(box.cls[0].detach().cpu().item())
        except Exception:
            return ""
        if isinstance(names, dict):
            return str(names.get(class_id, class_id))
        return str(class_id)

    def draw_yolo_annotations(self, frame, result, model_name):
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return frame

        names = getattr(result, "names", {}) or {}
        for box in boxes:
            coords = box.xyxy[0].detach().cpu().tolist()
            x1, y1, x2, y2 = [int(value) for value in coords]
            confidence = float(box.conf[0].detach().cpu().item()) if getattr(box, "conf", None) is not None else 0.0
            class_id = int(box.cls[0].detach().cpu().item()) if getattr(box, "cls", None) is not None else -1
            label = names.get(class_id, str(class_id)) if isinstance(names, dict) else str(class_id)
            color = hex_to_bgr(self.yolo_color_for_model(model_name))

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
            cv2.putText(
                frame,
                f"{label} {confidence:.2f}",
                (x1, max(14, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                color,
                1,
            )
        return frame

    def yolo_color_for_model(self, model_name):
        overlay = self.state.region_overlay
        model_colors = getattr(overlay, "yolo_model_colors", {})
        if isinstance(model_colors, dict):
            color = model_colors.get(model_name)
            if color:
                return color
        return getattr(overlay, "yolo_color", "#22c55e")

    def decision_rule_for(self, slot, model_name):
        default_threshold = getattr(self.state.decision, "pass_confidence_threshold", 0.5)
        default_rule = {
            "confidence_threshold": default_threshold,
            "required_object_count": 1,
        }
        rules = getattr(self.state.decision, "model_rules", {})
        if not isinstance(rules, dict):
            return default_rule
        rule = rules.get(_rule_key(slot, model_name), {})
        if not isinstance(rule, dict):
            return default_rule
        if getattr(self.state.decision, "confidence_threshold_mode", "custom") == "global":
            return {
                "confidence_operator": ">=",
                "confidence_threshold": default_threshold,
                "required_object_count_operator": rule.get("required_object_count_operator", "="),
                "required_object_count": rule.get("required_object_count", 1),
            }
        return {
            "confidence_operator": rule.get("confidence_operator", ">="),
            "confidence_threshold": rule.get("confidence_threshold", default_threshold),
            "required_object_count_operator": rule.get("required_object_count_operator", "="),
            "required_object_count": rule.get("required_object_count", 1),
        }

    def group_rule_for(self, group_id):
        rules = getattr(self.state.decision, "group_rules", {})
        rule = rules.get(str(group_id), {})
        return {
            "required": bool(rule.get("required", True)),
            "mode": "any",
        }

    def clear_model_cache(self):
        self.loaded_models.clear()
        self._load_errors.clear()

    def load_yolo_model(self, path):
        if not path:
            return None
        if path in self.loaded_models:
            return self.loaded_models[path]
        if path in self._load_errors:
            return None
        if self.ultralytics_available is False:
            return None
        try:
            from ultralytics import YOLO

            self.ultralytics_available = True
            model = YOLO(path)
            self.loaded_models[path] = model
            return model
        except ImportError:
            self.ultralytics_available = False
            return None
        except Exception:
            self._load_errors.add(path)
            return None

    def draw_placeholder_annotation(self, frame, slot, model_name, label):
        height, width = frame.shape[:2]
        x1 = max(20, width // 5)
        y1 = max(20, height // 5)
        x2 = min(width - 20, x1 + width // 2)
        y2 = min(height - 20, y1 + height // 3)
        color = hex_to_bgr(self.yolo_color_for_model(model_name))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        cv2.putText(
            frame,
            f"C{slot} {model_name}",
            (x1, max(16, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
        )
        cv2.putText(
            frame,
            label,
            (x1, min(height - 12, y2 + 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            color,
            1,
        )
        return frame
