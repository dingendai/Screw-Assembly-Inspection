"""Authentication endpoints (mirrors valve_gui LoginPage)."""

import asyncio
from datetime import datetime

import cv2
import numpy as np
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from valve_gui.camera import detect_camera_indexes
from valve_gui.paths import PHOTOS_DIR
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_DEVELOPER,
    has_permission,
    role_label,
    role_options,
)
from valve_gui.utils import verify_password

from valve_web import session
from valve_web.deps import require_login
from valve_web.overlay import encode_jpeg
from valve_web.schemas import LoginRequest
from valve_web.state import WebContext, get_context

router = APIRouter(prefix="/api", tags=["auth"])


def _permission_map(ctx: WebContext, role: str) -> dict:
    return {perm: has_permission(role, perm, ctx.state.role_permissions) for perm in CONFIGURABLE_PERMISSIONS}


@router.get("/roles")
def get_roles():
    ctx = get_context()
    return {
        "roles": [{"value": value, "label": label} for value, label in role_options(ctx.state.role_labels)],
        "permission_labels": PERMISSION_LABELS,
        "developer_role": ROLE_DEVELOPER,
        "operator_camera_index": int(ctx.state.operator_camera_index),
    }


@router.post("/login")
def login(req: LoginRequest, response: Response):
    ctx = get_context()
    role = req.role.strip()
    if role not in ctx.state.role_labels:
        raise HTTPException(status_code=400, detail="未知的角色")

    stored = ctx.state.role_passwords.get(role, "")
    if stored and not verify_password(req.password, stored):
        raise HTTPException(status_code=401, detail=f"{role_label(role, ctx.state.role_labels)}密鑰不正確。")

    if role == ROLE_DEVELOPER:
        name = req.name.strip() or "Developer"
        photo_path = ""
    else:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="請輸入操作者姓名。")
        photo_path = req.photo_path.strip()

    token = session.login(ctx.state, name, role, photo_path)
    response.set_cookie(key=session.COOKIE_NAME, value=token, httponly=True, samesite="lax")
    ctx.operator.stop()
    ctx.cameras.restart(ctx.state)
    return _me_payload(ctx)


@router.post("/logout")
def logout(response: Response, valve_web_session: str | None = Cookie(default=None)):
    ctx = get_context()
    session.logout(ctx.state, valve_web_session)
    ctx.cameras.stop_all()
    ctx.operator.stop()
    response.delete_cookie(key=session.COOKIE_NAME)
    return {"ok": True}


def _me_payload(ctx: WebContext) -> dict:
    state = ctx.state
    return {
        "logged_in": state.is_logged_in,
        "operator_name": state.operator_name,
        "operator_role": state.operator_role,
        "role_label": role_label(state.operator_role, state.role_labels),
        "login_time": state.login_time,
        "settings_applied": state.settings_applied,
        "is_developer": state.operator_role == ROLE_DEVELOPER,
        "permissions": _permission_map(ctx, state.operator_role),
        "font_size": getattr(state.display, "font_size", 14),
    }


@router.get("/me")
def me(ctx: WebContext = Depends(require_login)):
    return _me_payload(ctx)


# ---- operator camera preview (login page) ----

def _operator_index(ctx, index: int | None) -> int:
    return int(index) if index is not None else int(ctx.state.operator_camera_index)


@router.get("/operator/cameras")
async def operator_cameras():
    """Scan for connected cameras so the login page can pick one (pre-login)."""
    ctx = get_context()
    ctx.cameras.stop_all()
    ctx.operator.stop()
    found = await run_in_threadpool(detect_camera_indexes, 12)
    return {"cameras": found, "current": int(ctx.state.operator_camera_index)}


@router.post("/operator/preview/start")
def operator_preview_start(index: int | None = None):
    """Open a chosen camera for a live login-page preview (pre-login)."""
    ctx = get_context()
    ctx.cameras.stop_all()  # free inspection devices first
    ctx.operator.start(_operator_index(ctx, index), ctx.state.use_simulation)
    return {"ok": True}


@router.post("/operator/preview/stop")
def operator_preview_stop():
    get_context().operator.stop()
    return {"ok": True}


def _operator_placeholder(message: str):
    frame = np.zeros((360, 480, 3), dtype=np.uint8)
    frame[:] = (40, 40, 48)
    cv2.putText(frame, message, (20, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    return frame


@router.get("/operator/stream")
async def operator_stream(request: Request, index: int | None = None):
    ctx = get_context()
    ctx.operator.start(_operator_index(ctx, index), ctx.state.use_simulation)

    async def generate():
        while not await request.is_disconnected():
            frame = ctx.operator.latest()
            if frame is None:
                frame = _operator_placeholder("operator camera: no frame")
            data = await run_in_threadpool(encode_jpeg, frame)
            if data:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(0.06)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/operator-photo")
async def operator_photo(index: int | None = None):
    """Save a frame from the running operator preview (or open one transiently)."""
    ctx = get_context()
    ctx.operator.start(_operator_index(ctx, index), ctx.state.use_simulation)

    def _grab_and_save() -> str:
        frame = None
        for _ in range(15):  # wait for the preview worker to produce a frame
            frame = ctx.operator.latest()
            if frame is not None:
                break
            import time as _t
            _t.sleep(0.05)
        if frame is None:
            raise HTTPException(status_code=503, detail=ctx.operator.last_error() or "無法擷取操作者影像。")
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        path = PHOTOS_DIR / f"operator_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        cv2.imwrite(str(path), frame)
        return str(path)

    path = await run_in_threadpool(_grab_and_save)
    ctx.state.operator_photo_path = path
    return {"photo_path": path}
