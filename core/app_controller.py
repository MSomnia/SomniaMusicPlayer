from __future__ import annotations
import asyncio
import logging
import shutil
import httpx
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState
from core.player import UnifiedPlayer
from core.queue import PlayQueue
from core.vlc_backend import VLCBackend
from db.repository import AppRepository
from platforms.netease.auth import NeteaseAuth
from platforms.netease.proxy_client import NeteaseProxyClient, DEFAULT_PROXY_URL

logger = logging.getLogger(__name__)

_PROXY_READY_TIMEOUT = 15  # seconds


class AppController(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._repo = AppRepository()
        self._auth = NeteaseAuth(self._repo)
        self._client: NeteaseProxyClient | None = None
        self._player = UnifiedPlayer()
        self._vlc = VLCBackend()
        self._queue = PlayQueue()
        self._proxy_process: asyncio.subprocess.Process | None = None
        self._wire_internal()

    @property
    def is_netease_authenticated(self) -> bool:
        return self._client is not None

    def _wire_internal(self) -> None:
        self._vlc.position_changed.connect(self._player.update_position)
        self._vlc.end_reached.connect(
            lambda: asyncio.ensure_future(self.play_next())
        )
        self._vlc.error_occurred.connect(self._player.on_load_error)
        self._player.state_changed.connect(self.state_changed)
        self._player.position_changed.connect(self.position_changed)

    async def init(self) -> None:
        await self._repo.init()
        await self._ensure_proxy()
        cookies = await self._auth.load_cookies()
        if cookies:
            self._client = NeteaseProxyClient(cookies)
            self.netease_auth_changed.emit(True)

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

    async def ensure_netease_auth(self, parent: "QWidget | None" = None) -> bool:
        if self._client is not None:
            return True
        cookies = await self._auth.login(parent)
        if cookies:
            self._client = NeteaseProxyClient(cookies)
            self.netease_auth_changed.emit(True)
            return True
        return False

    async def search(self, query: str) -> list[Track]:
        if not self._client:
            return []
        tracks = await self._client.search(query)
        self.search_results_ready.emit(tracks)
        return tracks

    async def play_track(self, track: Track) -> None:
        if self._client is None:
            return
        self._queue.set_tracks([track], 0)
        self._player.load(track)
        try:
            url = await self._client.get_stream_url(track)
            self._vlc.play(url)
            self._player.on_load_success()
        except Exception as exc:
            self._player.on_load_error(str(exc))

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
        repeat_mode = self._player.state.repeat_mode
        next_track = self._queue.next(repeat_mode)
        if next_track is None:
            self._vlc.stop()
            self._player.stop()
        else:
            await self.play_track(next_track)

    async def play_prev(self) -> None:
        prev_track = self._queue.previous()
        if prev_track is not None:
            await self.play_track(prev_track)

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
