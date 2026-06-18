import sys
import os
from pathlib import Path


def _bootstrap_frozen_qt() -> None:
    if not getattr(sys, "frozen", False):
        return

    base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    qt_bin_dir = base_dir / "PyQt6" / "Qt6" / "bin"
    if not qt_bin_dir.is_dir():
        return

    os.environ["PATH"] = str(qt_bin_dir) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(qt_bin_dir))


_bootstrap_frozen_qt()

from PyQt6.QtWidgets import QApplication


ROOT_DIR = Path(__file__).resolve().parent
APP_SRC_DIR = ROOT_DIR / "app" / "src"
if str(APP_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(APP_SRC_DIR))

from valve_gui.main_window import MainWindow # type: ignore
from valve_gui.paths import DATA_DIR # type: ignore
from valve_gui.styles import apply_styles # type: ignore


def main():
    DATA_DIR.mkdir(exist_ok=True)
    app = QApplication(sys.argv)
    apply_styles(app)
    window = MainWindow()
    window.show_with_display_config()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
