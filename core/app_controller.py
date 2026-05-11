from __future__ import annotations
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState
from core.player import UnifiedPlayer
from core.queue import PlayQueue
from core.vlc_backend import VLCBackend
from db.repository import AppRepository
# NeteaseAuth is imported lazily (inside methods) to avoid importing
# QtWebEngineWidgets at module load time (it requires AA_ShareOpenGLContexts
# to be set before QApplication is created).
from platforms.netease.client import NeteaseClient


class AppController(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._repo = AppRepository()
        self._client: NeteaseClient | None = None
        self._player = UnifiedPlayer()
        self._vlc = VLCBackend()
        self._queue = PlayQueue()
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
        from platforms.netease.auth import NeteaseAuth
        await self._repo.init()
        auth = NeteaseAuth(self._repo)
        cookies = await auth.load_cookies()
        if cookies:
            self._client = NeteaseClient(cookies)
            self.netease_auth_changed.emit(True)

    async def ensure_netease_auth(self, parent=None) -> bool:
        if self._client is not None:
            return True
        from platforms.netease.auth import NeteaseAuth
        auth = NeteaseAuth(self._repo)
        cookies = await auth.login(parent)
        if cookies:
            self._client = NeteaseClient(cookies)
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

    async def get_initial_volume(self) -> int:
        val = await self._repo.get_setting("volume")
        return int(val) if val else 70

    async def close(self) -> None:
        await self._repo.close()
