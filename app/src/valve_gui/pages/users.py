import re

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from valve_gui.config_store import save_app_config
from valve_gui.models import AppState, UserAccount
from valve_gui.permissions import (
    CONFIGURABLE_PERMISSIONS,
    PERMISSION_LABELS,
    ROLE_DEVELOPER,
    ROLE_OPERATOR,
    ROLE_PERMISSIONS,
    role_label,
)


ROLE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
LETTER_PATTERN = re.compile(r"[A-Za-z\u3400-\u9fff]")
TABLE_ROW_HEIGHT = 45
ROLE_ROW_HEIGHT = TABLE_ROW_HEIGHT
USER_ROW_HEIGHT = TABLE_ROW_HEIGHT
TABLE_INPUT_HEIGHT = 45


class UserManagementPage(QWidget):
    def __init__(self, state: AppState, on_saved=None, on_logout=None):
        super().__init__()
        self.state = state
        self.on_saved = on_saved
        self.on_logout = on_logout
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("使用者管理")
        title.setObjectName("pageTitle")
        subtitle = QLabel("設定使用者密碼、角色位階排序，以及各角色可控制的操作介面權限。")
        subtitle.setObjectName("mutedText")

        title_block = QVBoxLayout()
        title_block.setSpacing(4)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        header.addLayout(title_block)
        header.addStretch()

        self.tabs = QTabWidget()
        self.tabs.setObjectName("userManagementTabs")
        self.tabs.addTab(self.build_rank_tab(), "使用者密碼設定")
        self.tabs.addTab(self.build_user_permission_tab(), "操作介面權限控制")

        self.status_label = QLabel("")
        self.status_label.setObjectName("mutedText")

        layout.addLayout(header)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.status_label)

    def build_rank_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel("在這裡新增或刪除角色位階。位階數值越小代表階級越低，數值越大代表階級越高。")
        hint.setObjectName("mutedText")

        developer_box = QGroupBox("開發者")
        developer_form = QFormLayout(developer_box)
        self.developer_password = self.create_password_editor()
        developer_form.addRow("Developer 登入密鑰", self.developer_password)

        self.role_table = QTableWidget(0, 4)
        self.role_table.setHorizontalHeaderLabels(["位階", "角色代碼", "角色名稱", "角色登入密鑰"])
        self.role_table.setAlternatingRowColors(True)
        self.role_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.role_table.verticalHeader().setVisible(False)
        self.role_table.verticalHeader().setDefaultSectionSize(ROLE_ROW_HEIGHT)
        self.role_table.verticalHeader().setMinimumSectionSize(ROLE_ROW_HEIGHT)
        self.role_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.role_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        actions = QHBoxLayout()
        add_button = QPushButton("新增位階")
        add_button.clicked.connect(lambda: self.add_role_row())
        remove_button = QPushButton("刪除選取位階")
        remove_button.clicked.connect(self.remove_selected_role)
        move_up_button = QPushButton("降低位階")
        move_up_button.clicked.connect(lambda: self.move_selected_role(-1))
        move_down_button = QPushButton("提高位階")
        move_down_button.clicked.connect(lambda: self.move_selected_role(1))
        self.add_role_button = add_button
        self.remove_role_button = remove_button
        self.move_role_down_button = move_up_button
        self.move_role_up_button = move_down_button
        actions.addWidget(add_button)
        actions.addWidget(remove_button)
        actions.addWidget(move_up_button)
        actions.addWidget(move_down_button)
        actions.addStretch()

        layout.addWidget(hint)
        layout.addWidget(developer_box)
        layout.addWidget(self.role_table, 1)
        layout.addLayout(actions)
        return page

    def build_user_permission_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        permission_hint = QLabel("依角色位階管理可控制的畫面功能。開發者固定擁有全部權限。")
        permission_hint.setObjectName("mutedText")

        self.permission_table = QTableWidget(0, 2 + len(CONFIGURABLE_PERMISSIONS))
        self.permission_table.setHorizontalHeaderLabels(
            ["位階", "角色位階"] + [PERMISSION_LABELS.get(permission, permission) for permission in CONFIGURABLE_PERMISSIONS]
        )
        self.permission_table.setAlternatingRowColors(True)
        self.permission_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.permission_table.verticalHeader().setVisible(False)
        self.permission_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.permission_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(permission_hint)
        layout.addWidget(self.permission_table, 1)
        return page

    def refresh(self):
        self._loading = True
        self.set_password_text(self.developer_password, self.state.role_passwords.get(ROLE_DEVELOPER, ""))
        self.load_roles()
        self.load_users()
        self._loading = False
        self.update_status()

    def load_roles(self):
        self.role_table.setRowCount(0)
        self.permission_table.setRowCount(0)
        for role, label in self.state.role_labels.items():
            if role == ROLE_DEVELOPER:
                continue
            self.add_role_row(
                role=role,
                label=label,
                permissions=self.state.role_permissions.get(role, set()),
                password=self.state.role_passwords.get(role, ""),
            )
        self.update_rank_numbers()

    def add_role_row(self, role=None, label=None, permissions=None, password=""):
        if role is None:
            role = self.next_role_key()
            label = "新位階"
            permissions = set()

        row = self.role_table.rowCount()
        self.role_table.insertRow(row)
        self.set_readonly_item(self.role_table, row, 0, "")
        role_input = self.create_table_input(role)
        label_input = self.create_table_input(label or role)
        role_input.textChanged.connect(self.on_role_editor_changed)
        label_input.textChanged.connect(self.on_role_editor_changed)
        self.role_table.setCellWidget(row, 1, role_input)
        self.role_table.setCellWidget(row, 2, label_input)

        password_input = self.create_password_editor(password)
        password_input.setPlaceholderText("可留空")
        self.role_table.setCellWidget(row, 3, password_input)
        self.role_table.setRowHeight(row, ROLE_ROW_HEIGHT)

        self.add_permission_row(row, role, label or role, permissions or set())
        self.update_rank_numbers()
        self.refresh_user_role_combos()
        self.update_status()

    def add_permission_row(self, row, role, label, permissions):
        self.permission_table.insertRow(row)
        self.set_readonly_item(self.permission_table, row, 0, "")
        self.set_readonly_item(self.permission_table, row, 1, self.role_display_text(role, label))
        for col, permission in enumerate(CONFIGURABLE_PERMISSIONS, start=2):
            checkbox = QCheckBox()
            checkbox.setChecked(permission in permissions)
            checkbox.setToolTip(PERMISSION_LABELS.get(permission, permission))
            self.permission_table.setCellWidget(row, col, self.centered_widget(checkbox))

    def remove_selected_role(self):
        row = self.role_table.currentRow()
        if row < 0:
            return

        role = self.role_key_at(row)
        if any(account.role == role for account in self.state.user_accounts):
            QMessageBox.warning(self, "無法刪除", "此角色位階仍有使用者，請先調整使用者的角色位階。")
            return

        self.role_table.removeRow(row)
        self.permission_table.removeRow(row)
        self.update_rank_numbers()
        self.refresh_user_role_combos()
        self.update_status()

    def move_selected_role(self, direction):
        row = self.role_table.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= self.role_table.rowCount():
            return

        roles = self.current_role_rows()
        roles[row], roles[target] = roles[target], roles[row]
        selected_role = roles[target]["role"]
        self.reload_role_rows(roles)
        self.select_role_row(selected_role)
        self.refresh_user_role_combos()

    def reload_role_rows(self, roles):
        self._loading = True
        self.role_table.setRowCount(0)
        self.permission_table.setRowCount(0)
        for role_data in roles:
            self.add_role_row(
                role=role_data["role"],
                label=role_data["label"],
                permissions=role_data["permissions"],
                password=role_data["password"],
            )
        self._loading = False
        self.update_rank_numbers()

    def select_role_row(self, role):
        for row in range(self.role_table.rowCount()):
            if self.role_key_at(row) == role:
                self.role_table.selectRow(row)
                return

    def load_users(self):
        if not hasattr(self, "user_table"):
            return
        self.user_table.setRowCount(0)
        for account in self.state.user_accounts:
            self.add_user_row(account)

    def add_user_row(self, account=None):
        account = account or UserAccount(
            username=self.next_username(),
            display_name="新使用者",
            role=self.default_user_role(),
            password="",
            enabled=True,
        )

        row = self.user_table.rowCount()
        self.user_table.insertRow(row)

        enabled = QCheckBox()
        enabled.setChecked(account.enabled)
        enabled.setToolTip("是否允許此帳號登入")
        self.user_table.setCellWidget(row, 0, self.centered_widget(enabled))
        self.set_table_item(self.user_table, row, 1, account.username)
        self.set_table_item(self.user_table, row, 2, account.display_name)

        role_combo = QComboBox()
        self.populate_role_combo(role_combo, account.role)
        self.user_table.setCellWidget(row, 3, role_combo)

        password = self.create_password_editor(account.password)
        password.setPlaceholderText("留空則使用角色密鑰")
        self.user_table.setCellWidget(row, 4, password)
        self.user_table.setRowHeight(row, USER_ROW_HEIGHT)
        self.update_status()

    def remove_selected_user(self):
        row = self.user_table.currentRow()
        if row >= 0:
            self.user_table.removeRow(row)
            self.update_status()

    def populate_role_combo(self, combo, selected_role=""):
        combo.blockSignals(True)
        combo.clear()
        combo.setEditable(True)
        combo.lineEdit().setReadOnly(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for role, label in self.current_role_options():
            combo.addItem(label, role)
        match = combo.findData(selected_role)
        combo.setCurrentIndex(match if match >= 0 else 0)
        self.apply_combo_alignment(combo)
        combo.blockSignals(False)
        combo.currentTextChanged.connect(lambda _text, target=combo: self.apply_combo_alignment(target))

    def refresh_user_role_combos(self):
        if not hasattr(self, "user_table"):
            return
        for row in range(self.user_table.rowCount()):
            combo = self.user_table.cellWidget(row, 3)
            if combo:
                selected = combo.currentData()
                self.populate_role_combo(combo, selected)

    def current_role_options(self):
        roles = []
        seen = set()
        for row in range(self.role_table.rowCount()):
            role = self.role_key_at(row)
            label = self.role_label_at(row)
            if role and role != ROLE_DEVELOPER and role not in seen:
                roles.append((role, self.role_display_text(role, label)))
                seen.add(role)
        return roles

    def current_role_rows(self):
        rows = []
        for row in range(self.role_table.rowCount()):
            rows.append(
                {
                    "role": self.role_key_at(row),
                    "label": self.role_label_at(row),
                    "password": self.role_password_at(row),
                    "permissions": self.permission_set_at(row),
                }
            )
        return rows

    def role_key_at(self, row):
        editor = self.role_table.cellWidget(row, 1)
        if isinstance(editor, QLineEdit):
            return editor.text().strip()
        item = self.role_table.item(row, 1)
        return item.text().strip() if item else ""

    def role_label_at(self, row):
        editor = self.role_table.cellWidget(row, 2)
        if isinstance(editor, QLineEdit):
            return editor.text().strip()
        role = self.role_key_at(row)
        item = self.role_table.item(row, 2)
        return item.text().strip() if item else role

    def role_password_at(self, row):
        password_input = self.role_table.cellWidget(row, 3)
        editor = self.line_edit_from_widget(password_input)
        return editor.text().strip() if editor else ""

    def permission_set_at(self, row):
        return {
            permission
            for col, permission in enumerate(CONFIGURABLE_PERMISSIONS, start=2)
            if self.checkbox_at(self.permission_table, row, col)
            and self.checkbox_at(self.permission_table, row, col).isChecked()
        }

    def user_role_at(self, row):
        if not hasattr(self, "user_table"):
            return ""
        combo = self.user_table.cellWidget(row, 3)
        return combo.currentData() if combo else ""

    def on_role_editor_changed(self):
        if self._loading:
            return
        sender = self.sender()
        row = self.role_editor_row(sender)
        if row < 0:
            return
        role = self.role_key_at(row)
        label = self.role_label_at(row)
        self.set_readonly_item(self.permission_table, row, 1, self.role_display_text(role, label))
        self.refresh_user_role_combos()

    def on_user_item_changed(self, item):
        self.apply_item_alignment(item)

    def role_editor_row(self, editor):
        for row in range(self.role_table.rowCount()):
            if editor in {self.role_table.cellWidget(row, 1), self.role_table.cellWidget(row, 2)}:
                return row
        return -1

    def update_rank_numbers(self):
        for row in range(self.role_table.rowCount()):
            rank = str(row + 1)
            self.set_readonly_item(self.role_table, row, 0, rank)
            self.set_readonly_item(self.permission_table, row, 0, rank)
            role = self.role_key_at(row)
            label = self.role_label_at(row)
            self.set_readonly_item(self.permission_table, row, 1, self.role_display_text(role, label))
        self.apply_role_row_heights()
        self.apply_user_row_heights()

    def apply_role_row_heights(self):
        for row in range(self.role_table.rowCount()):
            self.role_table.setRowHeight(row, ROLE_ROW_HEIGHT)

    def apply_user_row_heights(self):
        if not hasattr(self, "user_table"):
            return
        for row in range(self.user_table.rowCount()):
            self.user_table.setRowHeight(row, USER_ROW_HEIGHT)

    def set_readonly_item(self, table, row, column, text):
        item = self.set_table_item(table, row, column, text)
        item.setText(text)
        if table is self.role_table and column == 0:
            item.setSizeHint(QSize(0, ROLE_ROW_HEIGHT))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def set_table_item(self, table, row, column, text):
        item = table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            table.setItem(row, column, item)
        item.setText(text)
        self.apply_item_alignment(item)
        return item

    def create_table_input(self, text="", password=False):
        editor = QLineEdit(text)
        editor.setFixedHeight(TABLE_INPUT_HEIGHT)
        self.apply_editor_alignment(editor)
        editor.textChanged.connect(lambda _text, target=editor: self.apply_editor_alignment(target))
        if password:
            editor.setEchoMode(QLineEdit.EchoMode.Password)
        return editor

    def create_password_editor(self, text=""):
        editor = self.create_table_input(text, password=True)
        button = QPushButton("◉")
        button.setObjectName("passwordToggleButton")
        button.setToolTip("顯示密碼")
        button.setFixedHeight(TABLE_INPUT_HEIGHT)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        def toggle_password():
            hidden = editor.echoMode() == QLineEdit.EchoMode.Password
            editor.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
            button.setText("◎" if hidden else "◉")
            button.setToolTip("隱藏密碼" if hidden else "顯示密碼")

        button.clicked.connect(toggle_password)

        wrapper = QWidget()
        wrapper.setFixedHeight(TABLE_INPUT_HEIGHT)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(editor, 9)
        layout.addWidget(button, 1)
        wrapper.setPlaceholderText = editor.setPlaceholderText
        return wrapper

    def line_edit_from_widget(self, widget):
        if isinstance(widget, QLineEdit):
            return widget
        if isinstance(widget, QWidget):
            return widget.findChild(QLineEdit)
        return None

    def password_text(self, widget):
        editor = self.line_edit_from_widget(widget)
        return editor.text().strip() if editor else ""

    def set_password_text(self, widget, text):
        editor = self.line_edit_from_widget(widget)
        if editor:
            editor.setText(text)

    def centered_widget(self, child):
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(child)
        return wrapper

    def checkbox_at(self, table, row, column):
        widget = table.cellWidget(row, column)
        if isinstance(widget, QCheckBox):
            return widget
        if isinstance(widget, QWidget):
            return widget.findChild(QCheckBox)
        return None

    def apply_item_alignment(self, item):
        item.setTextAlignment(self.alignment_for_text(item.text()))

    def apply_editor_alignment(self, editor):
        editor.setAlignment(self.alignment_for_text(editor.text()))

    def apply_combo_alignment(self, combo):
        if combo.isEditable() and combo.lineEdit():
            combo.lineEdit().setAlignment(self.alignment_for_text(combo.currentText()))

    def alignment_for_text(self, text):
        horizontal = Qt.AlignmentFlag.AlignLeft if LETTER_PATTERN.search(text or "") else Qt.AlignmentFlag.AlignCenter
        return horizontal | Qt.AlignmentFlag.AlignVCenter

    def role_display_text(self, role, label):
        return f"{label or role} ({role})"

    def save(self):
        role_data = self.collect_roles()
        if role_data is None:
            return
        role_labels, role_permissions, role_passwords, role_keys = role_data

        users = self.state.user_accounts

        self.state.role_labels = role_labels
        self.state.role_permissions = role_permissions
        self.state.role_passwords = role_passwords
        self.state.user_accounts = users
        save_app_config(self.state)

        if self.on_saved:
            self.on_saved()

        QMessageBox.information(self, "儲存完成", "用戶、角色位階與畫面權限設定已更新。")
        self.refresh()

    def collect_roles(self):
        developer_password = self.password_text(self.developer_password)
        if not developer_password:
            QMessageBox.warning(self, "資料錯誤", "Developer 登入密鑰不可空白。")
            return None

        role_labels = {ROLE_DEVELOPER: role_label(ROLE_DEVELOPER)}
        role_permissions = {ROLE_DEVELOPER: set(ROLE_PERMISSIONS[ROLE_DEVELOPER])}
        role_passwords = {ROLE_DEVELOPER: developer_password}
        role_keys = {ROLE_DEVELOPER}

        for row in range(self.role_table.rowCount()):
            role = self.role_key_at(row)
            label = self.role_label_at(row)

            if not role:
                QMessageBox.warning(self, "資料錯誤", "角色代碼不可空白。")
                return None
            if role == ROLE_DEVELOPER:
                QMessageBox.warning(self, "資料錯誤", "developer 為系統保留角色，不能作為一般角色位階。")
                return None
            if not ROLE_KEY_PATTERN.match(role):
                QMessageBox.warning(self, "資料錯誤", f"角色代碼只能使用英數字、底線或連字號：{role}")
                return None
            if role in role_keys:
                QMessageBox.warning(self, "資料錯誤", f"角色代碼重複：{role}")
                return None

            role_keys.add(role)
            role_labels[role] = label or role
            role_passwords[role] = self.role_password_at(row)
            role_permissions[role] = self.permission_set_at(row)

        if len(role_keys) == 1:
            QMessageBox.warning(self, "資料錯誤", "至少需要保留一個可分配給使用者的角色位階。")
            return None

        return role_labels, role_permissions, role_passwords, role_keys

    def collect_users(self, role_keys):
        if not hasattr(self, "user_table"):
            return list(self.state.user_accounts)
        users = []
        usernames = set()
        for row in range(self.user_table.rowCount()):
            username_item = self.user_table.item(row, 1)
            display_item = self.user_table.item(row, 2)
            username = username_item.text().strip() if username_item else ""
            display_name = display_item.text().strip() if display_item else username
            role = self.user_role_at(row)

            if not username:
                QMessageBox.warning(self, "資料錯誤", "帳號不可空白。")
                return None
            if not ROLE_KEY_PATTERN.match(username):
                QMessageBox.warning(self, "資料錯誤", f"帳號只能使用英數字、底線或連字號：{username}")
                return None
            if username in usernames:
                QMessageBox.warning(self, "資料錯誤", f"帳號重複：{username}")
                return None
            if role not in role_keys or role == ROLE_DEVELOPER:
                QMessageBox.warning(self, "資料錯誤", f"{username} 的角色位階不存在。")
                return None

            enabled = self.checkbox_at(self.user_table, row, 0)
            password = self.line_edit_from_widget(self.user_table.cellWidget(row, 4))
            usernames.add(username)
            users.append(
                UserAccount(
                    username=username,
                    display_name=display_name or username,
                    role=role,
                    password=password.text().strip() if password else "",
                    enabled=enabled.isChecked() if enabled else True,
                )
            )
        return users

    def next_role_key(self):
        index = 1
        existing = {role for role, _ in self.current_role_options()} | set(self.state.role_labels)
        while f"role_{index}" in existing:
            index += 1
        return f"role_{index}"

    def next_username(self):
        if not hasattr(self, "user_table"):
            return "user1"
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
        if roles:
            return roles[0][0]
        return ROLE_OPERATOR

    def update_status(self):
        if hasattr(self, "status_label"):
            user_count = self.user_table.rowCount() if hasattr(self, "user_table") else len(self.state.user_accounts)
            self.status_label.setText(
                f"目前共有 {user_count} 個使用者、{self.role_table.rowCount()} 個一般角色位階。"
            )

    def logout(self):
        if self.on_logout:
            self.on_logout()
