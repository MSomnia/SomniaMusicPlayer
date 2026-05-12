# Phase 4 — YouTube Music Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate YouTube Music as a second playable platform — WebView login (header capture), ytmusicapi search, yt-dlp stream extraction, and LRCLIB timed lyrics.

**Architecture:** `YTMusicAuth` captures all WebView cookies and builds a ytmusicapi-compatible headers dict saved encrypted in SQLite. `YTMusicClient` wraps the synchronous ytmusicapi and yt-dlp in thread executors. `AppController` becomes platform-agnostic by dispatching to whichever client matches `track.platform`. `SearchPage` gets a platform tab switcher.

**Tech Stack:** `ytmusicapi>=1.7.0`, `yt-dlp>=2024.5.0`, `httpx`, PyQt6 WebEngine, `aiosqlite`/`pycryptodome` (existing), `ThreadPoolExecutor`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `ui/components/login_dialog.py` | Add `capture_all_cookies` param |
| Create | `platforms/ytmusic/auth.py` | Cookie capture → ytmusicapi headers |
| Create | `platforms/ytmusic/lyrics.py` | LRCLIB.net client |
| Create | `platforms/ytmusic/client.py` | Search, stream URL (yt-dlp), lyrics |
| Modify | `core/app_controller.py` | Multi-platform dispatch |
| Modify | `ui/pages/search_page.py` | Platform tab switcher |
| Modify | `ui/app_window.py` | Connect ytmusic_auth_changed signal |
| Create | `tests/test_ytmusic_lyrics.py` | LRCLIB unit tests |
| Create | `tests/test_ytmusic_client.py` | YTMusicClient unit tests |

---

## Task 1 — Extend `LoginDialog` to capture all cookies

**Files:**
- Modify: `ui/components/login_dialog.py`

The current dialog only stores cookies whose names are in `target_cookies`. YouTube Music auth needs ALL cookies (to build the full Cookie header string) but should still trigger completion when `SAPISID` appears.

- [ ] **Step 1.1: Add `capture_all_cookies` parameter**

Replace the full file:

```python
from __future__ import annotations
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineCookieStore
from PyQt6.QtNetwork import QNetworkCookie


class LoginDialog(QDialog):
    """Modal WebView dialog that captures cookies after user login.

    When capture_all_cookies=True every cookie is stored; the dialog closes
    and emits cookies_captured once all target_cookies have been seen.
    When capture_all_cookies=False (default) only target cookies are stored.
    """

    cookies_captured = pyqtSignal(dict)   # {name: value, ...}

    def __init__(
        self,
        url: str,
        target_cookies: list[str],
        title: str = "登录",
        capture_all_cookies: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 700)

        self._target = set(target_cookies)
        self._captured: dict[str, str] = {}
        self._capture_all = capture_all_cookies

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

        profile = self._view.page().profile()
        store: QWebEngineCookieStore = profile.cookieStore()
        store.cookieAdded.connect(self._on_cookie_added)

        self._view.load(QUrl(url))

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        name = bytes(cookie.name()).decode(errors="replace")
        value = bytes(cookie.value()).decode(errors="replace")
        if self._capture_all or name in self._target:
            self._captured[name] = value
        if self._target.issubset(self._captured.keys()):
            self.cookies_captured.emit(dict(self._captured))
            self.accept()
```

- [ ] **Step 1.2: Run existing tests to confirm no regression**

```bash
python3 -m pytest tests/ --ignore=tests/test_ui_components.py --ignore=tests/test_search_page.py -q
```

Expected: all pass.

- [ ] **Step 1.3: Commit**

```bash
git add ui/components/login_dialog.py
git commit -m "feat: LoginDialog supports capture_all_cookies mode for YTMusic auth"
```

---

## Task 2 — `platforms/ytmusic/auth.py`

**Files:**
- Create: `platforms/ytmusic/auth.py`
- Test: covered by integration; no isolated unit test (dialog requires WebEngine)

`YTMusicAuth` handles:
- `load_auth()` → loads encrypted headers dict from SQLite
- `login(parent)` → shows `LoginDialog`, captures cookies, builds ytmusicapi headers, saves to DB
- `_build_headers(cookies)` → static; converts raw cookie dict to ytmusicapi headers dict

- [ ] **Step 2.1: Create the file**

