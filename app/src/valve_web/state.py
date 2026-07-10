"""Process-wide singletons for the web UI.

This is a single-station app, so the web backend keeps one global ``AppState``
(the same object the desktop ``MainWindow`` would hold), one shared
``InferenceRouter`` and one ``CameraManager``. The state is loaded from the
shared ``app_config.json`` on startup, identical to the desktop boot path.
"""

import threading

from valve_gui import qc_db
from valve_gui.config_store import load_app_config
from valve_gui.inference_router import InferenceRouter
from valve_gui.model_registry import ensure_model_configs
from valve_gui.models import AppState
from valve_gui.paths import DATA_DIR, SESSION_LOG_PATH
from valve_gui.storage import read_sessions_csv

from valve_web.camera_manager import CameraManager, OperatorPreview


class WebContext:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.state = AppState()
        load_app_config(self.state)
        # 載回先前的登入紀錄，避免登出時整檔覆寫把歷史 sessions 洗掉。
        self.state.sessions = read_sessions_csv(SESSION_LOG_PATH)
        ensure_model_configs(self.state)
        qc_db.init_db()
        self.router = InferenceRouter(self.state)
        self.cameras = CameraManager()
        self.operator = OperatorPreview()
        # Continuous inspection bookkeeping (driven by the inspect router).
        self.continuous = False
        self.latest_result: dict | None = None
        self._last_record_signature: tuple[str, str] | None = None
        self.lock = threading.Lock()

    def reload_cameras(self):
        """Rebuild capture workers and drop cached models after a config change."""
        self.router.clear_model_cache()
        self.cameras.restart(self.state)


_context: WebContext | None = None


def get_context() -> WebContext:
    global _context
    if _context is None:
        _context = WebContext()
    return _context
