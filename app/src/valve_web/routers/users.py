"""User & role management endpoints (mirrors UserManagementPage). Developer only."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from valve_gui import paths, qc_db
from valve_gui.config_store import save_app_config
from valve_gui.models import OperatorSession, UserAccount
from valve_gui.paths import SESSION_LOG_PATH
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_DEVELOPER,
    ROLE_PERMISSIONS,
    default_role_permissions,
)
from valve_gui.storage import read_sessions_csv

from valve_web.deps import require_developer
from valve_web.schemas import PermissionsUpdate, QcOutputUpdate, UserItem
from valve_web.state import WebContext

router = APIRouter(prefix="/api", tags=["users"])


def _serialize(ctx: WebContext) -> dict:
    state = ctx.state
    return {
        "users": [asdict(u) for u in state.user_accounts],
        "role_labels": state.role_labels,
        "role_permissions": {role: sorted(perms) for role, perms in state.role_permissions.items()},
        "developer_permissions": sorted(ROLE_PERMISSIONS[ROLE_DEVELOPER]),
        "configurable_permissions": CONFIGURABLE_PERMISSIONS,
        "permission_labels": PERMISSION_LABELS,
        "protected_role": ROLE_DEVELOPER,
        "qc_output_dir": state.qc_output_dir or str(paths.get_qc_output_dir()),
    }


def _activate_qc_output_dir(ctx: WebContext, output_dir: str) -> None:
    target = paths.resolve_qc_output_dir(output_dir)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"無法建立品管資料輸出資料夾：{target} ({exc})") from exc

    old_output_dir = ctx.state.qc_output_dir
    ctx.state.qc_output_dir = str(target)
    paths.set_qc_output_dir(target)
    save_app_config(ctx.state)
    if old_output_dir == ctx.state.qc_output_dir:
        return

    qc_db.init_db()
    ctx.state.sessions = read_sessions_csv(SESSION_LOG_PATH)
    if ctx.state.is_logged_in:
        ctx.state.sessions.insert(
            0,
            OperatorSession(
                operator_name=ctx.state.operator_name,
                operator_role=ctx.state.operator_role,
                login_time=ctx.state.login_time,
                photo_path=ctx.state.operator_photo_path,
            ),
        )
        try:
            ctx.state.current_work_session_id = qc_db.start_work_session(
                ctx.state.operator_name,
                ctx.state.operator_role,
                ctx.state.login_time,
            )
        except Exception:
            ctx.state.current_work_session_id = None


@router.get("/users")
def get_users(ctx: WebContext = Depends(require_developer)):
    return _serialize(ctx)


@router.put("/users")
def update_users(items: list[UserItem], ctx: WebContext = Depends(require_developer)):
    ctx.state.user_accounts = [
        UserAccount(
            username=u.username.strip(),
            display_name=u.display_name.strip(),
            role=u.role.strip() or "operator",
            password=u.password,
            enabled=u.enabled,
        )
        for u in items
        if u.username.strip()
    ]
    save_app_config(ctx.state)  # hashes plain passwords automatically
    return _serialize(ctx)


@router.put("/permissions")
def update_permissions(req: PermissionsUpdate, ctx: WebContext = Depends(require_developer)):
    allowed = set(CONFIGURABLE_PERMISSIONS)
    merged = default_role_permissions()
    for role, perms in req.role_permissions.items():
        if role == ROLE_DEVELOPER:
            continue
        merged[role] = {p for p in perms if p in allowed}
    ctx.state.role_permissions = merged

    if req.role_labels is not None:
        labels = {ROLE_DEVELOPER: ctx.state.role_labels.get(ROLE_DEVELOPER, "開發者")}
        for role, label in req.role_labels.items():
            key = str(role).strip()
            if key:
                labels[key] = str(label).strip() or key
        ctx.state.role_labels = labels

    if req.role_passwords is not None:
        passwords = dict(ctx.state.role_passwords)
        for role, pw in req.role_passwords.items():
            if role in ctx.state.role_labels:
                passwords[role] = pw  # save_app_config hashes plain text
        ctx.state.role_passwords = passwords

    save_app_config(ctx.state)
    return _serialize(ctx)


@router.put("/users/qc-output")
def update_qc_output(req: QcOutputUpdate, ctx: WebContext = Depends(require_developer)):
    _activate_qc_output_dir(ctx, req.qc_output_dir)
    return _serialize(ctx)