```python
# platforms/ytmusic/auth.py
from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget
from db.repository import AppRepository

_LOGIN_URL = "https://music.youtube.com"
_TRIGGER_COOKIE = "SAPISID"          # presence signals successful Google login
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
```

- [ ] **Step 2.2: Commit**

```bash
git add platforms/ytmusic/auth.py
git commit -m "feat: YTMusicAuth — WebView cookie capture and ytmusicapi header builder"
```

---

## Task 3 — `platforms/ytmusic/lyrics.py` (LRCLIB client)

**Files:**
- Create: `platforms/ytmusic/lyrics.py`
- Test: `tests/test_ytmusic_lyrics.py`

LRCLIB is a free public API that returns LRC-format synced lyrics. No API key needed.

- [ ] **Step 3.1: Write the failing tests**

```python
# tests/test_ytmusic_lyrics.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from platforms.ytmusic.lyrics import LRCLibClient
from core.models import Track


def _track(title="Hello", artist="Adele"):
    return Track(
        id="dQw4w9WgXcQ", platform="ytmusic",
        title=title, artist=artist, artists=[artist],
        album="Album", album_cover_url="", duration_ms=210000,
    )


async def test_get_lyrics_returns_synced_lines():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"syncedLyrics": "[00:01.00]Hello\n[00:03.00]World\n", "plainLyrics": "Hello\nWorld"}
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert len(lines) == 2
    assert lines[0].text == "Hello"
    assert lines[0].start_ms == 1000
    assert lines[1].text == "World"
    assert lines[1].start_ms == 3000


async def test_get_lyrics_empty_response_returns_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert lines == []


async def test_get_lyrics_no_synced_falls_back_to_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"syncedLyrics": None, "plainLyrics": "Hello"}]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert lines == []


async def test_get_lyrics_http_error_returns_empty():
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=Exception("timeout"))):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert lines == []
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_ytmusic_lyrics.py -v
```

Expected: `ModuleNotFoundError: No module named 'platforms.ytmusic.lyrics'`

- [ ] **Step 3.3: Implement `LRCLibClient`**

```python
# platforms/ytmusic/lyrics.py
from __future__ import annotations
import logging
import httpx
from core.models import LyricLine, Track
from utils.lrc_parser import parse_lrc

logger = logging.getLogger(__name__)

_BASE = "https://lrclib.net/api"


class LRCLibClient:
    """Fetches synced LRC lyrics from the free LRCLIB.net public API."""

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        try:
            async with httpx.AsyncClient(timeout=6.0) as http:
                resp = await http.get(
                    f"{_BASE}/search",
                    params={
                        "track_name": track.title,
                        "artist_name": track.artist,
                    },
                )
                resp.raise_for_status()
                results = resp.json()
        except Exception as exc:
            logger.debug("LRCLIB request failed: %s", exc)
            return []

        for item in results:
            synced = item.get("syncedLyrics")
            if synced:
                return parse_lrc(synced)

        return []
```

- [ ] **Step 3.4: Run tests — expect pass**

```bash
python3 -m pytest tests/test_ytmusic_lyrics.py -v
```

Expected: 4 passed.

- [ ] **Step 3.5: Commit**

```bash
git add platforms/ytmusic/lyrics.py tests/test_ytmusic_lyrics.py
git commit -m "feat: LRCLibClient for YouTube Music synced lyrics"
```

---

## Task 4 — `platforms/ytmusic/client.py`

**Files:**
- Create: `platforms/ytmusic/client.py`
- Test: `tests/test_ytmusic_client.py`

`YTMusicClient` wraps the synchronous `ytmusicapi` and `yt-dlp` libraries in a `ThreadPoolExecutor`. All external calls are async from the caller's perspective.

- [ ] **Step 4.1: Write the failing tests**

