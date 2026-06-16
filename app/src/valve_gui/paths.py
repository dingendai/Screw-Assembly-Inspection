from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "inspection_data"
PHOTOS_DIR = DATA_DIR / "operator_photos"
SESSION_LOG_PATH = DATA_DIR / "operator_sessions.csv"
RECORDS_LOG_PATH = DATA_DIR / "inspection_records.csv"
USER_RECORDS_DIR = DATA_DIR / "user_records"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"
APP_CONFIG_PATH = DATA_DIR / "app_config.json"
