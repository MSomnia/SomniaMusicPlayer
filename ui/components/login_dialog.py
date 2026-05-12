from __future__ import annotations
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QInputDialog,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineCookieStore
from PyQt6.QtNetwork import QNetworkCookie


class LoginDialog(QDialog):
    """Modal WebView dialog that captures cookies after user login.

    Behaviour:
    - capture_all_cookies=True  → stores every cookie; closes when target_cookies appear
    - capture_all_cookies=False → stores only target cookies; closes when all appear
    - show_done_button=True     → adds a manual "我已登录" button the user can click
                                  to emit whatever cookies have been accumulated
    - Calls store.loadAllCookies() so an already-logged-in persistent profile is
      detected immediately without waiting for new cookieAdded events.
    """

    cookies_captured = pyqtSignal(dict)   # {name: value, ...}

    def __init__(
        self,
        url: str,
        target_cookies: list[str],
        title: str = "登录",
        capture_all_cookies: bool = False,
        show_done_button: bool = False,
        manual_cookie_name: str | None = None,
        manual_cookie_names: list[str] | None = None,
        user_agent: str | None = None,
        parent: "QWidget | None" = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)

        self._target = set(target_cookies)
        self._captured: dict[str, str] = {}
        self._capture_all = capture_all_cookies
        manual_names = list(manual_cookie_names or [])
        if manual_cookie_name and manual_cookie_name not in manual_names:
            manual_names.append(manual_cookie_name)
        self._manual_cookie_names = manual_names
        self._done = False  # guard against double-fire

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._view = QWebEngineView()
        if user_agent:
            self._view.page().profile().setHttpUserAgent(user_agent)
        layout.addWidget(self._view, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(8, 6, 8, 6)

        if show_done_button:
            hint = QLabel("在网页中完成登录后点击「我已登录」")
            hint.setStyleSheet("color: #A0A0A0; font-size: 11px;")
            btn_row.addWidget(hint)

        btn_row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        if self._manual_cookie_names:
            label = "/".join(self._manual_cookie_names)
            manual_btn = QPushButton(f"手动输入 {label}")
            manual_btn.clicked.connect(self._on_manual_cookies)
            btn_row.addWidget(manual_btn)

        if show_done_button:
            done_btn = QPushButton("我已登录")
            done_btn.setDefault(True)
            done_btn.setStyleSheet(
                "background-color: #1DB954; color: #000; font-weight: bold;"
                " padding: 4px 16px; border-radius: 4px;"
            )
            done_btn.clicked.connect(self._on_done_clicked)
            btn_row.addWidget(done_btn)

        layout.addLayout(btn_row)

        profile = self._view.page().profile()
        store: QWebEngineCookieStore = profile.cookieStore()
        store.cookieAdded.connect(self._on_cookie_added)
        # Re-emit cookies already in the profile (handles already-logged-in sessions)
        store.loadAllCookies()

        self._view.load(QUrl(url))

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        if self._done:
            return
        name = bytes(cookie.name()).decode(errors="replace")
        value = bytes(cookie.value()).decode(errors="replace")
        if self._capture_all or name in self._target:
            self._captured[name] = value
        # Auto-close once all target cookies are present
        if self._target and self._target.issubset(self._captured.keys()):
            self._emit_and_close()

    def _on_done_clicked(self) -> None:
        """User manually signals that login is complete."""
        self._emit_and_close()

    def _on_manual_cookies(self) -> None:
        if not self._manual_cookie_names:
            return
        for name in self._manual_cookie_names:
            value, ok = QInputDialog.getText(
                self,
                "手动输入 Cookie",
                f"粘贴 {name} 的值：",
            )
            value = value.strip()
            if ok and value:
                self._captured[name] = value
        if self._target.issubset(self._captured.keys()):
            self._emit_and_close()

    def _emit_and_close(self) -> None:
        if self._done:
            return
        self._done = True
        self.cookies_captured.emit(dict(self._captured))
        self.accept()