```python
# tests/test_ytmusic_client.py
import json, pytest
from unittest.mock import MagicMock, patch, AsyncMock
from core.models import Track


def _make_client():
    from platforms.ytmusic.client import YTMusicClient
    headers = {"Cookie": "SAPISID=x", "X-Goog-AuthUser": "0"}
    with patch("ytmusicapi.YTMusic.__init__", return_value=None):
        client = YTMusicClient(headers)
        client._ytm = MagicMock()
        return client


def _yt_song(video_id="abc123"):
    return {
        "videoId": video_id,
        "title": "Test Song",
        "artists": [{"name": "Test Artist", "id": "A1"}],
        "album": {"name": "Test Album", "id": "AL1"},
        "duration_seconds": 210,
        "thumbnails": [
            {"url": "http://img/small.jpg", "width": 60, "height": 60},
            {"url": "http://img/large.jpg", "width": 226, "height": 226},
        ],
    }


async def test_search_returns_tracks():
    client = _make_client()
    client._ytm.search.return_value = [_yt_song("abc")]

    tracks = await client.search("test query", limit=5)

    client._ytm.search.assert_called_once_with("test query", filter="songs", limit=5)
    assert len(tracks) == 1
    t = tracks[0]
    assert t.id == "abc"
    assert t.platform == "ytmusic"
    assert t.title == "Test Song"
    assert t.artist == "Test Artist"
    assert t.album == "Test Album"
    assert t.duration_ms == 210_000
    assert t.album_cover_url == "http://img/large.jpg"


async def test_search_empty_result():
    client = _make_client()
    client._ytm.search.return_value = []

    tracks = await client.search("nothing")
    assert tracks == []


async def test_search_missing_fields_handled():
    client = _make_client()
    minimal = {"videoId": "z", "title": "X"}
    client._ytm.search.return_value = [minimal]

    tracks = await client.search("x")
    assert tracks[0].artist == ""
    assert tracks[0].album == ""
    assert tracks[0].duration_ms == 0


async def test_is_authenticated():
    client = _make_client()
    assert await client.is_authenticated() is True


async def test_get_library_playlists_returns_list():
    client = _make_client()
    client._ytm.get_library_playlists.return_value = [
        {"playlistId": "PL1", "title": "My Mix",
         "thumbnails": [{"url": "http://t.jpg"}], "count": 12}
    ]
    playlists = await client.get_library_playlists()
    assert len(playlists) == 1
    assert playlists[0].id == "PL1"
    assert playlists[0].name == "My Mix"
    assert playlists[0].platform == "ytmusic"
```

- [ ] **Step 4.2: Run tests to confirm they fail**

```bash
python3 -m pytest tests/test_ytmusic_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'platforms.ytmusic.client'`

- [ ] **Step 4.3: Implement `YTMusicClient`**

```python
# platforms/ytmusic/client.py
from __future__ import annotations
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from core.models import Track, Playlist, LyricLine
from platforms.base import AbstractPlatform

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytmusic")


class YTMusicClient(AbstractPlatform):
    """Async wrapper around synchronous ytmusicapi + yt-dlp."""

    platform_id = "ytmusic"

    def __init__(self, headers: dict[str, str]) -> None:
        from ytmusicapi import YTMusic  # type: ignore[import]
        self._ytm = YTMusic(auth=json.dumps(headers))

    # ── AbstractPlatform ──────────────────────────────────────────────────────

    async def is_authenticated(self) -> bool:
        return True

    async def search(self, query: str, limit: int = 30) -> list[Track]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            _executor, lambda: self._ytm.search(query, filter="songs", limit=limit)
        )
        return [self._to_track(r) for r in (results or [])]

    async def get_stream_url(self, track: Track) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._extract_stream_url, track.id)

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        from platforms.ytmusic.lyrics import LRCLibClient
        return await LRCLibClient().get_lyrics(track)

    async def get_library_playlists(self) -> list[Playlist]:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            _executor, self._ytm.get_library_playlists
        )
        return [self._to_playlist(p) for p in (raw or [])]

    # ── internal ──────────────────────────────────────────────────────────────

    def _extract_stream_url(self, video_id: str) -> str:
        import yt_dlp  # type: ignore[import]
        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "youtube_include_dash_manifest": False,
            "extractor_args": {"youtube": {"skip": ["dash", "hls"]}},
        }
        url = f"https://music.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        formats = info.get("formats", [])
        audio_only = [
            f for f in formats
            if f.get("acodec") != "none" and f.get("vcodec") in ("none", None)
        ]
        if audio_only:
            best = max(audio_only, key=lambda f: f.get("abr") or 0)
            return best["url"]
        return info["url"]

    @staticmethod
    def _to_track(r: dict) -> Track:
        artists = [a["name"] for a in r.get("artists") or []]
        album_obj = r.get("album") or {}
        thumbs = r.get("thumbnails") or []
        cover = thumbs[-1]["url"] if thumbs else ""
        return Track(
            id=r.get("videoId", ""),
            platform="ytmusic",
            title=r.get("title", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album_obj.get("name", "") if isinstance(album_obj, dict) else "",
            album_cover_url=cover,
            duration_ms=(r.get("duration_seconds") or 0) * 1000,
        )

    @staticmethod
    def _to_playlist(p: dict) -> Playlist:
        thumbs = p.get("thumbnails") or []
        cover = thumbs[-1]["url"] if thumbs else ""
        return Playlist(
            id=p.get("playlistId", ""),
            platform="ytmusic",
            name=p.get("title", ""),
            cover_url=cover,
            track_count=p.get("count") or 0,
        )
```

