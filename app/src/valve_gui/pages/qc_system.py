from PyQt6.QtWidgets import QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

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
        subtitle = QLabel("設定品管資料存放位置。")
        subtitle.setObjectName("mutedText")

        hint = QLabel("檢測 CSV、SQLite 品管資料庫、操作者照片與個人紀錄都會寫入此資料夾。")
        hint.setObjectName("mutedText")

        output_box = QGroupBox("品管資料位置")
        form = QFormLayout(output_box)

        self.qc_output_dir_input = QLineEdit()
        self.qc_output_dir_input.setPlaceholderText(str(paths.DEFAULT_DATA_DIR))
        browse_button = QPushButton("選擇資料夾")
        browse_button.clicked.connect(self.browse_qc_output_dir)

        row = QHBoxLayout()
        row.addWidget(self.qc_output_dir_input, 1)
        row.addWidget(browse_button)
        form.addRow("資料夾", row)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(hint)
        layout.addWidget(output_box)
        layout.addStretch()

    def refresh(self):
        self.qc_output_dir_input.setText(self.state.qc_output_dir or str(paths.get_qc_output_dir()))

    def browse_qc_output_dir(self):
        current = self.qc_output_dir_input.text().strip()
        current_path = str(paths.resolve_qc_output_dir(current or self.state.qc_output_dir))
        selected = QFileDialog.getExistingDirectory(self, "選擇品管資料資料夾", current_path)
        if selected:
            self.qc_output_dir_input.setText(selected)

    def save(self):
        output_dir = paths.resolve_qc_output_dir(self.qc_output_dir_input.text().strip())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "資料錯誤", f"無法建立品管資料資料夾：\n{output_dir}\n\n{exc}")
            return False

        self.state.qc_output_dir = str(output_dir)
        save_app_config(self.state)
        if self.on_saved:
            self.on_saved()
        QMessageBox.information(self, "儲存完成", "品管資料位置已更新。")
        self.refresh()
        return True
