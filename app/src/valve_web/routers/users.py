"""User & role management endpoints (mirrors UserManagementPage). Developer only."""

from dataclasses import asdict

from fastapi import APIRouter, Depends

from valve_gui.config_store import save_app_config
from valve_gui.models import UserAccount
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_DEVELOPER,
    ROLE_PERMISSIONS,
    default_role_permissions,
)

from valve_web.deps import require_developer
from valve_web.schemas import PermissionsUpdate, UserItem
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
    }


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
