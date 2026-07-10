"""Inspection endpoints (mirrors MonitorPage detection flow)."""

import base64
import threading
import time
from datetime import datetime

from fastapi import APIRouter, Depends

from valve_gui import qc_db
from valve_gui.model_registry import format_camera_model_names
from valve_gui.models import InspectionRecord
from valve_gui.paths import DATA_DIR, RECORDS_LOG_PATH, RECORD_EVENTS_LOG_PATH
from valve_gui.permissions import PERMISSION_OPEN_MONITOR
from valve_gui.storage import append_record_csv, append_record_event_csv, save_qc_object_snapshot, upsert_record_list

from valve_web.deps import require_permission
from valve_web.overlay import encode_jpeg
from valve_web.state import WebContext

router = APIRouter(prefix="/api", tags=["inspect"])

_monitor_dep = require_permission(PERMISSION_OPEN_MONITOR)
_continuous_thread: threading.Thread | None = None
_continuous_stop = threading.Event()
_continuous_lock = threading.Lock()


def _enabled_cameras(ctx: WebContext):
    return [c for c in ctx.state.inspection_cameras if c.enabled]


def _add_record(ctx: WebContext, record: InspectionRecord, *, raw_frames=None, annotated_frames=None, inference=None):
    upsert_record_list(ctx.state.records, record)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    append_record_csv(RECORDS_LOG_PATH, record)
    append_record_event_csv(RECORD_EVENTS_LOG_PATH, record)
    # SQLite 為品管查詢/統計的單一真相；CSV 暫時保留作過渡。
    inspection_id = None
    if record.result in ("PASS", "NG") and record.part_id.strip():
        try:
            inspection_id = qc_db.record_inspection(
                record.part_id.strip(),
                record.result,
                note=record.note,
                operator=record.operator_name,
                operator_role=record.operator_role,
                confidence=record.confidence,
                active_cameras=record.active_cameras,
                inspected_at=record.timestamp,
                session_id=ctx.state.current_work_session_id,
                source=getattr(record, "barcode_source", ""),
            )
        except Exception:
            # 入庫失敗不應中斷檢驗流程（CSV 已寫入）。
            pass
        try:
            save_qc_object_snapshot(
                record,
                login_time=ctx.state.login_time,
                raw_frames=raw_frames,
                annotated_frames=annotated_frames,
                camera_results=getattr(inference, "camera_results", {}) if inference else {},
                roi_confirmations=getattr(inference, "roi_confirmations", {}) if inference else {},
                inspection_id=inspection_id,
            )
        except Exception:
            pass


def _record_from(ctx: WebContext, inference, part_id: str, source: str = "") -> InspectionRecord:
    active = ",".join(
        f"C{c.slot}:D{c.device_index}:M{format_camera_model_names(c)}" for c in _enabled_cameras(ctx)
    )
    return InspectionRecord(
        timestamp=f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        operator_name=ctx.state.operator_name,
        operator_role=ctx.state.operator_role,
        result=inference.result,
        part_id=part_id.strip() or f"PART-{datetime.now():%H%M%S}",
        active_cameras=active,
        confidence=f"{inference.confidence:.3f}",
        note=inference.note,
        barcode_source=source,
    )


def _result_payload(inference, include_images: bool = True) -> dict:
    payload = {
        "result": inference.result,
        "confidence": round(inference.confidence, 3),
        "note": inference.note,
        "camera_results": inference.camera_results,
        "roi_confirmations": inference.roi_confirmations,
        "timestamp": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
    }
    if include_images:
        images = {}
        for slot, frame in inference.annotated_frames.items():
            data = encode_jpeg(frame)
            if data:
                images[str(slot)] = "data:image/jpeg;base64," + base64.b64encode(data).decode()
        payload["annotated"] = images
    # Keep raw annotated frames for the MJPEG stream (not serialised to client).
    payload["_annotated"] = dict(inference.annotated_frames)
    return payload


def _run_once(ctx: WebContext, part_id: str, record: bool, throttle: bool, include_images: bool = True) -> dict:
    ctx.cameras.ensure_started(ctx.state)
    frames = ctx.cameras.frames_by_slot()
    inference = ctx.router.run(frames)
    record_mode = getattr(ctx.state.inspection_workflow, "record_mode", "continuous")
    if part_id.strip():
        effective_part_id = part_id
        source = "manual"
    else:
        effective_part_id = ""
        source = "auto"
    record_signature = (effective_part_id.strip() or source, inference.result)
    if record:
        do_record = True
        if throttle and record_mode == "continuous" and inference.result != "NG":
            now = time.time()
            last = getattr(ctx, "_last_record_time", 0.0)
            if now - last < 5.0:
                do_record = False
            else:
                ctx._last_record_time = now
        elif throttle and record_mode == "per_result":
            if record_signature == getattr(ctx, "_last_record_signature", None):
                do_record = False
            else:
                ctx._last_record_signature = record_signature
        if do_record:
            _add_record(
                ctx,
                _record_from(ctx, inference, effective_part_id, source),
                raw_frames=getattr(inference, "raw_frames", frames),
                annotated_frames=getattr(inference, "annotated_frames", {}),
                inference=inference,
            )
    payload = _result_payload(inference, include_images=include_images)
    with ctx.lock:
        ctx.latest_result = payload
    return payload


@router.post("/inspect")
def inspect(ctx: WebContext = Depends(_monitor_dep), part_id: str = ""):
    payload = _run_once(ctx, part_id, record=True, throttle=False)
    return {k: v for k, v in payload.items() if not k.startswith("_")}


@router.get("/results/latest")
def latest(ctx: WebContext = Depends(_monitor_dep)):
    with ctx.lock:
        payload = ctx.latest_result
    if not payload:
        return {"result": None}
    return {k: v for k, v in payload.items() if not k.startswith("_")}


def _continuous_loop(ctx: WebContext, part_id: str):
    # Continuous mode is viewed live via the MJPEG stream (which uses the raw
    # annotated frames), so we skip the costly base64 image encoding here.
    while not _continuous_stop.is_set():
        try:
            _run_once(ctx, part_id, record=True, throttle=True, include_images=False)
        except Exception:
            pass
        _continuous_stop.wait(0.5)


@router.post("/inspect/continuous/start")
def continuous_start(ctx: WebContext = Depends(_monitor_dep), part_id: str = ""):
    global _continuous_thread
    with _continuous_lock:
        if ctx.continuous and _continuous_thread and _continuous_thread.is_alive():
            return {"continuous": True}
        _continuous_stop.set()
        if _continuous_thread and _continuous_thread.is_alive():
            _continuous_thread.join(timeout=1.0)
        _continuous_stop.clear()
        ctx.continuous = True
        ctx._last_record_time = 0.0
        ctx._last_record_signature = None
        _continuous_thread = threading.Thread(
            target=_continuous_loop, args=(ctx, part_id), name="continuous-inspect", daemon=True
        )
        _continuous_thread.start()
    return {"continuous": True}


@router.post("/inspect/continuous/stop")
def continuous_stop(ctx: WebContext = Depends(_monitor_dep)):
    global _continuous_thread
    with _continuous_lock:
        _continuous_stop.set()
        ctx.continuous = False
        ctx._last_record_time = 0.0
        ctx._last_record_signature = None
        if _continuous_thread:
            _continuous_thread.join(timeout=1.0)
            _continuous_thread = None
    return {"continuous": False}