- [ ] **Step 4.4: Run tests — expect pass**

```bash
python3 -m pytest tests/test_ytmusic_client.py -v
```

Expected: 6 passed.

- [ ] **Step 4.5: Commit**

```bash
git add platforms/ytmusic/client.py tests/test_ytmusic_client.py
git commit -m "feat: YTMusicClient — search, yt-dlp stream, LRCLIB lyrics"
```

---

## Task 5 — Update `AppController` for multi-platform support

**Files:**
- Modify: `core/app_controller.py`

Add:
- `YTMusicAuth` instance and `_ytm_client: YTMusicClient | None`
- `ytmusic_auth_changed = pyqtSignal(bool)`
- `is_ytmusic_authenticated` property
- `ensure_ytmusic_auth(parent)` coroutine
- `_get_platform_client(platform)` helper
- Modify `search(query, platform)` to dispatch by platform
- Modify `play_track` to dispatch by `track.platform`
- Modify `_fetch_lyrics` to dispatch by `track.platform`
- Load ytmusic auth in `init()`

- [ ] **Step 5.1: Replace `core/app_controller.py`**

```python
# core/app_controller.py
from __future__ import annotations
import asyncio
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
import httpx
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState
from core.player import UnifiedPlayer
from core.queue import PlayQueue
from core.vlc_backend import VLCBackend
from db.repository import AppRepository
from platforms.base import AbstractPlatform
from platforms.netease.auth import NeteaseAuth
from platforms.netease.proxy_client import NeteaseProxyClient, DEFAULT_PROXY_URL
from platforms.ytmusic.auth import YTMusicAuth

logger = logging.getLogger(__name__)

_PROXY_READY_TIMEOUT = 15
_color_executor = ThreadPoolExecutor(max_workers=1)


class AppController(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)
    ytmusic_auth_changed = pyqtSignal(bool)
    lyrics_ready = pyqtSignal(list)
    cover_color_ready = pyqtSignal(int, int, int)
    cover_art_bytes = pyqtSignal(bytes)

    def __init__(self) -> None:
        super().__init__()
        self._repo = AppRepository()
        self._netease_auth = NeteaseAuth(self._repo)
        self._ytm_auth = YTMusicAuth(self._repo)
        self._netease_client: NeteaseProxyClient | None = None
        self._ytm_client = None   # YTMusicClient | None
        self._player = UnifiedPlayer()
        self._vlc = VLCBackend()
        self._queue = PlayQueue()
        self._proxy_process: asyncio.subprocess.Process | None = None
        self._wire_internal()

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def is_netease_authenticated(self) -> bool:
        return self._netease_client is not None

    @property
    def is_ytmusic_authenticated(self) -> bool:
        return self._ytm_client is not None

    # ── internal wiring ───────────────────────────────────────────────────────

    def _wire_internal(self) -> None:
        self._vlc.position_changed.connect(self._player.update_position)
        self._vlc.end_reached.connect(
            lambda: asyncio.ensure_future(self.play_next())
        )
        self._vlc.error_occurred.connect(self._player.on_load_error)
        self._player.state_changed.connect(self.state_changed)
        self._player.position_changed.connect(self.position_changed)

    def _get_platform_client(self, platform: str) -> AbstractPlatform | None:
        if platform == "netease":
            return self._netease_client
        if platform == "ytmusic":
            return self._ytm_client
        return None

    # ── initialisation ────────────────────────────────────────────────────────

    async def init(self) -> None:
        await self._repo.init()
        await self._ensure_proxy()
        # Restore Netease session
        cookies = await self._netease_auth.load_cookies()
        if cookies:
            self._netease_client = NeteaseProxyClient(cookies)
            self.netease_auth_changed.emit(True)
        # Restore YouTube Music session
        headers = await self._ytm_auth.load_auth()
        if headers:
            from platforms.ytmusic.client import YTMusicClient
            self._ytm_client = YTMusicClient(headers)
            self.ytmusic_auth_changed.emit(True)

    # ── Netease proxy management (unchanged) ──────────────────────────────────

    async def _ensure_proxy(self) -> None:
        if await self._proxy_is_ready():
            logger.info("Netease proxy already running at %s", DEFAULT_PROXY_URL)
            return
        npx = shutil.which("npx")
        if not npx:
            logger.warning("npx not found — cannot auto-start Netease proxy")
            return
        logger.info("Starting Netease proxy …")
        self._proxy_process = await asyncio.create_subprocess_exec(
            npx, "NeteaseCloudMusicApi",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        for _ in range(_PROXY_READY_TIMEOUT * 2):
            await asyncio.sleep(0.5)
            if await self._proxy_is_ready():
                logger.info("Netease proxy ready")
                return
        logger.error("Netease proxy did not become ready within %ds", _PROXY_READY_TIMEOUT)

    async def _proxy_is_ready(self) -> bool:
        try:
            async with httpx.AsyncClient() as http:
                r = await http.get(DEFAULT_PROXY_URL, timeout=1.0)
                return r.status_code < 500
        except Exception:
            return False

    # ── auth ──────────────────────────────────────────────────────────────────

    async def ensure_netease_auth(self, parent=None) -> bool:
        if self._netease_client is not None:
            return True
        cookies = await self._netease_auth.login(parent)
        if cookies:
            self._netease_client = NeteaseProxyClient(cookies)
            self.netease_auth_changed.emit(True)
            return True
        return False

    async def ensure_ytmusic_auth(self, parent=None) -> bool:
        if self._ytm_client is not None:
            return True
        headers = await self._ytm_auth.login(parent)
        if headers:
            from platforms.ytmusic.client import YTMusicClient
            self._ytm_client = YTMusicClient(headers)
            self.ytmusic_auth_changed.emit(True)
            return True
        return False

    # ── search & playback ────────────────────────────────────────────────────

    async def search(self, query: str, platform: str = "netease") -> list[Track]:
        client = self._get_platform_client(platform)
        if not client:
            return []
        tracks = await client.search(query)
        self.search_results_ready.emit(tracks)
        return tracks

    async def play_track(self, track: Track) -> None:
        client = self._get_platform_client(track.platform)
        if client is None:
            logger.warning("No client for platform %r", track.platform)
            return
        self._queue.set_tracks([track], 0)
        self._player.load(track)
        try:
            url = await client.get_stream_url(track)
            self._vlc.play(url)
            self._player.on_load_success()
        except Exception as exc:
            self._player.on_load_error(str(exc))
            return
        asyncio.ensure_future(self._fetch_lyrics(track))
        asyncio.ensure_future(self._fetch_cover_color(track))

    async def _fetch_lyrics(self, track: Track) -> None:
        client = self._get_platform_client(track.platform)
        if not client:
            self.lyrics_ready.emit([])
            return
        try:
            lines = await client.get_lyrics(track)
            self.lyrics_ready.emit(lines)
        except Exception as exc:
            logger.warning("Lyrics fetch failed: %s", exc)
            self.lyrics_ready.emit([])

    async def _fetch_cover_color(self, track: Track) -> None:
        if not track.album_cover_url:
            return
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(track.album_cover_url, timeout=5.0)
                image_data = resp.content
            self.cover_art_bytes.emit(image_data)
            loop = asyncio.get_event_loop()
            color = await loop.run_in_executor(
                _color_executor, self._extract_dominant_color, image_data
            )
            if color:
                self.cover_color_ready.emit(*color)
        except Exception as exc:
            logger.debug("Cover color extraction failed: %s", exc)

    @staticmethod
    def _extract_dominant_color(image_data: bytes) -> tuple[int, int, int] | None:
        try:
            from io import BytesIO
            from colorthief import ColorThief  # type: ignore[import]
            return ColorThief(BytesIO(image_data)).get_color(quality=1)
        except Exception:
            return None

    # ── transport controls ────────────────────────────────────────────────────

    def toggle_play_pause(self) -> None:
        status = self._player.state.status
        if status == "playing":
            self._vlc.pause()
            self._player.pause()
        elif status == "paused":
            self._vlc.pause()
            self._player.resume()

    def seek(self, ms: int) -> None:
        self._vlc.seek(ms)
        self._player.seek(ms)

    async def play_next(self) -> None:
        next_track = self._queue.next(self._player.state.repeat_mode)
        if next_track is None:
            self._vlc.stop()
            self._player.stop()
        else:
            await self.play_track(next_track)

    async def play_prev(self) -> None:
        prev = self._queue.previous()
        if prev is not None:
            await self.play_track(prev)

    def set_volume(self, v: int) -> None:
        self._vlc.set_volume(v)
        asyncio.ensure_future(self._repo.set_setting("volume", str(v)))

    async def get_initial_volume(self) -> int:
        val = await self._repo.get_setting("volume")
        return int(val) if val else 70

    async def close(self) -> None:
        await self._repo.close()
        if self._proxy_process is not None:
            self._proxy_process.terminate()
            try:
                await asyncio.wait_for(self._proxy_process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proxy_process.kill()
            self._proxy_process = None
```

