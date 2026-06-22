"""Authentication endpoints (mirrors valve_gui LoginPage)."""

from datetime import datetime

import cv2
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool

from valve_gui.camera import VideoSource
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
    ctx.cameras.restart(ctx.state)
    return _me_payload(ctx)


@router.post("/logout")
def logout(response: Response, valve_web_session: str | None = Cookie(default=None)):
    ctx = get_context()
    session.logout(ctx.state, valve_web_session)
    ctx.cameras.stop_all()
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
    }


@router.get("/me")
def me(ctx: WebContext = Depends(require_login)):
    return _me_payload(ctx)


def _capture_operator_photo(index: int, simulate: bool) -> str:
    source = VideoSource(f"OPERATOR {index}", index, simulate)
    try:
        frame = None
        for _ in range(5):  # let the sensor warm up
            frame = source.read()
            if frame is not None:
                break
        if frame is None:
            raise HTTPException(status_code=503, detail=source.last_error or "無法擷取操作者影像。")
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        path = PHOTOS_DIR / f"operator_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        cv2.imwrite(str(path), frame)
        return str(path)
    finally:
        source.release()


@router.post("/operator-photo")
async def operator_photo():
    """Capture one frame from the operator camera and save it (pre-login)."""
    ctx = get_context()
    # Free any inspection workers first so the operator device isn't contended,
    # and run the blocking capture off the event loop.
    ctx.cameras.stop_all()
    path = await run_in_threadpool(_capture_operator_photo, ctx.state.operator_camera_index, ctx.state.use_simulation)
    ctx.state.operator_photo_path = path
    return {"photo_path": path}
