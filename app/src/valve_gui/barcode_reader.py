"""影像條碼辨識（電腦視覺即時讀取條碼）。

對應 BARCODE_VISION_REQUIREMENTS.md：用一般攝影機影像 + zxing-cpp 解碼，
不需專用掃描槍。核心兩步：BGR 影像 → 轉灰階 → zxing-cpp 解碼。

zxing-cpp 採容錯匯入：套件未安裝時本模組仍可載入，解碼一律回空清單並記一次
警告，避免未裝套件就讓整個 Web/桌面程式起不來。
"""

import logging

import cv2

logger = logging.getLogger(__name__)

try:  # 容錯匯入：缺套件不應讓整個 app 無法啟動
    import zxingcpp

    _IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - 視執行環境而定
    zxingcpp = None
    _IMPORT_ERROR = str(exc)

_warned_missing = False


def is_available() -> bool:
    """zxing-cpp 是否可用（套件已安裝且匯入成功）。"""
    return zxingcpp is not None


def _warn_missing_once() -> None:
    global _warned_missing
    if not _warned_missing:
        _warned_missing = True
        logger.warning(
            "未安裝 zxing-cpp，條碼辨識停用。請 `pip install zxing-cpp`。原因：%s",
            _IMPORT_ERROR or "import 失敗",
        )


def _position_to_dict(position, *, scale: float = 1.0, offset_x: int = 0, offset_y: int = 0) -> dict | None:
    """把 zxing-cpp 四角座標映射回原始 frame 並轉成可序列化 dict。"""
    if position is None:
        return None
    corners = {}
    for name in ("top_left", "top_right", "bottom_right", "bottom_left"):
        point = getattr(position, name, None)
        if point is None:
            continue
        try:
            mapped_x = offset_x + float(point.x) / scale
            mapped_y = offset_y + float(point.y) / scale
            corners[name] = [max(0, int(round(mapped_x))), max(0, int(round(mapped_y)))]
        except Exception:
            continue
    return corners or None


def _read_barcodes(gray, *, source="full_frame", roi_index=None, scale=1.0, offset_x=0, offset_y=0) -> list[dict]:
    results = []
    for r in zxingcpp.read_barcodes(gray):
        text = str(getattr(r, "text", "") or "").strip()
        if not text:
            continue
        results.append(
            {
                "text": text,
                "format": str(getattr(r, "format", "")),
                "valid": bool(getattr(r, "valid", False)),
                "position": _position_to_dict(
                    getattr(r, "position", None),
                    scale=scale,
                    offset_x=offset_x,
                    offset_y=offset_y,
                ),
                "source": source,
                "roi_index": roi_index,
                "scale": float(scale),
            }
        )
    return results


def _enhanced_decode_candidates(gray):
    height, width = gray.shape[:2]
    rois = [
        (0, int(height * 0.20), width, int(height * 0.42), 2.5),
        (int(width * 0.18), int(height * 0.18), int(width * 0.64), int(height * 0.50), 3.0),
        (int(width * 0.28), int(height * 0.25), int(width * 0.46), int(height * 0.36), 4.0),
    ]
    for roi_index, (x, y, roi_w, roi_h, scale) in enumerate(rois):
        x1 = max(0, min(width, int(x)))
        y1 = max(0, min(height, int(y)))
        x2 = max(x1, min(width, int(x + roi_w)))
        y2 = max(y1, min(height, int(y + roi_h)))
        if x2 <= x1 or y2 <= y1:
            continue
        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        up = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        yield up, scale, x1, y1, roi_index

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(up)
        yield clahe, scale, x1, y1, roi_index

        blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
        sharp = cv2.addWeighted(clahe, 1.7, blur, -0.7, 0)
        yield sharp, scale, x1, y1, roi_index

        _, otsu = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        yield otsu, scale, x1, y1, roi_index


def _dedupe_detections(detections):
    deduped = []
    seen = set()
    for item in detections:
        key = (item.get("text", ""), item.get("format", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _filter_valid(detections, require_valid):
    if not require_valid:
        return detections
    return [item for item in detections if item.get("valid")]


def decode_frame(frame, *, enhance: bool = True, require_valid: bool = False) -> list[dict]:
    """輸入 BGR 影像，回傳本幀解到的條碼清單。

    每筆為 ``{"text", "format", "valid", "position", "source", "roi_index", "scale"}``。
    解碼失敗 / 套件未安裝 / 影像為 None 時回空清單。
    """
    if frame is None:
        return []
    if zxingcpp is None:
        _warn_missing_once()
        return []
    try:
        if frame.ndim == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame
        full_frame_results = _read_barcodes(gray)
        if full_frame_results or not enhance:
            return _filter_valid(_dedupe_detections(full_frame_results), require_valid)

        enhanced_results = []
        for candidate, scale, offset_x, offset_y, roi_index in _enhanced_decode_candidates(gray):
            enhanced_results.extend(
                _read_barcodes(
                    candidate,
                    source="enhanced_roi",
                    roi_index=roi_index,
                    scale=scale,
                    offset_x=offset_x,
                    offset_y=offset_y,
                )
            )
            if enhanced_results:
                break
        return _filter_valid(_dedupe_detections(enhanced_results), require_valid)
    except Exception:  # 解碼過程任何例外都不該中斷檢驗流程
        logger.exception("條碼解碼發生例外")
        return []


def decode_best(frame, require_valid: bool = True, enhance: bool = True) -> str | None:
    """從一幀影像取出最可信的單一條碼文字。

    預設只採用校驗碼通過（``valid=True``）的條碼，過濾印壞/反光/半遮的髒碼；
    取畫面中第一個符合條件者。解不到回 ``None``。
    """
    for item in decode_frame(frame, enhance=enhance, require_valid=require_valid):
        if require_valid and not item["valid"]:
            continue
        text = item["text"].strip()
        if text:
            return text
    return None
