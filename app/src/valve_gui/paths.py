import sys
import os
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
    DEFAULT_DATA_DIR = BASE_DIR / "inspection_data"
    MODEL_DIR = BASE_DIR / "models"
else:
    # Running from source: keep the original layout unchanged.
    APP_DIR = _THIS_FILE.parent.parent                      # app/src
    DEFAULT_DATA_DIR = APP_DIR / "inspection_data"
    MODEL_DIR = _THIS_FILE.parent.parent.parent.parent / "models"

_qc_output_dir = DEFAULT_DATA_DIR


def resolve_qc_output_dir(value: str | Path | None = None) -> Path:
    text = str(value or "").strip().strip('"')
    if not text:
        return DEFAULT_DATA_DIR
    return Path(text).expanduser().resolve()


def set_qc_output_dir(value: str | Path | None) -> Path:
    global _qc_output_dir
    _qc_output_dir = resolve_qc_output_dir(value)
    return _qc_output_dir


def get_qc_output_dir() -> Path:
    return _qc_output_dir


class RuntimePath(os.PathLike):
    """Path-like proxy that resolves after the QC output folder changes."""

    def __init__(self, resolver):
        self._resolver = resolver

    def path(self) -> Path:
        return Path(self._resolver())

    def __fspath__(self):
        return str(self.path())

    def __str__(self):
        return str(self.path())

    def __repr__(self):
        return repr(self.path())

    def __truediv__(self, other):
        return self.path() / other

    def __eq__(self, other):
        return self.path() == Path(other)

    def __getattr__(self, name):
        return getattr(self.path(), name)


DATA_DIR = RuntimePath(get_qc_output_dir)
PHOTOS_DIR = RuntimePath(lambda: get_qc_output_dir() / "operator_photos")
SESSION_LOG_PATH = RuntimePath(lambda: get_qc_output_dir() / "operator_sessions.csv")
RECORDS_LOG_PATH = RuntimePath(lambda: get_qc_output_dir() / "inspection_records.csv")
USER_RECORDS_DIR = RuntimePath(lambda: get_qc_output_dir() / "user_records")
QC_OBJECTS_DIR = RuntimePath(lambda: get_qc_output_dir() / "qc_objects")
QC_DB_PATH = RuntimePath(lambda: get_qc_output_dir() / "qc.db")

# Keep the bootstrap config fixed. It stores the selected QC output folder, so
# moving this file with the output data would make the next startup ambiguous.
APP_CONFIG_PATH = DEFAULT_DATA_DIR / "app_config.json"
