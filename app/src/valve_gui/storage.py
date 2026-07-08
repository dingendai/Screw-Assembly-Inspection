import csv
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import cv2

from valve_gui.models import OperatorSession
from valve_gui.paths import QC_OBJECTS_DIR
from valve_gui.permissions import role_label

_RECORD_HEADER = [
    "timestamp", "operator_name", "operator_role",
    "result", "part_id", "active_cameras", "confidence", "note",
]


def read_sessions_csv(path):
    """把登入/登出紀錄從 CSV 載回 OperatorSession 清單（newest-first，與寫入順序一致）。

    啟動時呼叫，避免登出時整檔覆寫把先前執行的登入紀錄洗掉。
    """
    path = Path(path)
    if not path.exists():
        return []
    sessions = []
    with open(path, "r", newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            name = (row.get("operator_name") or "").strip()
            if not name:
                continue
            sessions.append(
                OperatorSession(
                    operator_name=name,
                    operator_role=(row.get("operator_role") or "").strip(),
                    login_time=row.get("login_time") or "",
                    logout_time=row.get("logout_time") or "",
                    photo_path=row.get("photo_path") or "",
                )
            )
    return sessions


def write_sessions_csv(path, sessions, role_labels=None):
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["operator_name", "operator_role", "role_label", "login_time", "logout_time", "photo_path"])
        for session in sessions:
            writer.writerow([
                session.operator_name,
                session.operator_role,
                role_label(session.operator_role, role_labels),
                session.login_time,
                session.logout_time,
                session.photo_path,
            ])


def write_user_records_csv(path, records, role_labels=None):
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["時間", "操作者", "角色", "結果", "工件", "相機", "信心度", "備註"])
        for record in records:
            writer.writerow([
                record.timestamp,
                record.operator_name,
                role_label(record.operator_role, role_labels),
                record.result,
                record.part_id,
                record.active_cameras,
                record.confidence,
                record.note,
            ])


def append_record_csv(path, record):
    path = Path(path)
    rows = []
    if path.exists() and path.stat().st_size > 0:
        with open(path, "r", newline="", encoding="utf-8-sig") as file:
            rows = list(csv.DictReader(file))

    record_row = {
        "timestamp": record.timestamp,
        "operator_name": record.operator_name,
        "operator_role": record.operator_role,
        "result": record.result,
        "part_id": record.part_id,
        "active_cameras": record.active_cameras,
        "confidence": record.confidence,
        "note": record.note,
    }
    record_date = (record.timestamp or "")[:10]
    part_id = (record.part_id or "").strip()
    if part_id and record_date:
        rows = [
            row for row in rows
            if not ((row.get("part_id") or "").strip() == part_id and (row.get("timestamp") or "")[:10] == record_date)
        ]
    rows.append(record_row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=_RECORD_HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_path_part(value, fallback="unknown"):
    text = _INVALID_PATH_CHARS.sub("_", str(value or "").strip())
    text = text.strip(" .")
    return text[:120] or fallback


def session_folder_name(operator_name, login_time):
    operator = safe_path_part(operator_name, "unknown_operator")
    timestamp = safe_path_part((login_time or "").replace("-", "").replace(":", "").replace(" ", "_"), "unknown_time")
    return operator, timestamp


def save_qc_object_snapshot(
    record,
    *,
    login_time="",
    raw_frames=None,
    annotated_frames=None,
    camera_results=None,
    roi_confirmations=None,
    inspection_id=None,
):
    """Save the latest raw/annotated images for one barcode object in this work session."""
    barcode = (record.part_id or "").strip()
    if not barcode or getattr(record, "barcode_source", "") == "auto":
        return None

    barcode_dir_name = safe_path_part(barcode, "unknown_barcode")
    operator_dir, login_dir = session_folder_name(record.operator_name, login_time)
    object_dir = QC_OBJECTS_DIR / operator_dir / login_dir / barcode_dir_name
    remove_previous_qc_object_snapshots(barcode_dir_name, (record.timestamp or "")[:10], object_dir)
    object_dir.mkdir(parents=True, exist_ok=True)

    for old_file in object_dir.glob("camera_*_*.jpg"):
        old_file.unlink(missing_ok=True)

    raw_files = {}
    annotated_files = {}
    for slot, frame in sorted((raw_frames or {}).items()):
        file_name = f"camera_{slot}_raw.jpg"
        path = object_dir / file_name
        if cv2.imwrite(str(path), frame):
            raw_files[str(slot)] = file_name

    for slot, frame in sorted((annotated_frames or {}).items()):
        file_name = f"camera_{slot}_annotated.jpg"
        path = object_dir / file_name
        if cv2.imwrite(str(path), frame):
            annotated_files[str(slot)] = file_name

    metadata = {
        "inspection_id": inspection_id,
        "updated_at": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "timestamp": record.timestamp,
        "operator_name": record.operator_name,
        "operator_role": record.operator_role,
        "login_time": login_time,
        "barcode": barcode,
        "result": record.result,
        "source": getattr(record, "barcode_source", ""),
        "active_cameras": record.active_cameras,
        "confidence": record.confidence,
        "note": record.note,
        "camera_results": camera_results or {},
        "roi_confirmations": roi_confirmations or {},
        "files": {
            "raw": raw_files,
            "annotated": annotated_files,
        },
    }
    with open(object_dir / "result.json", "w", encoding="utf-8") as file:
        json.dump(metadata, file, ensure_ascii=False, indent=2)

    latest_csv = object_dir / "latest_result.csv"
    with open(latest_csv, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp", "barcode", "result", "operator_name", "operator_role", "confidence", "note"])
        writer.writerow([
            record.timestamp,
            barcode,
            record.result,
            record.operator_name,
            record.operator_role,
            record.confidence,
            record.note,
        ])
    return object_dir


def remove_previous_qc_object_snapshots(barcode_dir_name, record_date, keep_dir):
    if not record_date or not QC_OBJECTS_DIR.exists():
        return
    keep_path = Path(keep_dir)
    for operator_dir in QC_OBJECTS_DIR.iterdir():
        if not operator_dir.is_dir():
            continue
        for login_dir in operator_dir.iterdir():
            if not login_dir.is_dir():
                continue
            candidate = login_dir / barcode_dir_name
            if not candidate.is_dir() or candidate == keep_path:
                continue
            metadata_path = candidate / "result.json"
            if not metadata_path.exists():
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(metadata.get("timestamp", ""))[:10] == record_date:
                shutil.rmtree(candidate, ignore_errors=True)
