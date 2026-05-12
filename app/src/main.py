import sys

from PyQt6.QtWidgets import QApplication

from valve_gui.main_window import MainWindow
from valve_gui.paths import DATA_DIR
from valve_gui.styles import apply_styles


def main():
    DATA_DIR.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    apply_styles(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
