from __future__ import annotations
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from core.models import Track, Playlist, LyricLine
from platforms.base import AbstractPlatform

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ytmusic")

# User-Agent that matches what yt-dlp sends; returned alongside the stream URL
# so VLC can use it for the CDN request.
_YT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class YTMusicClient(AbstractPlatform):
    """Async wrapper around synchronous ytmusicapi + yt-dlp."""

    platform_id = "ytmusic"

    def __init__(self, headers: dict[str, str]) -> None:
        from ytmusicapi import YTMusic  # type: ignore[import]
        # Pass dict directly — ytmusicapi 1.12+ accepts str | dict | None for auth.
        # Passing json.dumps() makes ytmusicapi detect it as OAuth JSON; a dict
        # preserves the Authorization: SAPISIDHASH header needed for BROWSER detection.
        self._ytm = YTMusic(auth=headers)

    async def is_authenticated(self) -> bool:
        return bool(self._ytm)

    async def search(self, query: str, limit: int = 30) -> list[Track]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            _executor, lambda: self._ytm.search(query, filter="songs", limit=limit)
        )
        tracks = [self._to_track(r) for r in (results or []) if r.get("videoId")]
        return tracks

    async def get_stream_url(self, track: Track) -> str:
        if not track.id:
            raise ValueError(f"Track has no video ID: {track.title!r}")
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._extract_stream_url, track.id)

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        from platforms.ytmusic.lyrics import LRCLibClient
        return await LRCLibClient().get_lyrics(track)

    async def get_home(self) -> list[tuple[str, list[Track]]]:
        loop = asyncio.get_event_loop()
        try:
            home_data = await asyncio.wait_for(
                loop.run_in_executor(_executor, self._ytm.get_home),
                timeout=15.0,
            )
        except Exception as exc:
            logger.warning("YTMusic get_home failed: %s", exc)
            return []

        # Separate sections into those with individual songs vs. playlist shelves
        song_sections: list[tuple[str, list[Track]]] = []
        playlist_fallbacks: list[tuple[str, str]] = []  # (title, playlistId)

        for section in (home_data or [])[:6]:
            title = section.get("title", "")
            contents = section.get("contents", []) or []
            tracks = [self._to_track(item) for item in contents if item.get("videoId")]
            if tracks:
                song_sections.append((title, tracks))
            else:
                pids = [item["playlistId"] for item in contents if item.get("playlistId")]
                if pids and title:
                    playlist_fallbacks.append((title, pids[0]))

        if song_sections:
            return song_sections

        # Home page shows only playlists — load tracks from the first few sections
        results: list[tuple[str, list[Track]]] = []
        for title, pid in playlist_fallbacks[:3]:
            try:
                pl_data = await asyncio.wait_for(
                    loop.run_in_executor(
                        _executor, lambda p=pid: self._ytm.get_playlist(p, limit=10)
                    ),
                    timeout=10.0,
                )
                raw_tracks = (pl_data or {}).get("tracks", [])
                tracks = [self._to_track(t) for t in raw_tracks if t.get("videoId")]
                if tracks:
                    results.append((title, tracks))
            except Exception as exc:
                logger.debug("YTMusic home playlist fallback failed for %s: %s", pid, exc)
        return results

    async def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        loop = asyncio.get_event_loop()
        try:
            if playlist_id == "LM":
                # Special ID: ytmusicapi's Liked Music playlist
                data = await loop.run_in_executor(
                    _executor, lambda: self._ytm.get_liked_songs(limit=200)
                )
            else:
                data = await loop.run_in_executor(
                    _executor, lambda: self._ytm.get_playlist(playlist_id, limit=200)
                )
        except Exception as exc:
            logger.warning("YTMusic get_playlist_tracks failed: %s", exc)
            return []
        tracks_raw = (data or {}).get("tracks", [])
        return [self._to_track(t) for t in tracks_raw if t.get("videoId")]

    async def get_recommendations(self, track: Track) -> list[Track]:
        if not track.id:
            return []
        loop = asyncio.get_event_loop()
        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    _executor,
                    lambda: self._ytm.get_watch_playlist(videoId=track.id, limit=15),
                ),
                timeout=12.0,
            )
        except Exception as exc:
            logger.warning("YTMusic get_watch_playlist failed: %s", exc)
            return []
        raw = (data or {}).get("tracks", [])
        return [self._to_track(t) for t in raw if t.get("videoId")]

    async def get_library_playlists(self) -> list[Playlist]:
        loop = asyncio.get_event_loop()
        playlists: list[Playlist] = []

        # Liked Music comes first — ytmusicapi exposes it separately
        try:
            liked = await loop.run_in_executor(
                _executor, lambda: self._ytm.get_liked_songs(limit=1)
            )
            if liked is not None:
                count = liked.get("trackCount") or len(liked.get("tracks", []))
                playlists.append(Playlist(
                    id="LM",
                    platform="ytmusic",
                    name="喜欢的歌曲",
                    cover_url="",
                    track_count=int(count) if str(count).isdigit() else 0,
                ))
        except Exception as exc:
            logger.debug("YTMusic get_liked_songs failed (not critical): %s", exc)

        # User-created / saved playlists
        try:
            raw = await loop.run_in_executor(
                _executor, self._ytm.get_library_playlists
            )
            playlists.extend(self._to_playlist(p) for p in (raw or []))
        except Exception as exc:
            logger.warning("YTMusic get_library_playlists failed: %s", exc)

        return playlists

    def _extract_stream_url(self, video_id: str) -> str:
        import yt_dlp  # type: ignore[import]

        if not video_id:
            raise ValueError("Empty video_id passed to _extract_stream_url")

        opts = {
            # Prefer opus/webm (best quality audio-only); fall back to m4a, then any
            "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            # Do NOT skip DASH — audio-only DASH streams are direct HTTP URLs
            # (not manifests) and are the highest-quality option on YouTube.
        }

        yt_url = f"https://music.youtube.com/watch?v={video_id}"
        logger.debug("Extracting stream URL for video %s", video_id)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(yt_url, download=False)

        if not info:
            raise RuntimeError(f"yt-dlp returned no info for video {video_id!r}")

        # yt-dlp already applied the format selector; info["url"] is the winner.
        stream_url = info.get("url")

        # When video+audio are merged into separate tracks, URLs live here:
        if not stream_url:
            for fmt in info.get("requested_formats", []):
                u = fmt.get("url")
                if u and fmt.get("acodec") not in (None, "none"):
                    stream_url = u
                    break

        # Last resort: scan formats manually
        if not stream_url:
            fmts = [
                f for f in info.get("formats", [])
                if f.get("url") and f.get("acodec") not in (None, "none")
            ]
            if fmts:
                stream_url = max(fmts, key=lambda f: f.get("abr") or f.get("tbr") or 0)["url"]

        if not stream_url:
            raise RuntimeError(f"No playable stream URL found for video {video_id!r}")

        logger.debug("Stream URL extracted: %s…", stream_url[:60])
        return stream_url

    @staticmethod
    def _parse_duration(r: dict) -> int:
        """Return duration_ms from a ytmusicapi track dict.

        Different endpoints use different fields:
          - search()            → duration_seconds (int)
          - get_watch_playlist()→ length ("M:SS" string)
          - get_home()          → nothing (all None); VLC will fill it in later
        """
        secs = r.get("duration_seconds")
        if secs:
            return int(secs) * 1000
        for key in ("length", "duration"):
            val = r.get(key)
            if not val or not isinstance(val, str):
                continue
            try:
                parts = [int(p) for p in val.strip().split(":")]
                if len(parts) == 2:
                    return (parts[0] * 60 + parts[1]) * 1000
                if len(parts) == 3:
                    return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
            except (ValueError, IndexError):
                pass
        return 0

    @staticmethod
    def _to_track(r: dict) -> Track:
        artists = [a["name"] for a in r.get("artists") or []]
        album_obj = r.get("album") or {}
        # watch_playlist uses "thumbnail" (singular); others use "thumbnails"
        thumbs = r.get("thumbnails") or []
        if not thumbs:
            thumb = r.get("thumbnail")
            if isinstance(thumb, dict):
                thumbs = thumb.get("thumbnails") or []
        cover = thumbs[-1]["url"] if thumbs else ""
        return Track(
            id=r.get("videoId") or "",
            platform="ytmusic",
            title=r.get("title", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album_obj.get("name", "") if isinstance(album_obj, dict) else "",
            album_cover_url=cover,
            duration_ms=YTMusicClient._parse_duration(r),
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
