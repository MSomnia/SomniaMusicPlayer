from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget
from ui.components.login_dialog import LoginDialog
from db.repository import AppRepository

_NETEASE_LOGIN_URL = "https://music.163.com/#/login"
_TARGET_COOKIES = ["MUSIC_U", "__csrf"]


class NeteaseAuth:
    """Manages Netease login flow and credential persistence."""

    def __init__(self, repo: AppRepository) -> None:
        self._repo = repo

    async def load_cookies(self) -> dict[str, str] | None:
        cred = await self._repo.load_credential("netease")
        return cred

    async def login(self, parent: QWidget | None = None) -> dict[str, str] | None:
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, str] | None] = loop.create_future()

        dialog = LoginDialog(
            url=_NETEASE_LOGIN_URL,
            target_cookies=_TARGET_COOKIES,
            title="网易云音乐 — 登录",
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
        if cookies:
            await self._repo.save_credential("netease", cookies)
        return cookies

    async def ensure_authenticated(
        self, parent: QWidget | None = None
    ) -> dict[str, str] | None:
        existing = await self.load_cookies()
        if existing and existing.get("MUSIC_U"):
            return existing
        return await self.login(parent)
