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
        self._ytm_client: "YTMusicClient | None" = None  # lazy import defers ytmusicapi/yt-dlp cost
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

    # ── Netease proxy management ──────────────────────────────────────────────

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

    async def ensure_netease_auth(self, parent: "QWidget | None" = None) -> bool:
        if self._netease_client is not None:
            return True
        cookies = await self._netease_auth.login(parent)
        if cookies:
            self._netease_client = NeteaseProxyClient(cookies)
            self.netease_auth_changed.emit(True)
            return True
        return False

    async def ensure_ytmusic_auth(self, parent: "QWidget | None" = None) -> bool:
        if self._ytm_client is not None:
            return True
        headers = await self._ytm_auth.login(parent)
        if headers:
            from platforms.ytmusic.client import YTMusicClient
            self._ytm_client = YTMusicClient(headers)
            self.ytmusic_auth_changed.emit(True)
            return True
        return False

    # ── search & playback ─────────────────────────────────────────────────────

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
