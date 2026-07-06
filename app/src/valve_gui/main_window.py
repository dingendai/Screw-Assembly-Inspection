from datetime import datetime

from PyQt6.QtGui import QAction
from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QStackedWidget, QWidget

from valve_gui import qc_db
from valve_gui.config_store import load_app_config
from valve_gui.model_registry import ensure_model_configs
from valve_gui.models import AppState, InspectionRecord
from valve_gui.pages.help import HelpPage
from valve_gui.pages.history import HistoryPage
from valve_gui.pages.login import LoginPage
from valve_gui.pages.monitor import MonitorPage
from valve_gui.pages.qc_products import ProductMasterPage
from valve_gui.pages.qc_stats import StatisticsPage
from valve_gui.pages.regions import RegionSettingsPage
from valve_gui.pages.settings import DisplaySettingsPage, ModelSettingsPage, SettingsPage
from valve_gui.pages.users import UserManagementPage
from valve_gui.paths import DATA_DIR, RECORDS_LOG_PATH, SESSION_LOG_PATH, USER_RECORDS_DIR
from valve_gui.permissions import (
    PERMISSION_MANAGE_MODELS,
    PERMISSION_OPEN_HISTORY,
    PERMISSION_OPEN_MONITOR,
    PERMISSION_OPEN_SETTINGS,
    PERMISSION_QC_PRODUCT_MANAGE,
    PERMISSION_QC_VIEW,
    ROLE_DEVELOPER,
    ROLE_OPERATOR,
    has_permission,
    role_label,
)
from valve_gui.styles import apply_styles
from valve_gui.storage import append_record_csv, read_sessions_csv, write_sessions_csv, write_user_records_csv


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        load_app_config(self.state)
        # 載回先前的登入紀錄，避免登出時整檔覆寫把歷史 sessions 洗掉。
        self.state.sessions = read_sessions_csv(SESSION_LOG_PATH)
        apply_styles(QApplication.instance(), self.state.display.font_size)
        ensure_model_configs(self.state)
        self.setWindowTitle("Gas Valve Vision Inspection System")
        self.setMinimumSize(640, 480)

        self.stack = QStackedWidget()
        self.login_page = LoginPage(
            self.state,
            self.after_login,
            on_display_change=self.apply_display_config,
            on_exit=self.exit_application,
            on_release_cameras=self.release_all_hardware,
        )
        self.monitor_page = MonitorPage(self.state, self.add_record, self.logout)
        self.settings_page = SettingsPage(
            self.state,
            self.after_settings,
            before_camera_scan=self.release_inspection_hardware,
            on_display_change=self.apply_display_config,
            on_logout=self.logout,
        )
        self.model_page = ModelSettingsPage(self.state, self.after_model_settings_saved, self.logout)
        self.history_page = HistoryPage(self.state)
        self.qc_stats_page = StatisticsPage(self.state)
        self.qc_products_page = ProductMasterPage(self.state)
        self.display_page = DisplaySettingsPage(self.state, self.apply_display_config, self.logout)
        self.region_page = RegionSettingsPage(self.state, self.logout)
        self.user_page = UserManagementPage(self.state, self.after_user_management_saved, self.logout)
        self.help_page = HelpPage()
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.settings_page)
        self.stack.addWidget(self.model_page)
        self.stack.addWidget(self.monitor_page)
        self.stack.addWidget(self.history_page)
        self.stack.addWidget(self.qc_stats_page)
        self.stack.addWidget(self.qc_products_page)
        self.stack.addWidget(self.display_page)
        self.stack.addWidget(self.region_page)
        self.stack.addWidget(self.user_page)
        self.stack.addWidget(self.help_page)
        self.setCentralWidget(self.stack)

        self.actions = {}
        self.create_toolbar()
        self.stack.currentChanged.connect(self.update_active_action)
        self.update_navigation()
        self.start_all_cameras_on_boot()

    def show_with_display_config(self):
        self.apply_display_config(show_window=True)

    def apply_display_config(self, show_window=False):
        apply_styles(QApplication.instance(), self.state.display.font_size)
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
        self.restart_login_preview()

    def create_toolbar(self):
        toolbar = self.addToolBar("Navigation")
        toolbar.setMovable(False)
        action_specs = [
            ("login", "登入", self.show_login, True),
            ("settings", "相機設定", self.show_settings, True),
            ("models", "模型清單", self.show_models, True),
            ("regions", "指定範圍監視", self.show_region_settings, True),
            ("display", "GUI 顯示設定", self.show_display_settings, True),
            ("monitor", "監視", self.show_monitor, True),
            ("history", "歷史紀錄", self.show_history, True),
            ("qc_stats", "品管統計", self.show_qc_stats, True),
            ("qc_products", "品項主檔", self.show_qc_products, True),
            ("users", "用戶管理", self.show_users, True),
            ("help", "說明", self.show_help, True),
            ("logout", "登出", self.logout, False),
        ]
        for key, text, callback, checkable in action_specs:
            action = QAction(text, self)
            action.setCheckable(checkable)
            action.triggered.connect(callback)
            toolbar.addAction(action)
            if key == "logout":
                logout_tool_button = toolbar.widgetForAction(action)
                if logout_tool_button:
                    logout_tool_button.setObjectName("logoutButton")
            self.actions[key] = action

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.apply_settings_button = QPushButton("套用設定")
        self.apply_settings_button.setObjectName("primaryButton")
        self.apply_settings_button.clicked.connect(self.save_current_page_settings)
        self.apply_settings_action = toolbar.addWidget(self.apply_settings_button)
        self.enter_monitor_button = QPushButton("進入監測")
        self.enter_monitor_button.setObjectName("primaryButton")
        self.enter_monitor_button.clicked.connect(self.show_monitor)
        self.enter_monitor_action = toolbar.addWidget(self.enter_monitor_button)
        toolbar.addWidget(self.login_page.exit_button)
        self.role_badge = QLabel()
        self.role_badge.setObjectName("roleBadge")
        toolbar.addWidget(self.role_badge)

    def update_navigation(self):
        logged_in = self.state.is_logged_in
        settings_ready = self.state.settings_applied
        self.actions["login"].setVisible(not logged_in)
        self.actions["settings"].setVisible(
            logged_in and has_permission(
                self.state.operator_role,
                PERMISSION_OPEN_SETTINGS,
                self.state.role_permissions,
            )
        )
        self.actions["regions"].setVisible(
            logged_in and has_permission(
                self.state.operator_role,
                PERMISSION_OPEN_SETTINGS,
                self.state.role_permissions,
            )
        )
        self.actions["models"].setVisible(
            logged_in and has_permission(
                self.state.operator_role,
                PERMISSION_OPEN_SETTINGS,
                self.state.role_permissions,
            )
        )
        self.actions["display"].setVisible(True)
        self.actions["monitor"].setVisible(
            logged_in
            and settings_ready
            and has_permission(self.state.operator_role, PERMISSION_OPEN_MONITOR, self.state.role_permissions)
        )
        self.actions["history"].setVisible(
            logged_in
            and settings_ready
            and has_permission(self.state.operator_role, PERMISSION_OPEN_HISTORY, self.state.role_permissions)
        )
        self.actions["qc_stats"].setVisible(
            logged_in
            and settings_ready
            and has_permission(self.state.operator_role, PERMISSION_QC_VIEW, self.state.role_permissions)
        )
        self.actions["qc_products"].setVisible(
            logged_in
            and settings_ready
            and has_permission(self.state.operator_role, PERMISSION_QC_PRODUCT_MANAGE, self.state.role_permissions)
        )
        self.actions["users"].setVisible(logged_in and self.state.operator_role == ROLE_DEVELOPER)
        self.actions["help"].setVisible(True)
        self.actions["logout"].setVisible(logged_in)
        self.login_page.exit_button.setVisible(not logged_in)
        if logged_in:
            self.role_badge.setText(f"目前權限：{role_label(self.state.operator_role, self.state.role_labels)}")
        else:
            self.role_badge.setText("目前權限：未登入")
        self.update_apply_settings_button()
        self.update_active_action()

    def update_active_action(self):
        if not self.actions:
            return
        page_actions = {
            self.login_page: "login",
            self.settings_page: "settings",
            self.model_page: "models",
            self.region_page: "regions",
            self.monitor_page: "monitor",
            self.history_page: "history",
            self.qc_stats_page: "qc_stats",
            self.qc_products_page: "qc_products",
            self.display_page: "display",
            self.user_page: "users",
            self.help_page: "help",
        }
        active_key = page_actions.get(self.stack.currentWidget())
        for key, action in self.actions.items():
            if action.isCheckable():
                action.setChecked(key == active_key and action.isVisible())
        self.update_apply_settings_button()

    def update_apply_settings_button(self):
        if not hasattr(self, "apply_settings_button"):
            return
        should_show = self.current_page_save_handler() is not None
        self.apply_settings_button.setVisible(should_show)
        if hasattr(self, "apply_settings_action"):
            self.apply_settings_action.setVisible(should_show)
        monitor_visible = (
            self.state.is_logged_in
            and self.stack.currentWidget() != self.monitor_page
            and has_permission(self.state.operator_role, PERMISSION_OPEN_MONITOR, self.state.role_permissions)
        )
        self.enter_monitor_button.setVisible(monitor_visible)
        if hasattr(self, "enter_monitor_action"):
            self.enter_monitor_action.setVisible(monitor_visible)

    def current_page_save_handler(self):
        current = self.stack.currentWidget()
        if current == self.login_page:
            return None
        if (
            current == self.settings_page
            and self.state.is_logged_in
            and has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions)
        ):
            return self.apply_camera_settings_without_navigation
        if (
            current == self.model_page
            and self.state.is_logged_in
            and has_permission(self.state.operator_role, PERMISSION_MANAGE_MODELS, self.state.role_permissions)
        ):
            return self.model_page.save
        if (
            current == self.region_page
            and self.state.is_logged_in
            and has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions)
        ):
            return self.region_page.save_region_settings
        if current == self.display_page:
            return self.display_page.save_display_settings
        if current == self.user_page and self.state.is_logged_in and self.state.operator_role == ROLE_DEVELOPER:
            return self.user_page.save
        return None

    def save_current_page_settings(self):
        handler = self.current_page_save_handler()
        if handler:
            handler()

    def apply_camera_settings_without_navigation(self):
        if self.settings_page.apply(enter_monitor=False):
            self.monitor_page.router.clear_model_cache()
            self.apply_display_config()
            self.update_navigation()

    def require_login(self):
        if not self.state.is_logged_in:
            QMessageBox.warning(self, "尚未登入", "請先登入操作者。")
            self.release_all_hardware()
            self.restart_login_preview()
            self.stack.setCurrentWidget(self.login_page)
            return False
        return True

    def show_login(self):
        if self.state.is_logged_in:
            return
        self.restart_login_preview()
        self.stack.setCurrentWidget(self.login_page)
        self.update_apply_settings_button()

    def restart_login_preview(self):
        self.login_page.refresh_role_options()
        self.login_page.populate_camera_indexes(self.state.operator_camera_index)
        self.login_page.start_preview()

    def show_settings(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入相機設定。")
            self.show_monitor()
            return
        self.release_all_hardware()
        self.settings_page.refresh()
        self.stack.setCurrentWidget(self.settings_page)

    def show_models(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入模型清單。")
            self.show_monitor()
            return
        self.release_all_hardware()
        self.model_page.refresh()
        self.stack.setCurrentWidget(self.model_page)

    def show_display_settings(self):
        if self.state.is_logged_in and not has_permission(
            self.state.operator_role,
            PERMISSION_OPEN_SETTINGS,
            self.state.role_permissions,
        ):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入 GUI 顯示設定。")
            self.show_monitor()
            return
        self.release_all_hardware()
        self.display_page.refresh()
        self.stack.setCurrentWidget(self.display_page)

    def show_region_settings(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色無法進入指定範圍監視。")
            self.show_monitor()
            return
        self.release_all_hardware()
        self.region_page.refresh()
        self.stack.setCurrentWidget(self.region_page)

    def after_login(self):
        if self.state.operator_role == ROLE_OPERATOR:
            self.state.settings_applied = True
            self.update_navigation()
            self.release_all_hardware()
            if has_permission(self.state.operator_role, PERMISSION_OPEN_MONITOR, self.state.role_permissions):
                self.monitor_page.start()
                self.stack.setCurrentWidget(self.monitor_page)
            else:
                QMessageBox.information(self, "權限不足", "目前角色沒有可進入的監視頁面。")
            return
        self.update_navigation()
        self.release_all_hardware()
        if has_permission(self.state.operator_role, PERMISSION_OPEN_SETTINGS, self.state.role_permissions):
            self.settings_page.refresh()
            self.stack.setCurrentWidget(self.settings_page)
        elif has_permission(self.state.operator_role, PERMISSION_OPEN_MONITOR, self.state.role_permissions):
            self.state.settings_applied = True
            self.update_navigation()
            self.monitor_page.start()
            self.stack.setCurrentWidget(self.monitor_page)
        else:
            QMessageBox.information(self, "權限不足", "目前角色沒有可進入的 GUI 介面。")

    def after_settings(self):
        self.release_all_hardware()
        self.monitor_page.router.clear_model_cache()
        self.apply_display_config()
        self.update_navigation()
        if has_permission(self.state.operator_role, PERMISSION_OPEN_MONITOR, self.state.role_permissions):
            self.monitor_page.start()
            self.stack.setCurrentWidget(self.monitor_page)

    def after_model_settings_saved(self):
        self.monitor_page.router.clear_model_cache()
        self.settings_page.refresh_camera_model_combos()
        self.update_navigation()

    def show_monitor(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_MONITOR, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入監視頁面。")
            return
        if not self.state.settings_applied:
            QMessageBox.information(self, "尚未套用設定", "請先套用相機設定。")
            self.show_settings()
            return
        self.release_all_hardware()
        self.monitor_page.refresh()
        self.monitor_page.start()
        self.stack.setCurrentWidget(self.monitor_page)

    def show_history(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_OPEN_HISTORY, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入歷史紀錄。")
            return
        if not self.state.settings_applied:
            self.show_settings()
            return
        self.release_all_hardware()
        self.history_page.refresh()
        self.stack.setCurrentWidget(self.history_page)

    def show_qc_stats(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_QC_VIEW, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入品管統計。")
            self.show_monitor()
            return
        self.release_all_hardware()
        self.qc_stats_page.refresh()
        self.stack.setCurrentWidget(self.qc_stats_page)

    def show_qc_products(self):
        if not self.require_login():
            return
        if not has_permission(self.state.operator_role, PERMISSION_QC_PRODUCT_MANAGE, self.state.role_permissions):
            QMessageBox.warning(self, "權限不足", "目前角色不能進入品項主檔。")
            self.show_monitor()
            return
        self.release_all_hardware()
        self.qc_products_page.refresh()
        self.stack.setCurrentWidget(self.qc_products_page)

    def show_users(self):
        if not self.require_login():
            return
        if self.state.operator_role != ROLE_DEVELOPER:
            QMessageBox.warning(self, "權限不足", "只有開發者可以進入用戶管理。")
            return
        self.release_all_hardware()
        self.user_page.refresh()
        self.stack.setCurrentWidget(self.user_page)

    def show_help(self):
        self.release_all_hardware()
        self.help_page.refresh()
        self.stack.setCurrentWidget(self.help_page)
        self.update_apply_settings_button()

    def after_user_management_saved(self):
        self.login_page.refresh_role_options()
        self.update_navigation()

    def add_record(self, record: InspectionRecord):
        self.state.records.insert(0, record)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        append_record_csv(RECORDS_LOG_PATH, record)
        # SQLite 為歷史/品管查詢/統計的單一真相；CSV 暫時保留作過渡。
        if record.result in ("PASS", "NG") and record.part_id.strip():
            try:
                qc_db.record_inspection(
                    record.part_id.strip(),
                    record.result,
                    note=record.note,
                    operator=record.operator_name,
                    operator_role=record.operator_role,
                    confidence=record.confidence,
                    active_cameras=record.active_cameras,
                    inspected_at=record.timestamp,
                    session_id=self.state.current_work_session_id,
                    source=getattr(record, "barcode_source", ""),
                )
            except Exception:
                pass
        # 寫入 SQLite 後再刷新歷史頁，剛存的紀錄才查得到。
        self.history_page.refresh()

    def save_user_records(self, when):
        name = self.state.operator_name.strip()
        if not name:
            return
        user_records = [
            record for record in self.state.records if record.operator_name == name
        ]
        if not user_records:
            return
        USER_RECORDS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "user"
        path = USER_RECORDS_DIR / f"{safe_name} {when:%Y%m%d%H%M}.csv"
        write_user_records_csv(path, user_records, self.state.role_labels)

    def release_inspection_hardware(self):
        self.release_all_hardware()

    def release_all_hardware(self):
        self.monitor_page.stop()
        self.settings_page.stop_preview()
        self.model_page.stop_camera_photo_preview()
        self.region_page.stop()
        self.login_page.stop()

    def logout(self):
        if not self.state.is_logged_in:
            self.release_all_hardware()
            self.restart_login_preview()
            self.stack.setCurrentWidget(self.login_page)
            self.update_apply_settings_button()
            return

        now = datetime.now()
        logout_time = f"{now:%Y-%m-%d %H:%M:%S}"
        if self.state.sessions:
            self.state.sessions[0].logout_time = logout_time
        # 結束工作時段（= 登出）。
        try:
            qc_db.end_work_session(self.state.current_work_session_id, logout_time)
        except Exception:
            pass
        self.state.current_work_session_id = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_sessions_csv(SESSION_LOG_PATH, self.state.sessions, self.state.role_labels)
        self.save_user_records(now)

        self.release_all_hardware()
        self.state.operator_name = ""
        self.state.operator_role = ROLE_OPERATOR
        self.state.login_time = ""
        self.state.is_logged_in = False
        self.state.settings_applied = False
        self.login_page.reset()
        self.restart_login_preview()
        self.update_navigation()
        self.stack.setCurrentWidget(self.login_page)
        self.update_apply_settings_button()

    def closeEvent(self, event):
        if self.state.is_logged_in:
            self.logout()
        else:
            self.release_all_hardware()
        super().closeEvent(event)

    def exit_application(self):
        self.release_all_hardware()
        QApplication.quit()
