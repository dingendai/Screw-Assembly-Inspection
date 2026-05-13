from datetime import datetime

from PyQt6.QtGui import QAction
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QSizePolicy, QStackedWidget, QWidget

from valve_gui.config_store import load_app_config
from valve_gui.model_registry import ensure_model_configs
from valve_gui.models import AppState, InspectionRecord
from valve_gui.pages.history import HistoryPage
from valve_gui.pages.login import LoginPage
from valve_gui.pages.monitor import MonitorPage
from valve_gui.pages.settings import SettingsPage
from valve_gui.paths import DATA_DIR, SESSION_LOG_PATH
from valve_gui.permissions import (
    PERMISSION_OPEN_SETTINGS,
    ROLE_OPERATOR,
    has_permission,
    role_label,
)
from valve_gui.storage import write_sessions_csv


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        load_app_config(self.state)
        ensure_model_configs(self.state)
        self.setWindowTitle("Gas Valve Vision Inspection System")
        self.setMinimumSize(640, 480)

        self.stack = QStackedWidget()
        self.login_page = LoginPage(
            self.state,
            self.after_login,
            on_display_change=self.apply_display_config,
            on_exit=self.exit_application,
        )
        self.monitor_page = MonitorPage(self.state, self.add_record, self.logout)
        self.settings_page = SettingsPage(
            self.state,
            self.after_settings,
            before_camera_scan=self.release_inspection_hardware,
            on_display_change=self.apply_display_config,
            on_logout=self.logout,
        )
        self.history_page = HistoryPage(self.state)
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.monitor_page)
        self.stack.addWidget(self.history_page)
        self.setCentralWidget(self.stack)

        self.actions = {}
        self.create_toolbar()
        self.update_navigation()
        self.start_all_cameras_on_boot()

    def show_with_display_config(self):
        self.apply_display_config(show_window=True)

    def apply_display_config(self, show_window=False):
        mode = self.state.display.mode
        if mode == "fullscreen":
            self.showFullScreen()
            return

        self.showNormal()
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if mode == "custom":
            width = self.state.display.width
            height = self.state.display.height
            min_width = 640
            min_height = 480
            if available:
                min_width = min(min_width, available.width())
                min_height = min(min_height, available.height())
                width = min(width, available.width())
                height = min(height, available.height())
            self.resize(QSize(max(min_width, width), max(min_height, height)))
            self.center_on_screen(available)
            if show_window:
                self.show()
            return

        if show_window:
            self.show()
        self.showMaximized()

    def center_on_screen(self, available):
        if not available:
            return
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def start_all_cameras_on_boot(self):
        self.login_page.start_preview()
        self.monitor_page.start()

    def create_toolbar(self):
        toolbar = self.addToolBar("Navigation")
        toolbar.setMovable(False)
        action_specs = [
            ("login", "登入", self.show_login),
            ("settings", "相機設定", self.show_settings),
            ("monitor", "監視", self.show_monitor),
            ("history", "歷史紀錄", self.show_history),
            ("logout", "登出", self.logout),
        ]
        for key, text, callback in action_specs:
            action = QAction(text, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)
            self.actions[key] = action

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.role_badge = QLabel()
        self.role_badge.setObjectName("roleBadge")
        toolbar.addWidget(self.role_badge)

    def update_navigation(self):
        logged_in = self.state.is_logged_in
        settings_ready = self.state.settings_applied
        self.actions["login"].setVisible(not logged_in)
        self.actions["settings"].setVisible(
            logged_in and has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS)
        )
        self.actions["monitor"].setVisible(logged_in and settings_ready)
        self.actions["history"].setVisible(logged_in and settings_ready)
        self.actions["logout"].setVisible(logged_in)
        if logged_in:
            self.role_badge.setText(f"目前權限：{role_label(self.state.operator_role)}")
        else:
            self.role_badge.setText("目前權限：未登入")

    def require_login(self):
        if not self.state.is_logged_in:
            QMessageBox.warning(self, "尚未登入", "請先登入操作者。")
            self.stack.setCurrentWidget(self.login_page)
            return False
        return True

    def show_login(self):
        if self.state.is_logged_in:
            return
        self.login_page.populate_camera_indexes(self.state.operator_camera_index)
        self.login_page.load_display_controls()
        self.stack.setCurrentWidget(self.login_page)

    def show_settings(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入相機設定。")
            self.show_monitor()
            return
        self.release_inspection_hardware()
        self.settings_page.refresh()
        self.stack.setCurrentWidget(self.settings_page)

    def after_login(self):
        if self.state.operator_role == ROLE_OPERATOR:
            self.state.settings_applied = True
            self.update_navigation()
            self.monitor_page.start()
            self.stack.setCurrentWidget(self.monitor_page)
            return
        self.update_navigation()
        self.release_inspection_hardware()
        self.settings_page.refresh()
        self.stack.setCurrentWidget(self.settings_page)

    def after_settings(self):
        self.settings_page.stop_preview()
        self.apply_display_config()
        self.update_navigation()
        self.monitor_page.start()
        self.stack.setCurrentWidget(self.monitor_page)

    def show_monitor(self):
        if not self.require_login():
            return
        if not self.state.settings_applied:
            QMessageBox.information(self, "尚未套用設定", "請先套用相機設定。")
            self.show_settings()
            return
        self.settings_page.stop_preview()
        self.monitor_page.refresh()
        if not self.monitor_page.sources:
            self.monitor_page.start()
        self.stack.setCurrentWidget(self.monitor_page)

    def show_history(self):
        if not self.require_login():
            return
        if not self.state.settings_applied:
            self.show_settings()
            return
        self.settings_page.stop_preview()
        self.history_page.refresh()
        self.stack.setCurrentWidget(self.history_page)

    def add_record(self, record: InspectionRecord):
        self.state.records.insert(0, record)
        self.history_page.refresh()

    def release_inspection_hardware(self):
        self.monitor_page.stop()
        self.settings_page.stop_preview()

    def release_all_hardware(self):
        self.monitor_page.stop()
        self.settings_page.stop_preview()
        self.login_page.stop()

    def logout(self):
        if not self.state.is_logged_in:
            self.release_all_hardware()
            self.stack.setCurrentWidget(self.login_page)
            return

        logout_time = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        if self.state.sessions:
            self.state.sessions[0].logout_time = logout_time
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_sessions_csv(SESSION_LOG_PATH, self.state.sessions)

        self.release_all_hardware()
        self.state.operator_name = ""
        self.state.operator_role = ROLE_OPERATOR
        self.state.login_time = ""
        self.state.is_logged_in = False
        self.state.settings_applied = False
        self.login_page.reset()
        self.login_page.populate_camera_indexes(self.state.operator_camera_index)
        self.login_page.load_display_controls()
        self.update_navigation()
        self.stack.setCurrentWidget(self.login_page)

    def closeEvent(self, event):
        if self.state.is_logged_in:
            self.logout()
        else:
            self.release_all_hardware()
        super().closeEvent(event)

    def exit_application(self):
        self.release_all_hardware()
        QApplication.quit()
