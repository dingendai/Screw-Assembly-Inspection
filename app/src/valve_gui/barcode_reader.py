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


def _position_to_dict(position) -> dict | None:
    """把 zxing-cpp 的四角座標物件轉成可序列化的 dict。"""
    if position is None:
        return None
    corners = {}
    for name in ("top_left", "top_right", "bottom_right", "bottom_left"):
        point = getattr(position, name, None)
        if point is None:
            continue
        try:
            corners[name] = [int(point.x), int(point.y)]
        except Exception:
            continue
    return corners or None


def decode_frame(frame) -> list[dict]:
    """輸入 BGR 影像，回傳本幀解到的條碼清單。

    每筆為 ``{"text", "format", "valid", "position"}``。
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
        results = []
        for r in zxingcpp.read_barcodes(gray):
            if not r.text:
                continue
            results.append(
                {
                    "text": r.text,
                    "format": str(r.format),
                    "valid": bool(r.valid),
                    "position": _position_to_dict(r.position),
                }
            )
        return results
    except Exception:  # 解碼過程任何例外都不該中斷檢驗流程
        logger.exception("條碼解碼發生例外")
        return []


def decode_best(frame, require_valid: bool = True) -> str | None:
    """從一幀影像取出最可信的單一條碼文字。

    預設只採用校驗碼通過（``valid=True``）的條碼，過濾印壞/反光/半遮的髒碼；
    取畫面中第一個符合條件者。解不到回 ``None``。
    """
    for item in decode_frame(frame):
        if require_valid and not item["valid"]:
            continue
        text = item["text"].strip()
        if text:
            return text
    return None
