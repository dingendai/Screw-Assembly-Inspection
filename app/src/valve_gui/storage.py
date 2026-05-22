import csv
from pathlib import Path

from valve_gui.permissions import role_label

_RECORD_HEADER = [
    "timestamp", "operator_name", "operator_role",
    "result", "part_id", "active_cameras", "confidence", "note",
]


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


def append_record_csv(path, record):
    path = Path(path)
    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(_RECORD_HEADER)
        writer.writerow([
            record.timestamp,
            record.operator_name,
            record.operator_role,
            record.result,
            record.part_id,
            record.active_cameras,
            record.confidence,
            record.note,
        ])
