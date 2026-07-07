from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QPushButton, QToolButton


class _ButtonShadowFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.ChildAdded, QEvent.Type.Show):
            app = QApplication.instance()
            if app:
                QTimer.singleShot(0, lambda: apply_button_shadows(app))
        return False


def _apply_button_shadow(button):
    if button.property("buttonShadowApplied"):
        return

    shadow = QGraphicsDropShadowEffect(button)
    shadow.setBlurRadius(14)
    shadow.setOffset(0, 3)
    shadow.setColor(QColor(23, 32, 38, 60))
    button.setGraphicsEffect(shadow)
    button.setProperty("buttonShadowApplied", True)


def apply_button_shadows(app: QApplication):
    for button in app.allWidgets():
        if isinstance(button, (QPushButton, QToolButton)):
            _apply_button_shadow(button)


def install_button_shadow_filter(app: QApplication):
    if app.property("buttonShadowFilterInstalled"):
        return

    shadow_filter = _ButtonShadowFilter(app)
    app.installEventFilter(shadow_filter)
    app._button_shadow_filter = shadow_filter
    app.setProperty("buttonShadowFilterInstalled", True)


def apply_styles(app: QApplication, font_size: int = 14):
    font_size = max(10, min(28, int(font_size)))
    stylesheet = """
        QMainWindow, QWidget {
            background: #f1eee7;
            color: #172026;
            font-family: "Microsoft JhengHei UI", "Segoe UI", Arial;
            font-size: __FONT_SIZE__px;
        }
        QToolBar {
            background: #ffffff;
            border-bottom: 1px solid #d9e0e3;
            spacing: 8px;
            padding: 8px;
        }
        QToolBar QWidget {
            background: #ffffff;
        }
        QToolButton {
            padding: 8px 12px;
            border-radius: 6px;
        }
        QToolButton:hover {
            background: #e8eef1;
        }
        QToolButton#setupNavButton {
            background: #eef2f4;
            color: #172026;
            border: 1px solid #d6dde1;
            border-radius: 6px;
        }
        QToolButton#setupNavButton:hover {
            background: #e2e8ec;
            border: 1px solid #c8d1d6;
            color: #172026;
        }
        QToolButton:checked {
            background: #176b5d;
            color: #ffffff;
            border: 1px solid #176b5d;
            border-radius: 6px;
            font-weight: 800;
        }
        QToolButton:checked:hover {
            background: #135b50;
            border: 1px solid #135b50;
            color: #ffffff;
        }
        QToolButton#setupNavButton:checked {
            background: #ffffff;
            color: #172026;
            border: 2px solid #dc2626;
            border-radius: 6px;
            font-weight: 800;
        }
        QToolButton#setupNavButton:checked:hover {
            background: #fff7f7;
            border: 2px solid #b91c1c;
            color: #172026;
        }
        #roleBadge {
            background: #172026;
            color: #ffffff;
            border-radius: 6px;
            padding: 8px 12px;
            font-weight: 800;
        }
        QTabWidget::pane {
            border: 1px solid #d7dee2;
            background: #ffffff;
            border-radius: 8px;
            top: -1px;
        }
        QTabBar::tab {
            background: #eef3f5;
            border: 1px solid #c9d4d9;
            border-bottom: 0;
            padding: 9px 16px;
            margin-right: 4px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            font-weight: 700;
        }
        QTabBar::tab:selected {
            background: #ffffff;
            color: #176b5d;
        }
        #userManagementTabs QTabBar::tab {
            background: #e8eef1;
            color: #41515c;
            border: 1px solid #c9d4d9;
            border-bottom: 0;
            padding: 10px 18px;
        }
        #userManagementTabs QTabBar::tab:selected {
            background: #176b5d;
            color: #ffffff;
            border: 1px solid #176b5d;
            font-weight: 800;
        }
        #userManagementTabs QTabBar::tab:hover:!selected {
            background: #dce7eb;
            color: #172026;
        }
        QGroupBox, #cameraCard {
            background: #ffffff;
            border: 1px solid #d7dee2;
            border-radius: 8px;
            margin-top: 12px;
            padding: 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #41515c;
            font-weight: 700;
        }
        #loginPanel QWidget,
        #loginPanel QLabel,
        #loginPanel QCheckBox,
        #loginPanel QGroupBox::title {
            background: #ffffff;
        }
        #cameraSettingsGroup QWidget,
        #cameraSettingsGroup QLabel,
        #cameraSettingsGroup QCheckBox,
        #cameraSettingsGroup QGroupBox::title,
        #cameraSettingsCard QWidget,
        #cameraSettingsCard QLabel,
        #cameraSettingsCard QCheckBox,
        #cameraSettingsCard QGroupBox::title {
            background: #ffffff;
        }
        #cameraPreviewGroup QWidget,
        #cameraPreviewGroup QLabel,
        #cameraPreviewGroup #cameraCard,
        #cameraPreviewGroup #cameraTitle,
        #cameraPreviewGroup #mutedText,
        #cameraPreviewGroup QGroupBox::title {
            background: #ffffff;
        }
        QLineEdit, QSpinBox {
            background: #ffffff;
            border: 1px solid #bcc8ce;
            border-radius: 6px;
            padding: 8px;
            min-height: 24px;
        }
        QCheckBox {
            color: #25323a;
            font-weight: 700;
            spacing: 8px;
            padding: 4px 2px;
        }
        QCheckBox::indicator {
            width: 24px;
            height: 24px;
            border-radius: 5px;
            border: 2px solid #7c8d96;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border: 2px solid #176b5d;
            background: #eef7f4;
        }
        QCheckBox::indicator:checked {
            border: 2px solid #176b5d;
            background: #176b5d;
            image: none;
        }
        QCheckBox::indicator:checked:hover {
            background: #135b50;
        }
        QCheckBox::indicator:disabled {
            border: 2px solid #c4cdd2;
            background: #eef2f4;
        }
        QPushButton {
            background: #eef3f5;
            border: 1px solid #c9d4d9;
            border-radius: 6px;
            padding: 9px 14px;
            min-width: 96px;
        }
        QPushButton:hover {
            background: #e1eaee;
        }
        #loginPanel QPushButton:hover {
            background: #d6e0e4;
            border: 1px solid #aab9c0;
        }
        #logoutButton {
            background: #ffe2df;
            color: #9f1f16;
            border: 1px solid #f4aaa4;
            font-weight: 700;
        }
        #logoutButton:hover {
            background: #ffd2cc;
            border: 1px solid #e98f86;
        }
        #primaryButton {
            background: #176b5d;
            color: #ffffff;
            border: 1px solid #176b5d;
            font-weight: 700;
        }
        #primaryButton:hover {
            background: #135b50;
        }
        #loginPanel QPushButton#primaryButton {
            background: #176b5d;
            color: #ffffff;
            border: 1px solid #176b5d;
            font-weight: 700;
        }
        #loginPanel QPushButton#primaryButton:hover {
            background: #135b50;
        }
        #activeDetectionButton {
            background: #f59e0b;
            color: #172026;
            border: 1px solid #d97706;
            font-weight: 800;
        }
        #activeDetectionButton:hover {
            background: #f59e0b;
        }
        #continuousButton {
            background: #176b5d;
            color: #ffffff;
            border: 1px solid #176b5d;
            font-weight: 700;
        }
        #continuousButton:hover {
            background: #135b50;
        }
        #continuousButton:checked {
            background: #176b5d;
            color: #ffffff;
            border: 1px solid #176b5d;
            font-weight: 700;
        }
        #continuousButton:checked:hover {
            background: #135b50;
        }
        #passwordToggleButton {
            background: #ffffff;
            border: 1px solid #bcc8ce;
            border-radius: 6px;
            color: #41515c;
            font-size: 14px;
            font-weight: 800;
            min-width: 0;
            padding: 0;
        }
        #passwordToggleButton:hover {
            background: #eef7f4;
            border: 1px solid #176b5d;
            color: #176b5d;
        }
        #cameraImage, #cameraError {
            background: #ffffff;
            border-radius: 6px;
            color: #687981;
            min-height: 260px;
        }
        #cameraError {
            background: #2a1718;
            color: #ffd8d4;
            border: 2px solid #d92d20;
            font-weight: 800;
            padding: 16px;
        }
        #cameraTitle {
            color: #25323a;
            font-weight: 700;
        }
        #mutedText {
            color: #687981;
        }
        #ngReasonBox {
            background: #fff8e7;
            color: #6f4e00;
            border: 1px solid #f0d68a;
            border-radius: 6px;
            padding: 10px 12px;
            min-height: 52px;
        }
        #reasonPassBox {
            background: #dff4e9;
            color: #0d6b3f;
            border: 1px solid #8fd7b3;
            border-radius: 6px;
        }
        #reasonNgBox {
            background: #ffe2df;
            color: #9f1f16;
            border: 1px solid #f4aaa4;
            border-radius: 6px;
        }
        #reasonTitle {
            font-weight: 800;
        }
        #pageTitle {
            color: #172026;
            font-size: 20px;
            font-weight: 800;
        }
        #resultWaiting, #resultPass, #resultNg {
            border-radius: 8px;
            padding: 28px 16px;
            font-size: 44px;
            font-weight: 800;
            margin: 16px 0;
        }
        #resultWaiting {
            background: #e6ecef;
            color: #56656d;
        }
        #resultPass {
            background: #dff4e9;
            color: #0d6b3f;
        }
        #resultNg {
            background: #ffe2df;
            color: #b42318;
        }
        QTableWidget {
            background: #ffffff;
            alternate-background-color: #f0f4f6;
            border: 1px solid #d7dee2;
            gridline-color: #d7dee2;
        }
        QHeaderView::section {
            background: #e6ecef;
            padding: 8px;
            border: 0;
            border-right: 1px solid #d7dee2;
            font-weight: 700;
        }
        """
    app.setStyleSheet(stylesheet.replace("__FONT_SIZE__", str(font_size)))
    install_button_shadow_filter(app)
    QTimer.singleShot(0, lambda: apply_button_shadows(app))