- [ ] **Step 5.2: Run full test suite**

```bash
python3 -m pytest tests/ --ignore=tests/test_ui_components.py --ignore=tests/test_search_page.py -q
```

Expected: all pass (the renamed `_auth` → `_netease_auth` only affects app_controller internals; tests mock at the platform level).

- [ ] **Step 5.3: Commit**

```bash
git add core/app_controller.py platforms/ytmusic/auth.py
git commit -m "feat: AppController multi-platform dispatch + YTMusic auth"
```

---

## Task 6 — Update `SearchPage` with platform tabs

**Files:**
- Modify: `ui/pages/search_page.py`

Add platform tab buttons between the search box and the track list. Switching tab re-runs the current query on the new platform. Each platform prompts for login if not yet authenticated.

- [ ] **Step 6.1: Replace `ui/pages/search_page.py`**

```python
# ui/pages/search_page.py
from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton
from PyQt6.QtCore import QTimer
from ui.components.track_list import TrackListWidget
from ui.theme import COLORS, FONTS

_PLATFORMS = [
    ("netease", "网易云"),
    ("ytmusic", "YouTube Music"),
]


class SearchPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_platform = "netease"
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._on_timer_fired)
        self._setup_ui()
        ctrl.search_results_ready.connect(self._track_list.set_tracks)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索音乐…")
        self._search_input.setObjectName("searchInput")
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        # Platform tab row
        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)
        self._tab_btns: dict[str, QPushButton] = {}
        for pid, label in _PLATFORMS:
            btn = QPushButton(label)
            btn.setObjectName("platformTab")
            btn.setCheckable(True)
            btn.setChecked(pid == self._current_platform)
            btn.clicked.connect(lambda _checked, p=pid: self._on_tab(p))
            self._tab_btns[pid] = btn
            tab_row.addWidget(btn)
        tab_row.addStretch()
        layout.addLayout(tab_row)

        self._track_list = TrackListWidget()
        self._track_list.track_selected.connect(
            lambda t: asyncio.ensure_future(self._ctrl.play_track(t))
        )
        layout.addWidget(self._track_list, stretch=1)

        self._apply_styles()

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #searchInput {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                padding: 8px 14px;
            }}
            #searchInput:focus {{
                border-color: {c['accent']};
            }}
            #platformTab {{
                background: transparent;
                border: 1px solid {c['border']};
                border-radius: 6px;
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                padding: 4px 12px;
            }}
            #platformTab:checked {{
                background-color: {c['accent']};
                border-color: {c['accent']};
                color: #000000;
                font-weight: bold;
            }}
            #platformTab:hover:!checked {{
                border-color: {c['text_secondary']};
                color: {c['text_primary']};
            }}
        """)

    # ── event handlers ────────────────────────────────────────────────────────

    def _on_tab(self, platform: str) -> None:
        if platform == self._current_platform:
            return
        self._current_platform = platform
        for pid, btn in self._tab_btns.items():
            btn.setChecked(pid == platform)
        self._track_list.clear()
        query = self._search_input.text().strip()
        if query:
            asyncio.ensure_future(self._do_search(query))

    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def _on_timer_fired(self) -> None:
        asyncio.ensure_future(self._do_search(self._search_input.text()))

    async def _do_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            self._track_list.clear()
            return

        platform = self._current_platform
        if platform == "netease":
            if not self._ctrl.is_netease_authenticated:
                ok = await self._ctrl.ensure_netease_auth(self)
                if not ok:
                    self._track_list.show_empty("需要登录网易云音乐")
                    return
        elif platform == "ytmusic":
            if not self._ctrl.is_ytmusic_authenticated:
                ok = await self._ctrl.ensure_ytmusic_auth(self)
                if not ok:
                    self._track_list.show_empty("需要登录 YouTube Music")
                    return

        self._track_list.show_loading()
        try:
            await self._ctrl.search(query, platform=platform)
        except Exception:
            self._track_list.show_empty("搜索失败，请检查网络连接")
```

