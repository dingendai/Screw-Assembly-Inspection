"""History endpoints (mirrors HistoryPage).

Reads the shared CSV files on disk so records/sessions survive restarts and stay
consistent with the desktop GUI.
"""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from valve_gui.paths import RECORDS_LOG_PATH, SESSION_LOG_PATH
from valve_gui.permissions import (
    PERMISSION_EXPORT_RECORDS,
    PERMISSION_OPEN_HISTORY,
    PERMISSION_VIEW_ALL_RECORDS,
    PERMISSION_VIEW_SESSIONS,
    has_permission,
    role_label,
)

from valve_web.deps import require_permission
from valve_web.state import WebContext

router = APIRouter(prefix="/api", tags=["history"])

_history_dep = require_permission(PERMISSION_OPEN_HISTORY)


def _read_records() -> list[dict]:
    if not RECORDS_LOG_PATH.exists():
        return []
    with open(RECORDS_LOG_PATH, "r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    rows.reverse()  # newest first, matching the GUI's insert(0, ...)
    return rows


def _read_sessions() -> list[dict]:
    if not SESSION_LOG_PATH.exists():
        return []
    with open(SESSION_LOG_PATH, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


@router.get("/records")
def records(ctx: WebContext = Depends(_history_dep)):
    state = ctx.state
    can_view_all = has_permission(state.operator_role, PERMISSION_VIEW_ALL_RECORDS, state.role_permissions)
    can_view_sessions = has_permission(state.operator_role, PERMISSION_VIEW_SESSIONS, state.role_permissions)
    can_export = has_permission(state.operator_role, PERMISSION_EXPORT_RECORDS, state.role_permissions)

    rows = _read_records()
    for row in rows:
        row["role_label"] = role_label(row.get("operator_role", ""), state.role_labels)
    if not can_view_all:
        rows = [r for r in rows if r.get("operator_name") == state.operator_name]

    sessions = []
    if can_view_sessions:
        sessions = _read_sessions()

    return {
        "records": rows,
        "sessions": sessions,
        "can_view_sessions": can_view_sessions,
        "can_export": can_export,
    }


def _csv_response(rows: list[dict], fieldnames: list[str], filename: str):
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM for Excel
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/records/export")
def export_records(ctx: WebContext = Depends(_history_dep)):
    state = ctx.state
    if not has_permission(state.operator_role, PERMISSION_EXPORT_RECORDS, state.role_permissions):
        raise HTTPException(status_code=403, detail="目前角色不能匯出檢測紀錄。")
    rows = _read_records()
    if not has_permission(state.operator_role, PERMISSION_VIEW_ALL_RECORDS, state.role_permissions):
        rows = [r for r in rows if r.get("operator_name") == state.operator_name]
    for row in rows:
        row["role_label"] = role_label(row.get("operator_role", ""), state.role_labels)
    fields = [
        "timestamp", "operator_name", "operator_role", "role_label",
        "result", "part_id", "active_cameras", "confidence", "note",
    ]
    return _csv_response(rows, fields, f"inspection_records_{datetime.now():%Y%m%d_%H%M%S}.csv")


@router.get("/sessions/export")
def export_sessions(ctx: WebContext = Depends(_history_dep)):
    state = ctx.state
    if not has_permission(state.operator_role, PERMISSION_EXPORT_RECORDS, state.role_permissions):
        raise HTTPException(status_code=403, detail="目前角色不能匯出登入紀錄。")
    if not has_permission(state.operator_role, PERMISSION_VIEW_SESSIONS, state.role_permissions):
        raise HTTPException(status_code=403, detail="目前角色不能查看登入紀錄。")
    rows = _read_sessions()
    fields = ["operator_name", "operator_role", "role_label", "login_time", "logout_time", "photo_path"]
    return _csv_response(rows, fields, f"operator_sessions_{datetime.now():%Y%m%d_%H%M%S}.csv")
