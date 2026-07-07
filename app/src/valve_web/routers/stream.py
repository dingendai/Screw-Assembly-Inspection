"""Live camera streaming and snapshot endpoints (mirrors MonitorPage preview)."""

import asyncio

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from valve_web.deps import require_login
from valve_web.overlay import draw_region_overlay, encode_jpeg
from valve_web.state import WebContext

router = APIRouter(prefix="/api", tags=["stream"])

_BOUNDARY = "frame"
_STREAM_INTERVAL = 0.06  # ~16 fps; low enough to keep CPU/connections sane


def _camera_by_slot(ctx: WebContext, slot: int):
    for camera in ctx.state.inspection_cameras:
        if camera.slot == slot:
            return camera
    return None


def _placeholder(message: str):
    frame = np.zeros((360, 480, 3), dtype=np.uint8)
    frame[:] = (40, 40, 48)
    cv2.putText(frame, message, (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    return frame


def _compose_frame(ctx: WebContext, slot: int):
    """Build the JPEG bytes for one slot (runs off the event loop)."""
    frame = ctx.cameras.latest_frame(slot)
    if frame is None:
        frame = _placeholder(f"相機 {slot}: no frame")
    else:
        annotated = None
        if ctx.continuous and ctx.latest_result:
            annotated = ctx.latest_result.get("_annotated", {}).get(slot)
        if annotated is not None:
            frame = annotated
        else:
            camera = _camera_by_slot(ctx, slot)
            if camera is not None:
                frame = draw_region_overlay(frame, camera, ctx.state.region_overlay)
    return encode_jpeg(frame)


@router.get("/cameras/status")
def camera_status(ctx: WebContext = Depends(require_login)):
    ctx.cameras.ensure_started(ctx.state)
    return {"active_slots": ctx.cameras.active_slots(), "status": ctx.cameras.status()}


@router.get("/snapshot/{slot}")
def snapshot(slot: int, overlay: bool = True, ctx: WebContext = Depends(require_login)):
    ctx.cameras.ensure_started(ctx.state)
    frame = ctx.cameras.latest_frame(slot)
    if frame is None:
        frame = _placeholder(f"相機 {slot}: no frame")
    elif overlay:
        camera = _camera_by_slot(ctx, slot)
        if camera is not None:
            frame = draw_region_overlay(frame, camera, ctx.state.region_overlay)
    data = encode_jpeg(frame)
    if not data:
        raise HTTPException(status_code=500, detail="影像編碼失敗")
    return Response(content=data, media_type="image/jpeg")


@router.get("/stream/{slot}")
async def stream(slot: int, request: Request, ctx: WebContext = Depends(require_login)):
    ctx.cameras.ensure_started(ctx.state)

    async def generate():
        while True:
            # Stop promptly when the browser closes the <img> connection so we
            # don't leak threads/connections (the main cause of UI freezes).
            if await request.is_disconnected():
                break
            data = await run_in_threadpool(_compose_frame, ctx, slot)
            if data:
                yield (
                    b"--" + _BOUNDARY.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                )
            await asyncio.sleep(_STREAM_INTERVAL)

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
