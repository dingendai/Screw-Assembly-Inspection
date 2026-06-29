"""品管統計頁（PyQt）：不良率統計、條件查詢、NG 品項排行、匯出 CSV。

資料一律讀 valve_gui.qc_db（SQLite），與網頁端共用同一個 qc.db。
"""

import csv
from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from valve_gui import qc_db
from valve_gui.models import AppState


class StatisticsPage(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        # ---- 篩選條件 ----
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("條碼（留空 = 全部）")
        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("起 YYYY-MM-DD")
        self.start_input.setMaximumWidth(140)
        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("迄 YYYY-MM-DD")
        self.end_input.setMaximumWidth(140)
        self.result_combo = QComboBox()
        self.result_combo.addItem("全部判定", "")
        self.result_combo.addItem("PASS", "PASS")
        self.result_combo.addItem("NG", "NG")
        self.query_button = QPushButton("查詢")
        self.query_button.setObjectName("primaryButton")
        self.query_button.clicked.connect(self.refresh)
        self.export_button = QPushButton("匯出 CSV")
        self.export_button.clicked.connect(self.export_csv)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("條碼"))
        filters.addWidget(self.barcode_input)
        filters.addWidget(self.start_input)
        filters.addWidget(self.end_input)
        filters.addWidget(self.result_combo)
        filters.addWidget(self.query_button)
        filters.addWidget(self.export_button)
        filters.addStretch()

        # ---- 統計摘要 ----
        self.summary_label = QLabel("總檢驗數 0 ｜ PASS 0 ｜ NG 0 ｜ 不良率 0.0 %")
        self.summary_label.setObjectName("pageTitle")

        # ---- 歷史表格 ----
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["時間", "條碼", "品名", "判定", "操作者", "信心", "備註"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)

        # ---- NG 排行 ----
        self.rank_table = QTableWidget(0, 6)
        self.rank_table.setHorizontalHeaderLabels(["#", "條碼", "品名", "總數", "NG", "不良率"])
        self.rank_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rank_table.setAlternatingRowColors(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("品管統計"))
        layout.addLayout(filters)
        layout.addWidget(self.summary_label)
        layout.addWidget(QLabel("檢驗歷史"))
        layout.addWidget(self.table, 2)
        layout.addWidget(QLabel("NG 品項排行（不良率前 10）"))
        layout.addWidget(self.rank_table, 1)

    # ------------------------------------------------------------------
    def _filters(self):
        return {
            "barcode": self.barcode_input.text().strip() or None,
            "start": self.start_input.text().strip() or None,
            "end": self.end_input.text().strip() or None,
            "result": self.result_combo.currentData() or None,
        }

    def refresh(self):
        f = self._filters()
        stats = qc_db.get_stats(f["barcode"])
        self.summary_label.setText(
            f"總檢驗數 {stats['total']} ｜ PASS {stats['ok']} ｜ NG {stats['ng']} ｜ 不良率 {stats['ng_rate']} %"
        )

        records = qc_db.get_history(
            f["barcode"], start=f["start"], end=f["end"], result=f["result"], limit=500
        )
        self.table.setRowCount(len(records))
        for row, rec in enumerate(records):
            values = [
                rec.get("inspected_at", ""),
                rec.get("barcode", ""),
                rec.get("product_name") or "—",
                rec.get("result", ""),
                rec.get("operator") or "—",
                rec.get("confidence") or "—",
                rec.get("note") or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

        ranking = qc_db.get_ng_ranking(10)
        self.rank_table.setRowCount(len(ranking))
        for row, rec in enumerate(ranking):
            values = [
                str(row + 1),
                rec.get("barcode", ""),
                rec.get("product_name") or "—",
                str(rec.get("total", 0)),
                str(rec.get("ng", 0)),
                f"{rec.get('ng_rate', 0.0)} %",
            ]
            for column, value in enumerate(values):
                self.rank_table.setItem(row, column, QTableWidgetItem(value))

    def export_csv(self):
        f = self._filters()
        rows = qc_db.get_history(
            f["barcode"], start=f["start"], end=f["end"], result=f["result"], limit=100000
        )
        if not rows:
            QMessageBox.information(self, "匯出 CSV", "目前沒有符合條件的紀錄可匯出。")
            return
        default_path = f"qc_inspections_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "匯出品管紀錄 CSV", default_path, "CSV Files (*.csv)")
        if not path:
            return
        fields = [
            "id", "barcode", "product_name", "result", "inspected_at",
            "operator", "confidence", "active_cameras", "note",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        QMessageBox.information(self, "匯出完成", f"已匯出：{path}")
