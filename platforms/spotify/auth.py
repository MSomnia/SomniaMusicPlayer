from __future__ import annotations
import asyncio
import hashlib
import hmac
import re
import json
import logging
import struct
import time

logger = logging.getLogger(__name__)

_ACCOUNTS_URL = "https://open.spotify.com/"
_TOKEN_URL = "https://open.spotify.com/api/token"
_SERVER_TIME_URL = "https://open.spotify.com/api/server-time"
_WEB_PLAYER_URL = "https://open.spotify.com/"
_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TOTP_SECRET_RAW = [12, 56, 76, 33, 88, 44, 88, 33, 78, 78, 11, 66, 22, 22, 55, 69, 54]


class SpotifyAuth:
    def __init__(self, repo) -> None:
        self._repo = repo
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0
        self._totp_secret: bytes | None = None
        self._totp_version: int = 5

    async def load_sp_dc(self) -> str | None:
        cred = await self._repo.load_credential("spotify")
        if cred:
            return cred.get("sp_dc")
        return None

    async def login(self, parent=None) -> str | None:
        from ui.components.login_dialog import LoginDialog

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()

        dialog = LoginDialog(
            url=_ACCOUNTS_URL,
            target_cookies=["sp_dc", "sp_key"],
            title="Spotify — 登录",
            show_done_button=True,
            manual_cookie_names=["sp_dc", "sp_key"],
            user_agent=_WEB_UA,
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
        if not cookies or "sp_dc" not in cookies:
            logger.debug("Spotify login cancelled — sp_dc not captured")
            return None

        sp_dc = cookies["sp_dc"]
        credential = {"sp_dc": sp_dc}
        if cookies.get("sp_key"):
            credential["sp_key"] = cookies["sp_key"]
        await self._repo.save_credential("spotify", credential)
        logger.info("Spotify cookie credentials saved")
        return sp_dc

    async def get_access_token(self) -> str:
        now = time.time()
        if self._cached_token and now < self._token_expires_at - 60:
            return self._cached_token

        credential = await self._repo.load_credential("spotify")
        sp_dc = credential.get("sp_dc") if credential else None
        if not sp_dc:
            raise RuntimeError("Spotify not authenticated — sp_dc not found")
        sp_key = credential.get("sp_key") if credential else None

        import httpx
        async with httpx.AsyncClient() as http:
            server_time = await self._get_server_time(http)
            secret, version = await self._get_totp_config(http)
            totp = self._generate_totp(int(time.time()), secret=secret)
            totp_server = (
                self._generate_totp(server_time, secret=secret)
                if server_time is not None else "unavailable"
            )
            params = {
                "reason": "transport",
                "productType": "web-player",
                "totp": totp,
                "totpServer": totp_server,
                "totpVer": str(version),
            }
            try:
                resp = await http.get(
                    _TOKEN_URL,
                    params=params,
                    headers={
                        "User-Agent": _WEB_UA,
                        "Accept": "application/json",
                        "Referer": "https://open.spotify.com/",
                    },
                    cookies={
                        key: value
                        for key, value in {"sp_dc": sp_dc, "sp_key": sp_key}.items()
                        if value
                    },
                    follow_redirects=False,
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 403:
                    raise
                logger.warning(
                    "Spotify token HTTP request was blocked; retrying in WebEngine context"
                )
                data = await self._get_access_token_via_webengine(params)

        token = data.get("accessToken")
        if not token:
            raise RuntimeError("Spotify access token response did not contain accessToken")
        self._cached_token = token
        expires_ms = data.get("accessTokenExpirationTimestampMs", 0)
        self._token_expires_at = expires_ms / 1000 if expires_ms else now + 3600
        logger.info("Spotify access token refreshed (expires in %.0fs)", self._token_expires_at - now)
        return self._cached_token

    async def _get_access_token_via_webengine(self, params: dict) -> dict:
        from urllib.parse import urlencode
        from PyQt6.QtCore import QTimer, QUrl
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        view = QWebEngineView()
        view.resize(1, 1)
        view.page().profile().setHttpUserAgent(_WEB_UA)

        token_url = f"{_TOKEN_URL}?{urlencode(params)}"
        timeout = QTimer()
        timeout.setSingleShot(True)

        def _finish_text(text: str) -> None:
            timeout.stop()
            view.close()
            view.deleteLater()
            if future.done():
                return
            try:
                data = json.loads(text or "{}")
                if "accessToken" not in data:
                    raise RuntimeError(f"WebEngine token response missing accessToken: {text[:200]}")
                future.set_result(data)
            except Exception as exc:
                future.set_exception(exc)

        def _on_loaded(ok: bool) -> None:
            if not ok:
                _finish_text("")
                return
            view.page().toPlainText(_finish_text)

        def _on_timeout() -> None:
            _finish_text("")

        view.loadFinished.connect(_on_loaded)
        timeout.timeout.connect(_on_timeout)
        timeout.start(15_000)
        view.load(QUrl(token_url))
        # Keep Qt objects alive until the future completes.
        future._spotify_token_view = view  # type: ignore[attr-defined]
        future._spotify_token_timer = timeout  # type: ignore[attr-defined]
        return await future

    async def ensure_authenticated(self, parent=None) -> str | None:
        sp_dc = await self.load_sp_dc()
        if sp_dc:
            return sp_dc
        return await self.login(parent)

    async def _get_server_time(self, http) -> int | None:
        try:
            resp = await http.get(
                _SERVER_TIME_URL,
                headers={"User-Agent": _WEB_UA, "Accept": "application/json"},
                follow_redirects=False,
                timeout=10.0,
            )
            resp.raise_for_status()
            server_time = resp.json().get("serverTime")
            if server_time is not None:
                return int(server_time)
            logger.warning("Spotify server-time response missing serverTime; using client TOTP only")
        except Exception as exc:
            logger.warning("Spotify server-time unavailable (%s); using client TOTP only", exc)
        return None

    @classmethod
    def _generate_totp(cls, timestamp: int, secret: bytes | None = None) -> str:
        secret = secret or cls._totp_secret()
        counter = int(timestamp // 30)
        digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        return f"{code % 1_000_000:06d}"

    async def _get_totp_config(self, http) -> tuple[bytes, int]:
        if self._totp_secret is not None:
            return self._totp_secret, self._totp_version

        try:
            resp = await http.get(
                _WEB_PLAYER_URL,
                headers={"User-Agent": _WEB_UA, "Accept": "text/html"},
                timeout=10.0,
            )
            resp.raise_for_status()
            scripts = re.findall(r'https://[^"\']+/web-player\.[^"\']+\.js', resp.text)
            for script_url in scripts:
                js_resp = await http.get(
                    script_url,
                    headers={"User-Agent": _WEB_UA, "Accept": "*/*"},
                    timeout=15.0,
                )
                js_resp.raise_for_status()
                config = self._extract_totp_config(js_resp.text)
                if config is not None:
                    self._totp_secret, self._totp_version = config
                    logger.info("Spotify TOTP config loaded from Web Player bundle v%s", self._totp_version)
                    return config
        except Exception as exc:
            logger.warning("Spotify TOTP config fetch failed; using bundled fallback: %s", exc)

        self._totp_secret = self._totp_secret_from_bytes(_TOTP_SECRET_RAW)
        self._totp_version = 5
        return self._totp_secret, self._totp_version

    @classmethod
    def _extract_totp_config(cls, source: str) -> tuple[bytes, int] | None:
        marker = source.find("totpServer")
        if marker == -1:
            marker = source.find("totpVer")
        body = source[max(0, marker - 4000): marker + 500] if marker != -1 else source
        entries = re.findall(
            r"\{\s*secret\s*:\s*(?P<secret>'(?:\\.|[^'])*'|\"(?:\\.|[^\"])*\")\s*,\s*version\s*:\s*(?P<version>\d+)\s*\}",
            body,
        )
        if not entries:
            return None
        secret_literal, version_raw = entries[0]
        secret = json.loads(secret_literal) if secret_literal.startswith('"') else _parse_js_single_quoted(secret_literal)
        return cls._totp_secret_from_string(secret), int(version_raw)

    @staticmethod
    def _totp_secret() -> bytes:
        return SpotifyAuth._totp_secret_from_bytes(_TOTP_SECRET_RAW)

    @staticmethod
    def _totp_secret_from_bytes(values: list[int]) -> bytes:
        xored = [value ^ ((idx % 33) + 9) for idx, value in enumerate(values)]
        return "".join(str(num) for num in xored).encode("utf-8")

    @staticmethod
    def _totp_secret_from_string(value: str) -> bytes:
        xored = [ord(char) ^ ((idx % 33) + 9) for idx, char in enumerate(value)]
        return "".join(str(num) for num in xored).encode("utf-8")


def _parse_js_single_quoted(value: str) -> str:
    # The Spotify bundle uses normal JS string escapes; JSON can parse it once
    # we wrap the content as a double-quoted JSON string.
    inner = value[1:-1]
    inner = inner.replace("\\'", "'").replace('"', '\\"')
    return json.loads(f'"{inner}"')
