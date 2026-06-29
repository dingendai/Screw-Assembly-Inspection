"""歷史紀錄頁（PyQt）— 依「工作時段」分組。

重新定義後的歷史：
- 上層：操作者的一段工作時段（開始工作=登入 / 結束工作=登出 的時間戳與日期）。
- 下層：該時段內每個測試件的「序號（影像條碼）＋ OK/NG ＋ 檢測時間」。

資料一律讀 qc.db（單一真相），重啟後仍在，並與品管統計頁一致。
"""

import csv
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from valve_gui import qc_db
from valve_gui.models import AppState
from valve_gui.paths import DATA_DIR
from valve_gui.permissions import (
    PERMISSION_EXPORT_RECORDS,
    PERMISSION_VIEW_ALL_RECORDS,
    has_permission,
    role_label,
)

_NG_COLOR = QColor("#ef4444")
_PASS_COLOR = QColor("#22c55e")


class HistoryPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(
            ["操作者 / 工件序號", "開始工作 / 判定", "結束工作 / 檢測時間", "件數(NG) / 信心度", "備註"]
        )
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setAlternatingRowColors(True)

        self.summary_label = QLabel("")
        self.summary_label.setObjectName("mutedText")

        self.export_button = QPushButton("匯出檢測 CSV")
        self.export_button.setObjectName("primaryButton")
        self.export_button.clicked.connect(self.export_csv)
        self.refresh_button = QPushButton("重新整理")
        self.refresh_button.clicked.connect(self.refresh)

        actions = QHBoxLayout()
        actions.addWidget(self.summary_label)
        actions.addStretch()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("檢測歷史紀錄（依工作時段）"))
        layout.addWidget(self.tree, 1)
        layout.addLayout(actions)

    # ------------------------------------------------------------------
    def _operator_filter(self):
        can_view_all = has_permission(
            self.state.operator_role, PERMISSION_VIEW_ALL_RECORDS, self.state.role_permissions
        )
        return None if can_view_all else self.state.operator_name

    def _load_groups(self):
        """回傳 (sessions_with_inspections, orphans)。"""
        operator = self._operator_filter()
        sessions = qc_db.get_work_sessions(operator=operator, limit=1000)
        groups = [(s, qc_db.get_session_inspections(s["id"])) for s in sessions]
        orphans = qc_db.get_orphan_inspections(operator=operator)
        return groups, orphans

    def _make_child(self, insp):
        result = insp.get("result", "")
        source = insp.get("source") or ""
        # 標籤資料來源：條碼來自哪個標籤類別（manual/auto 不另標示）。
        serial = f"序號 {insp.get('barcode', '')}"
        if source and source not in ("manual", "auto"):
            serial += f"（標籤：{source}）"
        child = QTreeWidgetItem([
            serial,
            result,
            insp.get("inspected_at", ""),
            insp.get("confidence") or "",
            insp.get("note") or "",
        ])
        child.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
        child.setForeground(1, _NG_COLOR if result == "NG" else _PASS_COLOR)
        return child

    def refresh(self):
        groups, orphans = self._load_groups()
        self.tree.clear()

        total_pieces = 0
        total_ng = 0
        for session, inspections in groups:
            total = session.get("total") or 0
            ng = session.get("ng") or 0
            total_pieces += total
            total_ng += ng
            role = role_label(session.get("operator_role") or "", self.state.role_labels)
            parent = QTreeWidgetItem([
                f"{session.get('operator') or '--'}（{role}）",
                session.get("login_time") or "",
                session.get("logout_time") or "（工作中）",
                f"{total} 件，NG {ng}",
                "",
            ])
            for insp in inspections:
                parent.addChild(self._make_child(insp))
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)

        if orphans:
            parent = QTreeWidgetItem(["未指定工作時段", "", "", f"{len(orphans)} 件", ""])
            for insp in orphans:
                total_pieces += 1
                if insp.get("result") == "NG":
                    total_ng += 1
                parent.addChild(self._make_child(insp))
            self.tree.addTopLevelItem(parent)
            parent.setExpanded(True)

        ng_rate = round(total_ng / total_pieces * 100, 2) if total_pieces else 0.0
        self.summary_label.setText(
            f"工作時段 {len(groups)} 段 ｜ 測試件 {total_pieces} 件 ｜ NG {total_ng} ｜ 不良率 {ng_rate} %"
        )

    # ------------------------------------------------------------------
    def export_csv(self):
        if not has_permission(self.state.operator_role, PERMISSION_EXPORT_RECORDS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能匯出檢測紀錄。")
            return
        groups, orphans = self._load_groups()
        rows = []
        for session, inspections in groups:
            role = session.get("operator_role") or ""
            for insp in inspections:
                rows.append({
                    "operator": session.get("operator") or "",
                    "operator_role": role,
                    "role_label": role_label(role, self.state.role_labels),
                    "login_time": session.get("login_time") or "",
                    "logout_time": session.get("logout_time") or "",
                    "serial": insp.get("barcode") or "",
                    "label_source": insp.get("source") or "",
                    "result": insp.get("result") or "",
                    "inspected_at": insp.get("inspected_at") or "",
                    "confidence": insp.get("confidence") or "",
                    "note": insp.get("note") or "",
                })
        for insp in orphans:
            rows.append({
                "operator": "", "operator_role": "", "role_label": "",
                "login_time": "", "logout_time": "",
                "serial": insp.get("barcode") or "",
                "label_source": insp.get("source") or "",
                "result": insp.get("result") or "",
                "inspected_at": insp.get("inspected_at") or "",
                "confidence": insp.get("confidence") or "",
                "note": insp.get("note") or "",
            })
        if not rows:
            QMessageBox.information(self, "匯出 CSV", "目前沒有檢測紀錄可匯出。")
            return

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        default_path = DATA_DIR / f"work_history_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "匯出檢測 CSV", str(default_path), "CSV Files (*.csv)")
        if not path:
            return
        fields = [
            "operator", "operator_role", "role_label", "login_time", "logout_time",
            "serial", "label_source", "result", "inspected_at", "confidence", "note",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        QMessageBox.information(self, "匯出完成", f"已匯出：{path}")
