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

    async def is_authenticated(self) -> bool:
        # Client can only be constructed with headers; True as long as they exist
        return bool(self._ytm)

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
            if f.get("acodec") not in (None, "none")
            and f.get("vcodec") in ("none", None)
        ]
        if audio_only:
            best = max(audio_only, key=lambda f: f.get("abr") or 0)
            return best["url"]
        fallback = info.get("url")
        if not fallback:
            raise RuntimeError(f"No audio stream available for video {video_id!r}")
        return fallback

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
