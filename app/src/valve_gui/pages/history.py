import csv
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from valve_gui.models import AppState
from valve_gui.paths import DATA_DIR
from valve_gui.permissions import (
    PERMISSION_EXPORT_RECORDS,
    PERMISSION_VIEW_ALL_RECORDS,
    PERMISSION_VIEW_SESSIONS,
    has_permission,
    role_label,
)
from valve_gui.storage import write_sessions_csv


class HistoryPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["時間", "操作者", "角色", "結果", "工件", "相機", "信心度", "備註"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)

        self.session_title = QLabel("操作者登入 / 登出紀錄")
        self.session_table = QTableWidget(0, 5)
        self.session_table.setHorizontalHeaderLabels(["操作者", "角色", "登入時間", "登出時間", "照片"])
        self.session_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.session_table.setAlternatingRowColors(True)

        self.export_button = QPushButton("匯出檢測 CSV")
        self.export_button.setObjectName("primaryButton")
        self.export_button.clicked.connect(self.export_csv)
        self.export_session_button = QPushButton("匯出登入紀錄 CSV")
        self.export_session_button.clicked.connect(self.export_sessions_csv)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.export_session_button)
        actions.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("檢測歷史紀錄"))
        layout.addWidget(self.table, 2)
        layout.addWidget(self.session_title)
        layout.addWidget(self.session_table, 1)
        layout.addLayout(actions)

    def refresh(self):
        can_view_all = has_permission(
            self.state.operator_role,
            PERMISSION_VIEW_ALL_RECORDS,
            self.state.role_permissions,
        )
        can_view_sessions = has_permission(
            self.state.operator_role,
            PERMISSION_VIEW_SESSIONS,
            self.state.role_permissions,
        )
        can_export = has_permission(
            self.state.operator_role,
            PERMISSION_EXPORT_RECORDS,
            self.state.role_permissions,
        )

        records = self.state.records if can_view_all else [
            record for record in self.state.records if record.operator_name == self.state.operator_name
        ]
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.timestamp,
                record.operator_name,
                role_label(record.operator_role, self.state.role_labels),
                record.result,
                record.part_id,
                record.active_cameras,
                record.confidence,
                record.note,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

        self.session_title.setVisible(can_view_sessions)
        self.session_table.setVisible(can_view_sessions)
        self.export_session_button.setVisible(can_view_sessions and can_export)
        self.export_button.setVisible(can_export)
        if not can_view_sessions:
            self.session_table.setRowCount(0)
            return

        self.session_table.setRowCount(len(self.state.sessions))
        for row, session in enumerate(self.state.sessions):
            values = [
                session.operator_name,
                role_label(session.operator_role, self.state.role_labels),
                session.login_time,
                session.logout_time,
                session.photo_path,
            ]
            for column, value in enumerate(values):
                self.session_table.setItem(row, column, QTableWidgetItem(value))

    def export_csv(self):
        if not has_permission(self.state.operator_role, PERMISSION_EXPORT_RECORDS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能匯出檢測紀錄。")
            return
        if not self.state.records:
            QMessageBox.information(self, "匯出 CSV", "目前沒有檢測紀錄可匯出。")
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default_path = DATA_DIR / f"inspection_records_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "匯出檢測 CSV", str(default_path), "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "operator_name",
                "operator_role",
                "role_label",
                "result",
                "part_id",
                "active_cameras",
                "confidence",
                "note",
            ])
            for record in self.state.records:
                writer.writerow([
                    record.timestamp,
                    record.operator_name,
                    record.operator_role,
                    role_label(record.operator_role, self.state.role_labels),
                    record.result,
                    record.part_id,
                    record.active_cameras,
                    record.confidence,
                    record.note,
                ])
        QMessageBox.information(self, "匯出完成", f"已匯出：{path}")

    def export_sessions_csv(self):
        if not has_permission(self.state.operator_role, PERMISSION_EXPORT_RECORDS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能匯出登入紀錄。")
            return
        if not self.state.sessions:
            QMessageBox.information(self, "匯出 CSV", "目前沒有登入紀錄可匯出。")
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default_path = DATA_DIR / f"operator_sessions_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "匯出登入紀錄 CSV", str(default_path), "CSV Files (*.csv)")
        if path:
            write_sessions_csv(path, self.state.sessions, self.state.role_labels)
            QMessageBox.information(self, "匯出完成", f"已匯出：{path}")
