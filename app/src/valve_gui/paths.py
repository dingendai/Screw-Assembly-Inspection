import sys
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()


def _is_frozen() -> bool:
    """True when running from a PyInstaller (or similar) bundled .exe."""
    return getattr(sys, "frozen", False)


if _is_frozen():
    # Bundled .exe: anchor writable data and models next to the executable so
    # records/config persist and external model files can be found.
    BASE_DIR = Path(sys.executable).resolve().parent
    APP_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "inspection_data"
    MODEL_DIR = BASE_DIR / "models"
else:
    # Running from source: keep the original layout unchanged.
    APP_DIR = _THIS_FILE.parent.parent                      # app/src
    DATA_DIR = APP_DIR / "inspection_data"
    MODEL_DIR = _THIS_FILE.parent.parent.parent.parent / "models"

PHOTOS_DIR = DATA_DIR / "operator_photos"
SESSION_LOG_PATH = DATA_DIR / "operator_sessions.csv"
RECORDS_LOG_PATH = DATA_DIR / "inspection_records.csv"
USER_RECORDS_DIR = DATA_DIR / "user_records"
APP_CONFIG_PATH = DATA_DIR / "app_config.json"
