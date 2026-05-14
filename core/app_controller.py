from __future__ import annotations
import asyncio
import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState
from core.librespot_backend import LibrespotBackend
from core.player import UnifiedPlayer
from core.queue import PlayQueue
from core.vlc_backend import VLCBackend
from db.repository import AppRepository
from platforms.base import AbstractPlatform
from platforms.netease.auth import NeteaseAuth
from platforms.netease.proxy_client import NeteaseProxyClient, DEFAULT_PROXY_URL
from platforms.spotify.auth import SpotifyAuth
from platforms.spotify.librespot_bridge import LibrespotBridge
from platforms.ytmusic.auth import YTMusicAuth

logger = logging.getLogger(__name__)

_LIBRESPOT_FATAL_CODES = ("TravelRestriction", "PremiumAccountRequired", "BadCredentials")

_HOME_CACHE_TTL = 600     # 10 min — recommendations change infrequently
_LIBRARY_CACHE_TTL = 300  # 5 min  — playlists may be edited occasionally
_TRACKS_CACHE_TTL = 300   # 5 min  — playlist contents

_PREFETCH_THRESHOLD: dict[str, int] = {
    "netease": 5_000,    # 5s  — get_stream_url ≈ 200-800ms
    "ytmusic": 25_000,   # 25s — yt-dlp 解析 ≈ 8-15s
    "spotify": 20_000,   # 20s — 提前准备 autoplay；librespot 下载超出本次范围
}
_PREFETCH_FALLBACK_MS = 30_000   # 无时长时，播放满 30s 后触发


def _is_fatal_librespot_error(exc_str: str) -> bool:
    return any(code in exc_str for code in _LIBRESPOT_FATAL_CODES)


def _librespot_fatal_message(exc_str: str) -> str:
    if "PremiumAccountRequired" in exc_str:
        return (
            "Spotify 流媒体播放需要 Premium 订阅。"
            "免费账号无法通过 librespot 客户端播放完整曲目。"
        )
    if "TravelRestriction" in exc_str or "BadCredentials" in exc_str:
        return (
            "Spotify AP 服务器拒绝了连接。可能原因：\n"
            "① 需要 Spotify Premium 订阅（免费账号不支持第三方客户端流式播放）\n"
            "② librespot-python 与当前 Spotify AP 版本不兼容"
        )
    return f"Spotify 播放凭证创建失败：{exc_str}"


_PROXY_READY_TIMEOUT = 15
_color_executor = ThreadPoolExecutor(max_workers=1)

_YT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _vlc_options_for(platform: str) -> list[str]:
    """Return platform-specific VLC media options."""
    if platform == "ytmusic":
        # YouTube CDN validates the User-Agent on some CDN nodes.
        # Use the same UA that yt-dlp sends to avoid 403 responses.
        return [
            f":http-user-agent={_YT_UA}",
            ":http-reconnect=true",
        ]
    return []