- [ ] **Step 6.2: Run tests**

```bash
python3 -m pytest tests/ --ignore=tests/test_ui_components.py --ignore=tests/test_search_page.py -q
```

Expected: all pass.

- [ ] **Step 6.3: Commit**

```bash
git add ui/pages/search_page.py
git commit -m "feat: SearchPage platform tabs — Netease | YouTube Music"
```

---

## Task 7 — Wire `ytmusic_auth_changed` in `app_window.py`

**Files:**
- Modify: `ui/app_window.py`

Connect the new `ytmusic_auth_changed` signal to the sidebar's platform status indicator, and handle `ensure_ytmusic_auth` from the sidebar's platform login button.

- [ ] **Step 7.1: Add ytmusic signal wiring in `_wire_signals`**

In `ui/app_window.py`, inside `_wire_signals`, after the existing `netease_auth_changed` connection add:

```python
ctrl.ytmusic_auth_changed.connect(
    lambda ok: self.sidebar.set_platform_status("ytmusic", ok)
)
self.sidebar.set_platform_status("ytmusic", ctrl.is_ytmusic_authenticated)
```

And in `_on_platform_login`, extend the `if` chain:

```python
def _on_platform_login(self, platform_id: str) -> None:
    if platform_id == "netease":
        asyncio.ensure_future(self._ctrl.ensure_netease_auth(self))
    elif platform_id == "ytmusic":
        asyncio.ensure_future(self._ctrl.ensure_ytmusic_auth(self))
```

