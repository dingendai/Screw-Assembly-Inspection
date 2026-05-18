import csv

from valve_gui.permissions import role_label


def write_sessions_csv(path, sessions):
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["operator_name", "operator_role", "role_label", "login_time", "logout_time", "photo_path"])
        for session in sessions:
            writer.writerow([
                session.operator_name,
                session.operator_role,
                role_label(session.operator_role),
                session.login_time,
                session.logout_time,
                session.photo_path,
            ])
