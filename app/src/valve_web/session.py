"""Minimal cookie-token session for the single-station web UI.

Login mutates the shared ``AppState`` operator fields (exactly like the desktop
``LoginPage._complete_login``) and records an ``OperatorSession``. A random
token is stored in a cookie so subsequent requests are recognised. Because this
is a single physical station we keep at most one active operator at a time.
"""

import secrets
import threading
from datetime import datetime

from valve_gui import qc_db
from valve_gui.models import OperatorSession
from valve_gui.paths import DATA_DIR, RECORD_EVENTS_LOG_PATH, SESSION_LOG_PATH, USER_RECORDS_DIR
from valve_gui.permissions import ROLE_OPERATOR
from valve_gui.storage import read_record_events_csv, write_sessions_csv, write_user_records_csv

COOKIE_NAME = "valve_web_session"

_tokens: set[str] = set()
_lock = threading.Lock()


def is_valid(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        return token in _tokens


def login(state, name: str, role: str, photo_path: str = "") -> str:
    """Mirror desktop LoginPage._complete_login and return a session token."""
    state.operator_name = name
    state.operator_role = role
    state.login_time = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
    state.is_logged_in = True
    state.settings_applied = True
    state.sessions.insert(
        0,
        OperatorSession(
            operator_name=name,
            operator_role=role,
            login_time=state.login_time,
            photo_path=photo_path,
        ),
    )
    token = secrets.token_urlsafe(24)
    with _lock:
        _tokens.add(token)
    try:
        state.current_work_session_id = qc_db.start_work_session(name, role, state.login_time)
    except Exception:
        state.current_work_session_id = None
    return token


def _save_user_records(state, when):
    name = state.operator_name.strip()
    if not name:
        return
    user_records = read_record_events_csv(
        RECORD_EVENTS_LOG_PATH,
        operator_name=name,
        start_time=state.login_time,
        end_time=f"{when:%Y-%m-%d %H:%M:%S}",
    )
    if not user_records:
        user_records = [r for r in state.records if r.operator_name == name]
    if not user_records:
        return
    USER_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "user"
    path = USER_RECORDS_DIR / f"{safe_name} {when:%Y%m%d%H%M}.csv"
    write_user_records_csv(path, user_records, state.role_labels)


def logout(state, token: str | None):
    """Mirror desktop MainWindow.logout: stamp logout time, persist CSVs."""
    with _lock:
        if token:
            _tokens.discard(token)
    if not state.is_logged_in:
        return
    now = datetime.now()
    if state.sessions:
        state.sessions[0].logout_time = f"{now:%Y-%m-%d %H:%M:%S}"
    try:
        qc_db.end_work_session(state.current_work_session_id, state.sessions[0].logout_time if state.sessions else None)
    except Exception:
        pass
    state.current_work_session_id = None
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_sessions_csv(SESSION_LOG_PATH, state.sessions, state.role_labels)
    _save_user_records(state, now)
    state.operator_name = ""
    state.operator_role = ROLE_OPERATOR
    state.login_time = ""
    state.is_logged_in = False
    state.settings_applied = False