- [ ] **Step 7.2: Run full test suite**

```bash
python3 -m pytest tests/ --ignore=tests/test_ui_components.py --ignore=tests/test_search_page.py -q
```

Expected: all pass.

- [ ] **Step 7.3: Commit**

```bash
git add ui/app_window.py
git commit -m "feat: wire YouTube Music auth status into sidebar"
```

---

## Task 8 — Smoke-test end-to-end

Manual steps to verify the full flow works:

- [ ] **Step 8.1: Start the app**

```bash
python3 main.py
```

- [ ] **Step 8.2: Login to YouTube Music**
  - Click "YouTube Music" in the sidebar platform account section
  - WebView opens to `music.youtube.com`
  - Sign in with a Google account
  - Dialog closes automatically when `SAPISID` cookie is detected
  - Sidebar shows "● YouTube Music" in green

- [ ] **Step 8.3: Search YouTube Music**
  - Click "🔍 搜索" in sidebar
  - Click "YouTube Music" tab in search page
  - Type an artist or song name
  - Results appear within a few seconds (ytmusicapi search)

- [ ] **Step 8.4: Play a track**
  - Double-click any result
  - Progress bar starts at 0 and advances
  - Bottom bar shows title, artist, and album art thumbnail
  - Lyrics page shows LRCLIB lyrics (if available for that track) after a few seconds

- [ ] **Step 8.5: Commit final state**

```bash
git add -A
git commit -m "feat: Phase 4 — YouTube Music complete (search, play, lyrics)"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] WebView 登录 + Headers 捕获 → Task 1, 2
- [x] ytmusicapi 集成 (search, stream) → Task 4
- [x] 音频流获取（yt-dlp 辅助）→ Task 4 `_extract_stream_url`
- [x] 歌词源接入（LRCLIB）→ Task 3
- [x] Platform tab UI → Task 6
- [x] Sidebar auth status → Task 7
- [x] Credential persistence → Task 2 (`save_credential("ytmusic", ...)`)

**No placeholders:** All steps contain full, runnable code.

**Type consistency:**
- `YTMusicAuth.load_auth()` returns `dict[str, str] | None` → consumed by `YTMusicClient(headers: dict)`
- `AppController._ytm_auth` is `YTMusicAuth` → used in `init()`, `ensure_ytmusic_auth()`
- `AppController.search(query, platform)` — `SearchPage._do_search` passes `platform=self._current_platform`
- `LRCLibClient.get_lyrics(track: Track)` — called from `YTMusicClient.get_lyrics`
- All consistent.
