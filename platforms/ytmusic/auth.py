from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget
from db.repository import AppRepository

_LOGIN_URL = "https://music.youtube.com"
_TRIGGER_COOKIE = "SAPISID"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class YTMusicAuth:
    """Manages YouTube Music login via WebView cookie capture."""

    def __init__(self, repo: AppRepository) -> None:
        self._repo = repo

    async def load_auth(self) -> dict[str, str] | None:
        return await self._repo.load_credential("ytmusic")

    async def login(
        self, parent: QWidget | None = None
    ) -> dict[str, str] | None:
        from ui.components.login_dialog import LoginDialog  # lazy: needs WebEngine
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, str] | None] = loop.create_future()

        dialog = LoginDialog(
            url=_LOGIN_URL,
            target_cookies=[_TRIGGER_COOKIE],
            title="YouTube Music — 登录",
            capture_all_cookies=True,
            parent=parent,
        )

        def _on_captured(cookies: dict) -> None:
            if not future.done():
                future.set_result(cookies)

        def _on_rejected() -> None:
            if not future.done():
                future.set_result(None)

        dialog.cookies_captured.connect(_on_captured)
        dialog.rejected.connect(_on_rejected)
        dialog.show()

        cookies = await future
        if not cookies or _TRIGGER_COOKIE not in cookies:
            return None

        headers = self._build_headers(cookies)
        await self._repo.save_credential("ytmusic", headers)
        return headers

    async def ensure_authenticated(
        self, parent: QWidget | None = None
    ) -> dict[str, str] | None:
        existing = await self.load_auth()
        if existing and existing.get("Cookie"):
            return existing
        return await self.login(parent)

    @staticmethod
    def _build_headers(cookies: dict[str, str]) -> dict[str, str]:
        """Build a ytmusicapi-compatible headers dict from captured cookies."""
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {
            "User-Agent": _USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "X-Goog-AuthUser": "0",
            "x-origin": "https://music.youtube.com",
            "Cookie": cookie_str,
        }
