import csv


def write_sessions_csv(path, sessions):
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["operator_name", "login_time", "logout_time", "photo_path"])
        for session in sessions:
            writer.writerow([session.operator_name, session.login_time, session.logout_time, session.photo_path])

