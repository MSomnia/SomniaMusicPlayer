from __future__ import annotations
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore
from PyQt6.QtNetwork import QNetworkCookie


class LoginDialog(QDialog):
    """Modal WebView dialog that captures specific cookies after user login."""

    cookies_captured = pyqtSignal(dict)   # {name: value, ...}

    def __init__(
        self,
        url: str,
        target_cookies: list[str],
        title: str = "登录",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)

        self._target = set(target_cookies)
        self._captured: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = QWebEngineView()
        layout.addWidget(self._view, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 4, 8, 4)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        # Wire cookie store before loading URL
        profile = self._view.page().profile()
        store: QWebEngineCookieStore = profile.cookieStore()
        store.cookieAdded.connect(self._on_cookie_added)

        self._view.load(QUrl(url))

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        name = bytes(cookie.name()).decode(errors="replace")
        value = bytes(cookie.value()).decode(errors="replace")
        if name in self._target:
            self._captured[name] = value
            if self._target.issubset(self._captured.keys()):
                self.cookies_captured.emit(dict(self._captured))
                self.accept()
