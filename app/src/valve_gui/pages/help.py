from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

# 之後改版只要動這三個常數即可
APP_NAME = "螺絲裝配檢測系統"
APP_VERSION = "1.0.0"
APP_RELEASE_DATE = "2026-06-24"


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
            "<div style='line-height:1.8'>"
            f"<h2 style='margin-bottom:2px'>{APP_NAME}</h2>"
            f"<p style='{muted}; margin-top:0'>版本 {APP_VERSION}</p>"

            "<h3>開發單位</h3>"
            "<p>國立勤益科技大學 智慧自動化工程系</p>"

            "<h3>開發團隊</h3>"
            "<p><b>指導教授：</b>賴嘉宏 老師</p>"
            "<p><b>學生：</b>林冠銘、戴鼎恩、黃思豪</p>"

            "<h3>致謝</h3>"
            "<p>感謝 國立勤益科技大學 智慧自動化工程系 提供研究環境與資源，"
            "並感謝 賴嘉宏 老師於本專案開發期間的悉心指導。</p>"

            "<h3>版本資訊</h3>"
            f"<p>軟體名稱：{APP_NAME}<br>"
            f"版本號：{APP_VERSION}<br>"
            f"發行日期：{APP_RELEASE_DATE}</p>"

            f"<p style='{muted}'>© 2026 國立勤益科技大學 智慧自動化工程系。"
            "保留一切權利。</p>"
            "</div>"
        )

    # ---- 之後灌內容用的介面 ----
    def set_manual_html(self, html: str):
        self.manual_view.setHtml(html)

    def set_about_html(self, html: str):
        self.about_view.setHtml(html)

    def refresh(self):
        pass
