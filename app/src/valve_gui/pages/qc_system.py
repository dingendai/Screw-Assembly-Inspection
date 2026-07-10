from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from valve_gui import paths
from valve_gui.config_store import save_app_config
from valve_gui.models import AppState


class QcSystemPage(QWidget):
    def __init__(self, state: AppState, on_saved=None):
        super().__init__()
        self.state = state
        self.on_saved = on_saved

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("品管系統")
        title.setObjectName("pageTitle")
        subtitle = QLabel("設定品管輸出資料夾與記錄方式。")
        subtitle.setObjectName("mutedText")

        hint = QLabel("檢測 CSV、SQLite 與品管輸出影像都會寫到這裡，也可以決定連續檢測時要持續記錄，或每次判定後只記錄一次。")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)

        output_box = QGroupBox("品管輸出設定")
        form = QFormLayout(output_box)

        self.qc_output_dir_input = QLineEdit()
        self.qc_output_dir_input.setPlaceholderText(str(paths.DEFAULT_DATA_DIR))
        browse_button = QPushButton("選擇資料夾")
        browse_button.clicked.connect(self.browse_qc_output_dir)

        row = QHBoxLayout()
        row.addWidget(self.qc_output_dir_input, 1)
        row.addWidget(browse_button)
        form.addRow("輸出路徑", row)

        self.record_mode_combo = QComboBox()
        self.record_mode_combo.addItem("連續記錄", "continuous")
        self.record_mode_combo.addItem("每次判定記錄一次", "per_result")
        form.addRow("記錄方式", self.record_mode_combo)

        record_hint = QLabel("連續記錄會在連續檢測期間持續寫入；每次判定記錄一次會在連續檢測下於第一個 PASS 或 NG 記錄後自動停止。")
        record_hint.setObjectName("mutedText")
        record_hint.setWordWrap(True)
        form.addRow("", record_hint)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(hint)
        layout.addWidget(output_box)
        layout.addStretch()

    def refresh(self):
        self.qc_output_dir_input.setText(self.state.qc_output_dir or str(paths.get_qc_output_dir()))
        record_mode = getattr(self.state.inspection_workflow, "record_mode", "continuous")
        match = self.record_mode_combo.findData(record_mode)
        self.record_mode_combo.setCurrentIndex(match if match >= 0 else 0)

    def browse_qc_output_dir(self):
        current = self.qc_output_dir_input.text().strip()
        current_path = str(paths.resolve_qc_output_dir(current or self.state.qc_output_dir))
        selected = QFileDialog.getExistingDirectory(self, "選擇品管輸出資料夾", current_path)
        if selected:
            self.qc_output_dir_input.setText(selected)

    def save(self):
        output_dir = paths.resolve_qc_output_dir(self.qc_output_dir_input.text().strip())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "輸出路徑錯誤", f"無法建立品管輸出資料夾：\n{output_dir}\n\n{exc}")
            return False

        self.state.qc_output_dir = str(output_dir)
        self.state.inspection_workflow.record_mode = str(self.record_mode_combo.currentData())
        save_app_config(self.state)
        if self.on_saved:
            self.on_saved()
        QMessageBox.information(self, "儲存完成", "品管系統設定已更新。")
        self.refresh()
        return True
