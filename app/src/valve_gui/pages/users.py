from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from valve_gui.config_store import save_app_config
from valve_gui.models import AppState, UserAccount
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_DEVELOPER,
    default_role_labels,
    default_role_permissions,
    role_label,
)


class UserManagementPage(QWidget):
    def __init__(self, state: AppState, on_saved=None, on_logout=None):
        super().__init__()
        self.state = state
        self.on_saved = on_saved
        self.on_logout = on_logout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("用戶階級與帳號管理")
        title.setObjectName("pageTitle")
        logout_button = QPushButton("登出並釋放硬體")
        logout_button.clicked.connect(self.logout)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(logout_button)

        self.role_table = QTableWidget(0, 2 + len(CONFIGURABLE_PERMISSIONS))
        self.role_table.setHorizontalHeaderLabels(
            ["階級代碼", "顯示名稱"] + [PERMISSION_LABELS.get(permission, permission) for permission in CONFIGURABLE_PERMISSIONS]
        )

        role_actions = QHBoxLayout()
        add_role_button = QPushButton("新增階級")
        add_role_button.clicked.connect(self.add_role_row)
        remove_role_button = QPushButton("刪除選取階級")
        remove_role_button.clicked.connect(self.remove_selected_role)
        role_actions.addWidget(add_role_button)
        role_actions.addWidget(remove_role_button)
        role_actions.addStretch()

        self.user_table = QTableWidget(0, 5)
        self.user_table.setHorizontalHeaderLabels(["啟用", "帳號", "姓名", "階級", "密碼"])

        user_actions = QHBoxLayout()
        add_user_button = QPushButton("新增用戶")
        add_user_button.clicked.connect(self.add_user_row)
        remove_user_button = QPushButton("刪除選取用戶")
        remove_user_button.clicked.connect(self.remove_selected_user)
        user_actions.addWidget(add_user_button)
        user_actions.addWidget(remove_user_button)
        user_actions.addStretch()

        save_button = QPushButton("保存階級與用戶")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.save)

        layout.addLayout(header)
        layout.addWidget(QLabel("用戶階級"))
        layout.addWidget(self.role_table, 1)
        layout.addLayout(role_actions)
        layout.addWidget(QLabel("用戶帳號"))
        layout.addWidget(self.user_table, 1)
        layout.addLayout(user_actions)
        layout.addWidget(save_button)

    def refresh(self):
        self.load_roles()
        self.load_users()

    def load_roles(self):
        self.role_table.setRowCount(0)
        for role, label in self.state.role_labels.items():
            if role == ROLE_DEVELOPER:
                continue
            self.add_role_row(role, label, self.state.role_permissions.get(role, set()))

    def add_role_row(self, role=None, label=None, permissions=None):
        if role is None:
            role = self.next_role_key()
            label = "新階級"
            permissions = set()
        row = self.role_table.rowCount()
        self.role_table.insertRow(row)
        self.role_table.setItem(row, 0, QTableWidgetItem(role))
        self.role_table.setItem(row, 1, QTableWidgetItem(label or role))
        permissions = permissions or set()
        for col, permission in enumerate(CONFIGURABLE_PERMISSIONS, start=2):
            checkbox = QCheckBox()
            checkbox.setChecked(permission in permissions)
            self.role_table.setCellWidget(row, col, checkbox)

    def remove_selected_role(self):
        row = self.role_table.currentRow()
        if row < 0:
            return
        role_item = self.role_table.item(row, 0)
        role = role_item.text().strip() if role_item else ""
        if any(self.user_role_at(user_row) == role for user_row in range(self.user_table.rowCount())):
            QMessageBox.warning(self, "無法刪除", "此階級仍有用戶使用，請先調整用戶階級。")
            return
        self.role_table.removeRow(row)
        self.refresh_user_role_combos()

    def load_users(self):
        self.user_table.setRowCount(0)
        for account in self.state.user_accounts:
            self.add_user_row(account)

    def add_user_row(self, account=None):
        account = account or UserAccount(
            username=self.next_username(),
            display_name="新用戶",
            role=self.default_user_role(),
            password="",
            enabled=True,
        )
        row = self.user_table.rowCount()
        self.user_table.insertRow(row)

        enabled = QCheckBox()
        enabled.setChecked(account.enabled)
        self.user_table.setCellWidget(row, 0, enabled)
        self.user_table.setItem(row, 1, QTableWidgetItem(account.username))
        self.user_table.setItem(row, 2, QTableWidgetItem(account.display_name))

        role_combo = QComboBox()
        self.populate_role_combo(role_combo, account.role)
        self.user_table.setCellWidget(row, 3, role_combo)

        password = QLineEdit(account.password)
        password.setEchoMode(QLineEdit.EchoMode.Password)
        self.user_table.setCellWidget(row, 4, password)

    def remove_selected_user(self):
        row = self.user_table.currentRow()
        if row >= 0:
            self.user_table.removeRow(row)

    def populate_role_combo(self, combo, selected_role=""):
        combo.clear()
        for role, label in self.current_role_options():
            combo.addItem(label, role)
        match = combo.findData(selected_role)
        if match >= 0:
            combo.setCurrentIndex(match)

    def refresh_user_role_combos(self):
        for row in range(self.user_table.rowCount()):
            combo = self.user_table.cellWidget(row, 3)
            if combo:
                selected = combo.currentData()
                self.populate_role_combo(combo, selected)

    def current_role_options(self):
        roles = []
        for row in range(self.role_table.rowCount()):
            role_item = self.role_table.item(row, 0)
            label_item = self.role_table.item(row, 1)
            role = role_item.text().strip() if role_item else ""
            label = label_item.text().strip() if label_item else role
            if role and role != ROLE_DEVELOPER:
                roles.append((role, label or role))
        return roles

    def user_role_at(self, row):
        combo = self.user_table.cellWidget(row, 3)
        return combo.currentData() if combo else ""

    def save(self):
        role_labels = {ROLE_DEVELOPER: self.state.role_labels.get(ROLE_DEVELOPER, role_label(ROLE_DEVELOPER))}
        role_permissions = default_role_permissions()
        role_keys = set(role_labels)

        for row in range(self.role_table.rowCount()):
            role_item = self.role_table.item(row, 0)
            label_item = self.role_table.item(row, 1)
            role = role_item.text().strip() if role_item else ""
            label = label_item.text().strip() if label_item else role
            if not role or role == ROLE_DEVELOPER:
                QMessageBox.warning(self, "資料錯誤", "階級代碼不可空白，也不可使用 developer。")
                return
            if role in role_keys:
                QMessageBox.warning(self, "資料錯誤", f"階級代碼重複：{role}")
                return
            role_keys.add(role)
            role_labels[role] = label or role
            role_permissions[role] = {
                permission
                for col, permission in enumerate(CONFIGURABLE_PERMISSIONS, start=2)
                if self.role_table.cellWidget(row, col) and self.role_table.cellWidget(row, col).isChecked()
            }

        users = []
        usernames = set()
        for row in range(self.user_table.rowCount()):
            username_item = self.user_table.item(row, 1)
            display_item = self.user_table.item(row, 2)
            username = username_item.text().strip() if username_item else ""
            display_name = display_item.text().strip() if display_item else username
            role = self.user_role_at(row)
            if not username:
                QMessageBox.warning(self, "資料錯誤", "用戶帳號不可空白。")
                return
            if username in usernames:
                QMessageBox.warning(self, "資料錯誤", f"用戶帳號重複：{username}")
                return
            if role not in role_keys or role == ROLE_DEVELOPER:
                QMessageBox.warning(self, "資料錯誤", f"{username} 的階級不存在。")
                return
            usernames.add(username)
            enabled = self.user_table.cellWidget(row, 0)
            password = self.user_table.cellWidget(row, 4)
            users.append(
                UserAccount(
                    username=username,
                    display_name=display_name or username,
                    role=role,
                    password=password.text() if password else "",
                    enabled=enabled.isChecked() if enabled else True,
                )
            )

        self.state.role_labels = role_labels
        self.state.role_permissions = role_permissions
        self.state.role_passwords = {
            role: self.state.role_passwords.get(role, "")
            for role in role_labels
        }
        self.state.user_accounts = users
        save_app_config(self.state)
        if self.on_saved:
            self.on_saved()
        QMessageBox.information(self, "保存完成", "用戶階級與帳號已更新。")
        self.refresh()

    def next_role_key(self):
        index = 1
        existing = {role for role, _ in self.current_role_options()} | set(self.state.role_labels)
        while f"role_{index}" in existing:
            index += 1
        return f"role_{index}"

    def next_username(self):
        index = 1
        existing = {
            self.user_table.item(row, 1).text().strip()
            for row in range(self.user_table.rowCount())
            if self.user_table.item(row, 1)
        } | {account.username for account in self.state.user_accounts}
        while f"user{index}" in existing:
            index += 1
        return f"user{index}"

    def default_user_role(self):
        roles = self.current_role_options()
        return roles[0][0] if roles else "operator"

    def logout(self):
        if self.on_logout:
            self.on_logout()
