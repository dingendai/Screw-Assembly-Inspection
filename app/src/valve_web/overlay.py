"""Region overlay drawing, ported as pure functions from valve_gui MonitorPage.

Kept UI-agnostic so both MJPEG streams and snapshots can reuse it.
"""

import cv2

from valve_gui.camera import normalised_region_to_pixels
from valve_gui.utils import hex_to_bgr


def _draw_region_list(frame, regions, color, label, width, height):
    for index, region in enumerate(regions, start=1):
        x1, y1, x2, y2 = normalised_region_to_pixels(region, width, height)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f"{label}{index}",
            (x1 + 4, max(16, y1 + 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )


def draw_region_overlay(frame, camera, region_overlay):
    """Overlay detection/exclusion regions onto a copy of ``frame``."""
    if not getattr(region_overlay, "show_on_monitor", True):
        return frame
    if not getattr(camera, "region_detection_enabled", False):
        return frame
    if not camera.detection_regions and not camera.exclusion_regions:
        return frame
    annotated = frame.copy()
    height, width = annotated.shape[:2]
    _draw_region_list(
        annotated, camera.detection_regions, hex_to_bgr(region_overlay.detection_color), "ROI", width, height
    )
    _draw_region_list(
        annotated, camera.exclusion_regions, hex_to_bgr(region_overlay.exclusion_color), "EX", width, height
    )
    return annotated


def encode_jpeg(frame, quality: int = 80) -> bytes:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return b""
    return buffer.tobytes()
