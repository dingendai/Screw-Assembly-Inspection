from PyQt6.QtWidgets import QApplication


def apply_styles(app: QApplication):
    app.setStyleSheet(
        """
        QMainWindow, QWidget {
            background: #f5f7f8;
            color: #172026;
            font-family: "Microsoft JhengHei UI", "Segoe UI", Arial;
            font-size: 14px;
        }
        QToolBar {
            background: #ffffff;
            border-bottom: 1px solid #d9e0e3;
            spacing: 8px;
            padding: 8px;
        }
        QToolButton {
            padding: 8px 12px;
            border-radius: 6px;
        }
        QToolButton:hover {
            background: #e8eef1;
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
            background: #11171c;
            border-radius: 6px;
            color: #9fb0b9;
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
    )