class AppController(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)
    ytmusic_auth_changed = pyqtSignal(bool)
    spotify_auth_changed = pyqtSignal(bool)
    lyrics_ready = pyqtSignal(list)
    cover_color_ready = pyqtSignal(int, int, int)
    cover_art_bytes = pyqtSignal(bytes)
    # Phase 6
    home_sections_ready = pyqtSignal(str, list)   # (platform, [(title, [Track])])
    library_ready = pyqtSignal(str, list)          # (platform, [Playlist])
    album_search_ready = pyqtSignal(str, list)     # (platform, [Album])
    queue_changed = pyqtSignal(list, int)          # ([Track], current_index)
    settings_ready = pyqtSignal(dict)
    profile_changed = pyqtSignal(str)
    background_changed = pyqtSignal(str)
    volume_changed = pyqtSignal(int)
    artist_ready = pyqtSignal(object)         # Artist
    artist_tracks_ready = pyqtSignal(list)    # list[Track]

    def __init__(self) -> None:
        super().__init__()
        self._repo = AppRepository()
        self._netease_auth = NeteaseAuth(self._repo)
        self._ytm_auth = YTMusicAuth(self._repo)
        self._netease_client: NeteaseProxyClient | None = None
        self._ytm_client: "YTMusicClient | None" = None  # lazy import defers ytmusicapi/yt-dlp cost
        self._spotify_auth = SpotifyAuth(self._repo)
        creds_path = str(Path.home() / ".somniaplayer" / "spotify_credentials.json")
        self._librespot_bridge = LibrespotBridge(creds_path)
        self._spotify_client: "SpotifyClient | None" = None
        self._player = UnifiedPlayer()
        self._vlc = VLCBackend()
        self._librespot = LibrespotBackend(self._librespot_bridge)
        self._queue = PlayQueue()
        self._proxy_process: asyncio.subprocess.Process | None = None
        # (platform) → (timestamp, data)
        self._home_cache: dict[str, tuple[float, list]] = {}
        self._library_cache: dict[str, tuple[float, list]] = {}
        # "platform:playlist_id" → (timestamp, tracks)
        self._tracks_cache: dict[str, tuple[float, list]] = {}
        self._display_name = "Somnia"
        self._background_image_path = ""
        self.last_playlist_error = ""
        self._prefetch_task: asyncio.Task | None = None
        self._prefetch_done: bool = False
        self._prefetched_next_track: Track | None = None
        self._prefetched_autoplay: list[Track] | None = None
        from core.macos_media import MacOSMediaHandler
        self._macos_media = MacOSMediaHandler(self)
        self._wire_internal()

    # ── properties ────────────────────────────────────────────────────────────

    @property
    def is_netease_authenticated(self) -> bool:
        return self._netease_client is not None

    @property
    def is_ytmusic_authenticated(self) -> bool:
        return self._ytm_client is not None

    @property
    def is_spotify_authenticated(self) -> bool:
        return self._spotify_client is not None

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def background_image_path(self) -> str:
        return self._background_image_path

    # ── internal wiring ───────────────────────────────────────────────────────

    def _wire_internal(self) -> None:
        self._vlc.position_changed.connect(self._player.update_position)
        if hasattr(self._vlc, "duration_changed"):
            self._vlc.duration_changed.connect(self._player.update_duration)
        self._vlc.end_reached.connect(
            lambda: asyncio.ensure_future(self.play_next())
        )
        self._vlc.error_occurred.connect(self._player.on_load_error)
        self._librespot.position_changed.connect(self._player.update_position)
        self._librespot.end_reached.connect(
            lambda: asyncio.ensure_future(self.play_next())
        )
        self._librespot.error_occurred.connect(self._player.on_load_error)
        self._librespot.playback_started.connect(self._player.on_load_success)
        self._player.state_changed.connect(self.state_changed)
        self._player.state_changed.connect(self._on_player_state_changed)
        self._player.position_changed.connect(self.position_changed)
        self._player.position_changed.connect(self._on_position_changed)
        self.cover_art_bytes.connect(self._macos_media.set_cover_data)

    def _get_platform_client(self, platform: str) -> AbstractPlatform | None:
        if platform == "netease":
            return self._netease_client
        if platform == "ytmusic":
            return self._ytm_client
        if platform == "spotify":
            return self._spotify_client
        return None

    # ── initialisation ────────────────────────────────────────────────────────

    async def init(self) -> None:
        await self._repo.init()
        self._display_name = (await self._repo.get_setting("display_name")) or "Somnia"
        self._background_image_path = (
            await self._repo.get_setting("background_image_path")
        ) or ""
        await self._ensure_proxy()
        # Restore Netease session
        cookies = await self._netease_auth.load_cookies()
        if cookies:
            self._netease_client = NeteaseProxyClient(cookies)
            self.netease_auth_changed.emit(True)
        # Restore YouTube Music session
        headers = await self._ytm_auth.load_auth()
        if headers:
            try:
                from platforms.ytmusic.client import YTMusicClient
                self._ytm_client = YTMusicClient(headers)
                self.ytmusic_auth_changed.emit(True)
            except Exception as exc:
                logger.warning("YTMusic client init failed (stale credentials?): %s", exc)
        # Restore Spotify session
        sp_dc = await self._spotify_auth.load_sp_dc()
        if sp_dc:
            from platforms.spotify.client import SpotifyClient
            self._spotify_client = SpotifyClient(self._spotify_auth)
            self.spotify_auth_changed.emit(True)
            try:
                self._librespot_bridge.create_session()
                logger.info("Librespot session restored from stored credentials")
            except Exception as exc:
                logger.info("Librespot stored credentials not ready: %s", exc)

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
        if not headers:
            return False
        try:
            from platforms.ytmusic.client import YTMusicClient
            self._ytm_client = YTMusicClient(headers)
            self.ytmusic_auth_changed.emit(True)
            return True
        except Exception as exc:
            logger.error("YTMusic client init failed: %s", exc)
            return False

    async def ensure_spotify_auth(self, parent: "QWidget | None" = None) -> bool:
        if self._spotify_client is not None:
            await self._ensure_librespot_session(parent, prompt=True)
            return True
        sp_dc = await self._spotify_auth.login(parent)
        if not sp_dc:
            return False
        from platforms.spotify.client import SpotifyClient
        self._spotify_client = SpotifyClient(self._spotify_auth)
        self.spotify_auth_changed.emit(True)
        await self._ensure_librespot_session(parent, prompt=True)
        return True

    # ── cache accessors (synchronous, for UI pre-checks) ─────────────────────

    def get_cached_home(self, platform: str) -> list | None:
        entry = self._home_cache.get(platform)
        return entry[1] if entry else None

    def get_cached_library(self, platform: str) -> list | None:
        entry = self._library_cache.get(platform)
        return entry[1] if entry else None

    def get_cached_tracks(self, platform: str, playlist_id: str) -> list | None:
        entry = self._tracks_cache.get(f"{platform}:{playlist_id}")
        if not entry:
            return None
        ts, tracks = entry
        return tracks if time.time() - ts < _TRACKS_CACHE_TTL else None

    def _evict_platform(self, platform: str) -> None:
        self._home_cache.pop(platform, None)
        self._library_cache.pop(platform, None)
        prefix = f"{platform}:"
        stale = [k for k in self._tracks_cache if k.startswith(prefix)]
        for k in stale:
            del self._tracks_cache[k]

    async def logout_netease(self) -> None:
        await self._netease_auth.logout()
        self._netease_client = None
        self.netease_auth_changed.emit(False)
        self._evict_platform("netease")

    async def logout_ytmusic(self) -> None:
        await self._ytm_auth.logout()
        self._ytm_client = None
        self.ytmusic_auth_changed.emit(False)
        self._evict_platform("ytmusic")

    async def logout_spotify(self) -> None:
        await self._spotify_auth.logout()
        self._spotify_client = None
        self.spotify_auth_changed.emit(False)
        self._evict_platform("spotify")

    async def get_account_name(self, platform: str) -> str | None:
        if platform == "netease":
            return await self._netease_auth.get_display_name()
        if platform == "ytmusic":
            return await self._ytm_auth.get_display_name()
        if platform == "spotify":
            return await self._spotify_auth.get_display_name()
        return None

    async def _ensure_librespot_session(
        self,
        parent: "QWidget | None" = None,
        prompt: bool = False,
    ) -> None:
        if self._librespot_bridge.has_session():
            return

        # 1. Try stored credentials (fastest path, subsequent launches)
        try:
            self._librespot_bridge.create_session()
            logger.info("Librespot session created from stored credentials")
            return
        except Exception as exc:
            logger.info("Librespot stored credentials unavailable: %s", exc)

        # 2. Try with the sp_dc access token — AUTHENTICATION_SPOTIFY_TOKEN was
        #    designed for web-player tokens and avoids the keymaster OAuth flow.
        if self._spotify_auth is not None:
            try:
                token = await self._spotify_auth.get_access_token()
                await asyncio.get_event_loop().run_in_executor(
                    None, self._librespot_bridge.create_session_with_token, token
                )
                logger.info("Librespot session created with sp_dc access token")
                return
            except Exception as exc:
                exc_str = str(exc)
                if _is_fatal_librespot_error(exc_str):
                    raise RuntimeError(_librespot_fatal_message(exc_str)) from exc
                logger.info("Librespot sp_dc token auth failed: %s", exc)

        if not prompt:
            return
        await self._prompt_librespot_credentials(parent)

    async def _prompt_librespot_credentials(self, parent: "QWidget | None" = None) -> None:
        """Start librespot OAuth browser flow and wait for completion."""
        import webbrowser
        from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

        loop = asyncio.get_event_loop()
        url_holder: list[str] = []
        url_ready: asyncio.Event = asyncio.Event()

        def _url_callback(url: str) -> None:
            url_holder.append(url)
            loop.call_soon_threadsafe(url_ready.set)

        oauth_future = loop.run_in_executor(
            None, self._librespot_bridge.create_session_oauth, _url_callback
        )

        # Wait for librespot to generate the OAuth URL (fast, <1s normally)
        try:
            await asyncio.wait_for(url_ready.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.error("Librespot OAuth: URL not generated within 15s")
            return

        if not url_holder:
            logger.error("Librespot OAuth: empty URL received")
            return

        oauth_url = url_holder[0]

        dialog = QDialog(parent)
        dialog.setWindowTitle("Spotify — 授权登录")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("请在浏览器中完成 Spotify 登录，完成后此窗口自动关闭。"))

        reopen_btn = QPushButton("重新打开浏览器")
        reopen_btn.clicked.connect(lambda: webbrowser.open(oauth_url))
        layout.addWidget(reopen_btn)

        dialog.show()
        webbrowser.open(oauth_url)

        try:
            await asyncio.wait_for(oauth_future, timeout=120.0)
            logger.info("Librespot OAuth session created")
        except asyncio.TimeoutError:
            dialog.close()
            raise RuntimeError(
                "Spotify 授权超时（120s）。请重试并及时在浏览器中完成登录。"
            )
        except Exception as exc:
            dialog.close()
            exc_str = str(exc)
            logger.error("Librespot credential error: %s", exc)
            raise RuntimeError(_librespot_fatal_message(exc_str)) from exc
        else:
            dialog.close()

    # ── search & playback ─────────────────────────────────────────────────────

    async def search(self, query: str, platform: str = "netease") -> list[Track]:
        client = self._get_platform_client(platform)
        if not client:
            return []
        tracks = await client.search(query)
        self.search_results_ready.emit(tracks)
        return tracks

    async def search_albums(self, query: str, platform: str = "netease") -> None:
        client = self._get_platform_client(platform)
        if not client:
            self.album_search_ready.emit(platform, [])
            return
        try:
            albums = await client.search_albums(query, limit=6)
        except Exception as exc:
            logger.warning("search_albums failed for %s: %s", platform, exc)
            albums = []
        self.album_search_ready.emit(platform, albums)

    async def get_album_tracks(self, album) -> list:
        client = self._get_platform_client(album.platform)
        if not client:
            return []
        try:
            return await client.get_album_tracks(album.id)
        except Exception as exc:
            logger.warning("get_album_tracks failed: %s", exc)
            return []

    async def play_track(self, track: Track) -> None:
        client = self._get_platform_client(track.platform)
        if client is None:
            logger.warning("No client for platform %r", track.platform)
            return
        if len(self._queue.tracks) == 0 or self._queue.current_track != track:
            self._queue.set_tracks([track], 0)
        self._emit_queue_changed()
        self._prefetch_done = False
        self._prefetched_next_track = None
        self._prefetched_autoplay = None
        if self._prefetch_task is not None:
            self._prefetch_task.cancel()
            self._prefetch_task = None
        self._player.load(track)
        try:
            if track.platform == "spotify":
                self._vlc.stop()
                await self._ensure_librespot_session(prompt=True)
                if not self._librespot_bridge.has_session():
                    raise RuntimeError(
                        "Spotify 播放凭证未创建。首次播放需要完成 librespot 账号密码登录。"
                    )
                self._librespot.play(track.id)
            else:
                self._librespot.stop()
                url = track.stream_url or await client.get_stream_url(track)
                vlc_opts = _vlc_options_for(track.platform)
                self._vlc.play(url, vlc_opts)
                self._player.on_load_success()
        except Exception as exc:
            logger.error("play_track failed for %r (%s): %s", track.title, track.platform, exc)
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
        current = self._player.state.current_track
        is_spotify = current is not None and current.platform == "spotify"
        if status == "playing":
            if is_spotify:
                self._librespot.pause()
            else:
                self._vlc.pause()
            self._player.pause()
        elif status == "paused":
            if is_spotify:
                self._librespot.resume()
            else:
                self._vlc.pause()
            self._player.resume()

    def seek(self, ms: int) -> None:
        current = self._player.state.current_track
        if current and current.platform == "spotify":
            self._librespot.seek(ms)
        else:
            self._vlc.seek(ms)
        self._player.seek(ms)

    async def play_next(self) -> None:
        next_track = self._queue.next(self._player.state.repeat_mode)
        if next_track is not None:
            await self.play_track(next_track)
            return
        # 队列已空：优先使用预取的推荐列表
        if self._prefetched_autoplay:
            recs = self._prefetched_autoplay
            self._prefetched_autoplay = None
            self._vlc.stop()
            self._librespot.stop()
            self._player.stop()
            self._queue.set_tracks(recs, 0)
            self._emit_queue_changed()
            await self.play_track(recs[0])
        else:
            seed = self._player.state.current_track
            self._vlc.stop()
            self._librespot.stop()
            self._player.stop()
            if seed:
                asyncio.ensure_future(self._autoplay(seed))

    async def _autoplay(self, seed: Track) -> None:
        client = self._get_platform_client(seed.platform)
        if not client:
            self._vlc.stop()
            self._player.stop()
            return
        try:
            tracks = await client.get_recommendations(seed)
        except Exception as exc:
            logger.warning("Autoplay recommendations failed for %r: %s", seed.title, exc)
            tracks = []
        # Drop the seed track to avoid immediate repetition
        tracks = [t for t in tracks if t.id != seed.id]
        if not tracks:
            self._vlc.stop()
            self._player.stop()
            return
        self._queue.set_tracks(tracks, 0)
        self._emit_queue_changed()
        await self.play_track(tracks[0])

    async def play_prev(self) -> None:
        prev = self._queue.previous()
        if prev is not None:
            await self.play_track(prev)

    def set_volume(self, v: int) -> None:
        volume = max(0, min(int(v), 100))
        self._vlc.set_volume(volume)
        self._librespot.set_volume(volume)
        self.volume_changed.emit(volume)
        asyncio.ensure_future(self._repo.set_setting("volume", str(volume)))

    async def get_initial_volume(self) -> int:
        val = await self._repo.get_setting("volume")
        return int(val) if val else 70

    async def close(self) -> None:
        self._librespot.stop()
        self._librespot_bridge.close()
        await self._repo.close()
        if self._proxy_process is not None:
            self._proxy_process.terminate()
            try:
                await asyncio.wait_for(self._proxy_process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proxy_process.kill()
            self._proxy_process = None

    # ── macOS media integration ───────────────────────────────────────────────

    def _on_player_state_changed(self, state) -> None:
        self._macos_media.update_full(
            state.current_track,
            state.position_ms,
            state.status == "playing",
        )

    def _on_position_changed(self, position_ms: int) -> None:
        state = self._player.state
        self._macos_media.update_position(position_ms, state.status == "playing")
        if (
            state.status == "playing"
            and state.current_track is not None
            and not self._prefetch_done
            and self._prefetch_task is None
        ):
            platform = state.current_track.platform
            threshold = _PREFETCH_THRESHOLD.get(platform, _PREFETCH_FALLBACK_MS)
            duration = state.duration_ms
            if duration > 0:
                should = (duration - position_ms) <= threshold
            else:
                should = position_ms >= _PREFETCH_FALLBACK_MS
            if should:
                self._prefetch_done = True
                self._prefetch_task = asyncio.ensure_future(self._prefetch_next())

    async def _prefetch_next(self) -> None:
        try:
            state = self._player.state
            if state.current_track is None:
                return
            repeat_mode = state.repeat_mode
            next_track = self._queue.peek_next(repeat_mode)
            if next_track is not None:
                await self._prefetch_stream_url(next_track)
                self._prefetched_next_track = next_track
            else:
                client = self._get_platform_client(state.current_track.platform)
                if client is None:
                    return
                recs = await client.get_recommendations(state.current_track)
                recs = [t for t in recs if t.id != state.current_track.id]
                if recs:
                    self._prefetched_autoplay = recs
                    await self._prefetch_stream_url(recs[0])
        except Exception:
            pass
        finally:
            self._prefetch_task = None

    async def _prefetch_stream_url(self, track: Track) -> None:
        if track.stream_url:
            return
        if track.platform == "spotify":
            return
        client = self._get_platform_client(track.platform)
        if client is None:
            return
        url = await client.get_stream_url(track)
        if url:
            track.stream_url = url

    # ── home recommendations ──────────────────────────────────────────────────

    async def load_home(self, platform: str) -> None:
        client = self._get_platform_client(platform)
        if not client:
            self.home_sections_ready.emit(platform, [])
            return
        now = time.time()
        cached = self._home_cache.get(platform)
        if cached:
            ts, data = cached
            self.home_sections_ready.emit(platform, data)
            if now - ts < _HOME_CACHE_TTL:
                return  # fresh — skip network request
        try:
            sections = await client.get_home()
        except Exception as exc:
            logger.warning("get_home failed for %s: %s", platform, exc)
            if not cached:
                self.home_sections_ready.emit(platform, [])
            return
        self._home_cache[platform] = (now, sections)
        self.home_sections_ready.emit(platform, sections)

    # ── library ───────────────────────────────────────────────────────────────

    async def load_library(self, platform: str) -> None:
        client = self._get_platform_client(platform)
        if not client:
            self.library_ready.emit(platform, [])
            return
        now = time.time()
        cached = self._library_cache.get(platform)
        if cached:
            ts, data = cached
            self.library_ready.emit(platform, data)
            if now - ts < _LIBRARY_CACHE_TTL:
                return  # fresh — skip network request
        try:
            playlists = await client.get_library_playlists()
        except Exception as exc:
            logger.warning(
                "get_library_playlists failed for %s: %r", platform, exc
            )
            if not cached:
                self.library_ready.emit(platform, [])
            return
        self._library_cache[platform] = (now, playlists)
        self.library_ready.emit(platform, playlists)

    async def get_playlist_tracks(self, playlist) -> list:
        key = f"{playlist.platform}:{playlist.id}"
        now = time.time()
        cached = self._tracks_cache.get(key)
        if cached:
            ts, data = cached
            if now - ts < _TRACKS_CACHE_TTL:
                return data  # fresh — no network request
        client = self._get_platform_client(playlist.platform)
        if not client:
            return cached[1] if cached else []
        try:
            tracks = await client.get_playlist_tracks(playlist.id)
        except Exception as exc:
            logger.warning("get_playlist_tracks failed: %s", exc)
            return cached[1] if cached else []
        self._tracks_cache[key] = (now, tracks)
        return tracks

    async def get_addable_playlists(self, platform: str) -> list:
        client = self._get_platform_client(platform)
        if not client:
            return []
        try:
            playlists = await client.get_addable_playlists()
        except Exception as exc:
            logger.warning("get_addable_playlists failed for %s: %s", platform, exc)
            return []
        self._library_cache[platform] = (time.time(), playlists)
        return playlists

    async def add_track_to_playlist(self, track: Track, playlist) -> bool:
        self.last_playlist_error = ""
        if track.platform != playlist.platform:
            logger.warning(
                "Refusing cross-platform playlist add: track=%s playlist=%s",
                track.platform,
                playlist.platform,
            )
            self.last_playlist_error = "歌曲和歌单不属于同一平台"
            return False
        client = self._get_platform_client(track.platform)
        if not client:
            self.last_playlist_error = "需要先登录对应平台"
            return False
        try:
            ok = await client.add_track_to_playlist(playlist.id, track)
        except Exception as exc:
            logger.warning("add_track_to_playlist failed: %s", exc)
            self.last_playlist_error = "加入歌单失败"
            return False
        if ok:
            self._library_cache.pop(track.platform, None)
            self._tracks_cache.pop(f"{track.platform}:{playlist.id}", None)
        else:
            self.last_playlist_error = (
                getattr(client, "last_playlist_error", "") or "加入歌单失败"
            )
        return ok

    # ── queue management ──────────────────────────────────────────────────────

    def _emit_queue_changed(self) -> None:
        self.queue_changed.emit(list(self._queue.tracks), self._queue.current_index)

    def add_to_queue(self, track: Track) -> None:
        self._queue.add(track)
        self._emit_queue_changed()

    def play_queue_tracks(self, tracks: list, start: int = 0) -> None:
        if not tracks:
            return
        self._queue.set_tracks(tracks, start)
        asyncio.ensure_future(self.play_track(tracks[start]))

    async def jump_to_queue_index(self, index: int) -> None:
        track = self._queue.tracks[index] if 0 <= index < len(self._queue.tracks) else None
        if track is None:
            return
        self._queue._index = index
        await self.play_track(track)

    @property
    def queue_tracks(self) -> list:
        return list(self._queue.tracks)

    @property
    def queue_index(self) -> int:
        return self._queue.current_index

    # ── shuffle / repeat ──────────────────────────────────────────────────────

    def toggle_shuffle(self) -> None:
        new_val = not self._player.state.shuffle
        self._player.set_shuffle(new_val)
        if new_val:
            self._queue.shuffle()
            self._emit_queue_changed()
        asyncio.ensure_future(self._repo.set_setting("shuffle", str(new_val).lower()))

    def cycle_repeat_mode(self) -> None:
        modes = ("none", "all", "one")
        current = self._player.state.repeat_mode
        next_mode = modes[(modes.index(current) + 1) % len(modes)]
        self._player.set_repeat_mode(next_mode)
        asyncio.ensure_future(self._repo.set_setting("repeat_mode", next_mode))

    # ── settings ──────────────────────────────────────────────────────────────

    async def load_settings(self) -> None:
        keys = (
            "volume",
            "repeat_mode",
            "shuffle",
            "cover_rotation",
            "lyrics_font_size",
            "display_name",
            "background_image_path",
        )
        result = {}
        for key in keys:
            val = await self._repo.get_setting(key)
            result[key] = val
        self.settings_ready.emit(result)

    async def save_setting(self, key: str, value: str) -> None:
        if key == "display_name":
            value = value.strip() or "Somnia"
            self._display_name = value
        elif key == "background_image_path":
            value = value.strip()
            self._background_image_path = value
        await self._repo.set_setting(key, value)
        if key == "display_name":
            self.profile_changed.emit(value)
        elif key == "background_image_path":
            self.background_changed.emit(value)

    # ── artist ────────────────────────────────────────────────────────────────

    @property
    def current_state(self) -> PlayerState:
        return self._player.state

    async def load_artist(self, artist_name: str, platform: str) -> None:
        client = self._get_platform_client(platform)
        if client is None:
            logger.warning("load_artist: no client for platform %r", platform)
            return
        try:
            artist = await client.search_artist(artist_name)
        except Exception as exc:
            logger.warning("load_artist search_artist failed: %s", exc)
            return
        if artist is None:
            return
        self.artist_ready.emit(artist)
        try:
            tracks = await client.get_artist_top_tracks(artist.id)
        except Exception as exc:
            logger.warning("load_artist get_artist_top_tracks failed: %s", exc)
            tracks = []
        self.artist_tracks_ready.emit(tracks)
