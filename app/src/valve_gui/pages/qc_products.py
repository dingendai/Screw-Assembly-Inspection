"""品項主檔頁（PyQt）：維護條碼對應的品名 / 規格。

條碼為品項唯一鍵；同一條碼的多次檢驗累計於檢驗數。資料讀寫走 valve_gui.qc_db。
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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

from valve_gui import qc_db
from valve_gui.models import AppState
from valve_gui.permissions import PERMISSION_QC_PRODUCT_MANAGE, has_permission


class ProductMasterPage(QWidget):
    # 條碼 / 檢驗數 / 建檔時間唯讀；品名、規格可編輯。
    COL_BARCODE, COL_NAME, COL_SPEC, COL_COUNT, COL_CREATED = range(5)

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["條碼", "品名", "規格", "檢驗數", "建檔時間"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)

        self.save_button = QPushButton("儲存品名 / 規格")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self.save_changes)
        self.refresh_button = QPushButton("重新整理")
        self.refresh_button.clicked.connect(self.refresh)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(QLabel("品項主檔"))
        layout.addWidget(
            QLabel("條碼為品項唯一鍵；檢驗一次條碼後會自動建檔。可補上品名與規格。"),
        )
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)

    def _can_manage(self):
        return has_permission(
            self.state.operator_role, PERMISSION_QC_PRODUCT_MANAGE, self.state.role_permissions
        )

    def refresh(self):
        products = qc_db.list_products()
        editable = self._can_manage()
        self.save_button.setVisible(editable)
        self.table.setRowCount(len(products))
        for row, product in enumerate(products):
            barcode_item = QTableWidgetItem(product.get("barcode", ""))
            barcode_item.setFlags(barcode_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item = QTableWidgetItem(product.get("name") or "")
            spec_item = QTableWidgetItem(product.get("spec") or "")
            if not editable:
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                spec_item.setFlags(spec_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            count_item = QTableWidgetItem(str(product.get("inspection_count", 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            created_item = QTableWidgetItem(product.get("created_at", ""))
            created_item.setFlags(created_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, self.COL_BARCODE, barcode_item)
            self.table.setItem(row, self.COL_NAME, name_item)
            self.table.setItem(row, self.COL_SPEC, spec_item)
            self.table.setItem(row, self.COL_COUNT, count_item)
            self.table.setItem(row, self.COL_CREATED, created_item)

    def save_changes(self):
        if not self._can_manage():
            QMessageBox.warning(self, "權限不足", "目前角色不能維護品項主檔。")
            return
        saved = 0
        for row in range(self.table.rowCount()):
            barcode_item = self.table.item(row, self.COL_BARCODE)
            if not barcode_item or not barcode_item.text().strip():
                continue
            name = self.table.item(row, self.COL_NAME)
            spec = self.table.item(row, self.COL_SPEC)
            qc_db.update_product(
                barcode_item.text().strip(),
                name=(name.text().strip() if name else "") or None,
                spec=(spec.text().strip() if spec else "") or None,
            )
            saved += 1
        QMessageBox.information(self, "儲存完成", f"已更新 {saved} 個品項。")
        self.refresh()
