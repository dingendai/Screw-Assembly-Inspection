import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parent
APP_SRC_DIR = ROOT_DIR / "app" / "src"
if str(APP_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(APP_SRC_DIR))

from valve_gui.main_window import MainWindow
from valve_gui.paths import DATA_DIR
from valve_gui.styles import apply_styles


def main():
    DATA_DIR.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    apply_styles(app)
    window = MainWindow()
    window.show_with_display_config()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
