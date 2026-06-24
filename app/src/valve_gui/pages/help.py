from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class HelpPage(QWidget):
    """說明頁：兩個分頁 —— 使用者操作手冊 / 關於。

    內容由使用者後續提供，這裡先建立空白結構。
    - set_manual_html() / set_about_html() 之後可用來灌入內容。
    """

    def __init__(self):
        super().__init__()

        self.tabs = QTabWidget()

        # ---- 分頁一：使用者操作手冊（內容待匯入）----
        self.manual_view = QTextBrowser()
        self.manual_view.setOpenExternalLinks(True)
        self.manual_view.setHtml(
            "<p style='color:#888'>（使用者操作手冊內容待匯入）</p>"
        )
        self.tabs.addTab(self.manual_view, "使用者操作手冊")

        # ---- 分頁二：關於（致謝 / 開發者 / 版本資訊，內容待填）----
        self.about_view = QTextBrowser()
        self.about_view.setOpenExternalLinks(True)
        self.about_view.setHtml(self._default_about_html())
        self.tabs.addTab(self.about_view, "關於")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("說明")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(self.tabs)

    def _default_about_html(self) -> str:
        muted = "color:#888"
        return (
            "<h3>致謝</h3>"
            f"<p style='{muted}'>（致謝對象待填）</p>"
            "<h3>開發者</h3>"
            f"<p style='{muted}'>（開發者資訊待填）</p>"
            "<h3>版本資訊</h3>"
            f"<p style='{muted}'>（詳細版本內容待填）</p>"
        )

    # ---- 之後灌內容用的介面 ----
    def set_manual_html(self, html: str):
        self.manual_view.setHtml(html)

    def set_about_html(self, html: str):
        self.about_view.setHtml(html)

    def refresh(self):
        pass
