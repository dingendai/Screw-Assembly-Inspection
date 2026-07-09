from dataclasses import dataclass, field

import cv2
import numpy as np


LOCK_GEOMETRY_MODES = {"gap", "dark", "both"}


@dataclass
class LockGeometryRegion:
    x: int
    y: int
    w: int
    h: int
    base_line_y: int | None = None
    red_line_y: int | None = None
    split_line_y: int | None = None
    gap_threshold_px: int = 6
    dark_threshold_ratio: float = 0.25
    dark_gray_threshold: int = 70
    mode: str = "both"
    metal_edge_count: int = 1


@dataclass
class LockGeometryResult:
    prediction: str
    gap_px: int | None
    dark_ratio: float
    dark_pixels: int
    total_pixels: int
    metal_edge_y: int | None
    base_line_y: int | None
    reason: str
    metal_edge_ys: list[int] = field(default_factory=list)
    red_line_y: int | None = None
    split_line_y: int | None = None
    red_zone_violation: bool = False


@dataclass
class LockGeometryAnalysis:
    region_config: dict
    region: LockGeometryRegion
    result: LockGeometryResult


def clamp_float(value, fallback=0.0, minimum=0.0, maximum=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def clamp_int(value, fallback=0, minimum=0, maximum=255):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def normalise_line_ratio(value):
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def normalised_region_to_lock_roi(region: dict, frame_width: int, frame_height: int) -> LockGeometryRegion:
    x = clamp_float(region.get("x", 0.0))
    y = clamp_float(region.get("y", 0.0))
    w = clamp_float(region.get("w", 0.0), 0.0, 0.0, 1.0 - x)
    h = clamp_float(region.get("h", 0.0), 0.0, 0.0, 1.0 - y)
    x1 = max(0, min(frame_width - 1, int(x * frame_width)))
    y1 = max(0, min(frame_height - 1, int(y * frame_height)))
    x2 = max(x1 + 1, min(frame_width, int((x + w) * frame_width)))
    y2 = max(y1 + 1, min(frame_height, int((y + h) * frame_height)))
    roi_h = max(1, y2 - y1)

    return LockGeometryRegion(
        x=x1,
        y=y1,
        w=max(1, x2 - x1),
        h=roi_h,
        base_line_y=line_ratio_to_roi_y(region.get("base_line_y"), roi_h),
        red_line_y=line_ratio_to_roi_y(region.get("red_line_y"), roi_h),
        split_line_y=line_ratio_to_roi_y(region.get("split_line_y"), roi_h, minimum=1),
        gap_threshold_px=clamp_int(region.get("gap_threshold_px", 6), 6, 0, 500),
        dark_threshold_ratio=clamp_float(region.get("dark_threshold_ratio", 0.25), 0.25),
        dark_gray_threshold=clamp_int(region.get("dark_gray_threshold", 70), 70, 0, 255),
        mode=normalise_mode(region.get("mode", "both")),
        metal_edge_count=clamp_int(region.get("metal_edge_count", 1), 1, 1, 5),
    )


def line_ratio_to_roi_y(value, roi_height: int, minimum=0):
    ratio = normalise_line_ratio(value)
    if ratio is None:
        return None
    return max(minimum, min(roi_height - 1, int(ratio * roi_height)))


def roi_y_to_frame_y(roi: LockGeometryRegion, roi_y: int | None):
    if roi_y is None:
        return None
    return roi.y + max(0, min(roi.h - 1, int(roi_y)))


def normalise_mode(value):
    mode = str(value).strip().lower()
    return mode if mode in LOCK_GEOMETRY_MODES else "both"


def clamp_roi(roi: LockGeometryRegion, frame_shape) -> LockGeometryRegion:
    height, width = frame_shape[:2]
    x = max(0, min(width - 1, int(roi.x)))
    y = max(0, min(height - 1, int(roi.y)))
    w = max(1, min(width - x, int(roi.w)))
    h = max(1, min(height - y, int(roi.h)))
    base_line_y = None if roi.base_line_y is None else max(0, min(h - 1, int(roi.base_line_y)))
    red_line_y = None if roi.red_line_y is None else max(0, min(h - 1, int(roi.red_line_y)))
    split_line_y = None if roi.split_line_y is None else max(1, min(h - 1, int(roi.split_line_y)))
    return LockGeometryRegion(
        x=x,
        y=y,
        w=w,
        h=h,
        base_line_y=base_line_y,
        red_line_y=red_line_y,
        split_line_y=split_line_y,
        gap_threshold_px=max(0, int(roi.gap_threshold_px)),
        dark_threshold_ratio=max(0.0, min(1.0, float(roi.dark_threshold_ratio))),
        dark_gray_threshold=max(0, min(255, int(roi.dark_gray_threshold))),
        mode=normalise_mode(roi.mode),
        metal_edge_count=max(1, min(5, int(roi.metal_edge_count))),
    )


def strongest_edge_rows(row_scores, count: int, min_distance: int = 4) -> list[int]:
    count = max(1, int(count))
    ranked = sorted(
        ((int(score), int(index)) for index, score in enumerate(row_scores) if int(score) > 0),
        reverse=True,
    )
    selected: list[int] = []
    for _score, index in ranked:
        if all(abs(index - existing) >= min_distance for existing in selected):
            selected.append(index)
        if len(selected) >= count:
            break
    return selected


def analyze_lock_state(frame, roi: LockGeometryRegion) -> LockGeometryResult:
    try:
        roi = clamp_roi(roi, frame.shape)
        crop = frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]
        if crop.size == 0 or roi.w < 4 or roi.h < 8:
            return unknown_result("幾何 ROI 過小或沒有有效影像")

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        dark = gray < int(roi.dark_gray_threshold)
        dark_pixels = int(dark.sum())
        total_pixels = int(dark.size)
        dark_ratio = dark_pixels / total_pixels if total_pixels else 0.0

        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        row_scores = edges.sum(axis=1)
        metal_edge_y = None
        metal_edge_ys: list[int] = []
        base_line_y = roi.base_line_y
        red_line_y = roi.red_line_y
        split_line_y = max(1, min(roi.h - 1, int(roi.split_line_y if roi.split_line_y is not None else roi.h // 2)))
        gap_px = None
        red_zone_violation = False

        if int(row_scores.max()) <= 0:
            return LockGeometryResult(
                prediction="unknown",
                gap_px=None,
                dark_ratio=dark_ratio,
                dark_pixels=dark_pixels,
                total_pixels=total_pixels,
                metal_edge_y=None,
                base_line_y=base_line_y,
                reason="沒有找到可用水平邊緣",
                red_line_y=red_line_y,
                split_line_y=split_line_y,
            )

        upper = row_scores[:split_line_y]
        lower = row_scores[split_line_y:]
        if upper.size and int(upper.max()) > 0:
            metal_edge_ys = strongest_edge_rows(upper, roi.metal_edge_count)
            if metal_edge_ys:
                metal_edge_y = metal_edge_ys[0]
        if base_line_y is None and lower.size and int(lower.max()) > 0:
            base_line_y = int(split_line_y + np.argmax(lower))
        if metal_edge_ys and base_line_y is not None:
            metal_edge_y = min(metal_edge_ys, key=lambda y: abs(base_line_y - y))
            gap_px = abs(base_line_y - metal_edge_y)

        if red_line_y is not None and metal_edge_ys:
            red_zone_violation = any(edge_y <= red_line_y for edge_y in metal_edge_ys)

        gap_separated = gap_px is not None and gap_px > int(roi.gap_threshold_px)
        dark_separated = dark_ratio > float(roi.dark_threshold_ratio)
        if roi.mode == "gap":
            separated = gap_separated
        elif roi.mode == "dark":
            separated = dark_separated
        else:
            separated = gap_separated or dark_separated
        if red_zone_violation:
            separated = True

        if roi.mode in {"gap", "both"} and gap_px is None:
            prediction = "unknown"
            reason = "需要間隙判斷但無法取得金屬邊緣或基準線"
        else:
            prediction = "separated" if separated else "locked"
            reason = (
                f"gap {gap_px if gap_px is not None else '--'}px / "
                f"dark {dark_ratio:.3f} / "
                f"gap threshold {roi.gap_threshold_px} / "
                f"dark threshold {roi.dark_threshold_ratio:.3f}"
            )
            if red_zone_violation:
                reason = f"{reason} / red line violation"

        return LockGeometryResult(
            prediction=prediction,
            gap_px=gap_px,
            dark_ratio=dark_ratio,
            dark_pixels=dark_pixels,
            total_pixels=total_pixels,
            metal_edge_y=metal_edge_y,
            base_line_y=base_line_y,
            reason=reason,
            metal_edge_ys=metal_edge_ys,
            red_line_y=red_line_y,
            split_line_y=split_line_y,
            red_zone_violation=red_zone_violation,
        )
    except Exception as exc:
        return unknown_result(f"幾何分析失敗：{exc}")


def unknown_result(reason: str) -> LockGeometryResult:
    return LockGeometryResult(
        prediction="unknown",
        gap_px=None,
        dark_ratio=0.0,
        dark_pixels=0,
        total_pixels=0,
        metal_edge_y=None,
        base_line_y=None,
        reason=reason,
    )


def analyze_lock_geometry_regions(frame, regions: list[dict]) -> list[LockGeometryAnalysis]:
    height, width = frame.shape[:2]
    analyses = []
    for region in regions:
        if not bool(region.get("enabled", True)):
            continue
        roi = normalised_region_to_lock_roi(region, width, height)
        result = analyze_lock_state(frame, roi)
        analyses.append(LockGeometryAnalysis(region_config=region, region=roi, result=result))
    return analyses


def geometry_summary(region: dict, result: LockGeometryResult) -> str:
    name = str(region.get("name") or region.get("id") or "ROI").strip()
    return (
        f"幾何 {name}: {result.prediction} / "
        f"gap {result.gap_px if result.gap_px is not None else '--'}px / "
        f"dark {result.dark_ratio:.3f} / {result.reason}"
    )


def draw_lock_geometry_overlay(frame, analyses: list[LockGeometryAnalysis], show_result=True):
    for index, analysis in enumerate(analyses, start=1):
        roi = analysis.region
        result = analysis.result
        if show_result and result.prediction == "locked":
            frame_color = (34, 197, 94)
        else:
            frame_color = (36, 36, 240)
        x1, y1, x2, y2 = roi.x, roi.y, roi.x + roi.w, roi.y + roi.h
        cv2.rectangle(frame, (x1, y1), (x2, y2), frame_color, 1)
        cv2.putText(
            frame,
            f"ROI {index}",
            (x1 + 4, max(14, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            frame_color,
            1,
        )

        split_y = roi_y_to_frame_y(roi, result.split_line_y if result.split_line_y is not None else roi.split_line_y)
        if split_y is not None:
            cv2.line(frame, (x1, split_y), (x2, split_y), (220, 220, 220), 1)
        red_y = roi_y_to_frame_y(roi, result.red_line_y)
        if red_y is not None:
            cv2.line(frame, (x1, red_y), (x2, red_y), (0, 0, 255), 1)
        for edge_y in result.metal_edge_ys:
            y = roi_y_to_frame_y(roi, edge_y)
            if y is not None:
                cv2.line(frame, (x1, y), (x2, y), (255, 160, 0), 1)
        base_y = roi_y_to_frame_y(roi, result.base_line_y)
        if base_y is not None:
            cv2.line(frame, (x1, base_y), (x2, base_y), (0, 255, 255), 1)
    return frame


def draw_lock_geometry_config_overlay(frame, regions: list[dict]):
    height, width = frame.shape[:2]
    analyses = []
    for region in regions:
        if not bool(region.get("enabled", True)):
            continue
        roi = normalised_region_to_lock_roi(region, width, height)
        result = LockGeometryResult(
            prediction="設定",
            gap_px=None,
            dark_ratio=0.0,
            dark_pixels=0,
            total_pixels=0,
            metal_edge_y=None,
            base_line_y=roi.base_line_y,
            reason="",
            red_line_y=roi.red_line_y,
            split_line_y=roi.split_line_y,
        )
        analyses.append(LockGeometryAnalysis(region_config=region, region=roi, result=result))
    return draw_lock_geometry_overlay(frame, analyses, show_result=False)
