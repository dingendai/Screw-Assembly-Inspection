"""FastAPI dependencies: authentication and permission gating.

Permission checks reuse ``valve_gui.permissions.has_permission`` so the web UI
enforces exactly the same role rules as the desktop GUI.
"""

from fastapi import Cookie, Depends, HTTPException, status

from valve_gui.permissions import ROLE_DEVELOPER, has_permission

from valve_web import session
from valve_web.state import WebContext, get_context


def require_login(valve_web_session: str | None = Cookie(default=None)) -> WebContext:
    ctx = get_context()
    if not session.is_valid(valve_web_session) or not ctx.state.is_logged_in:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="尚未登入")
    return ctx


def require_permission(permission: str):
    def _dep(ctx: WebContext = Depends(require_login)) -> WebContext:
        if not has_permission(ctx.state.operator_role, permission, ctx.state.role_permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="權限不足")
        return ctx

    return _dep


def require_developer(ctx: WebContext = Depends(require_login)) -> WebContext:
    if ctx.state.operator_role != ROLE_DEVELOPER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有開發者可進行此操作")
    return ctx
