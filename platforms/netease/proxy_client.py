from __future__ import annotations
import httpx
from core.models import Track, Playlist, LyricLine
from platforms.base import AbstractPlatform
from utils.lrc_parser import parse_lrc

# Default URL for a locally-running NeteaseCloudMusicApi instance.
# Start it with: npx @binaryify/netease-cloud-music-api
DEFAULT_PROXY_URL = "http://localhost:3000"


class NeteaseProxyClient(AbstractPlatform):
    """Calls a local NeteaseCloudMusicApi proxy instead of Netease directly.

    Avoids geo-blocking by delegating all requests to the local proxy server,
    which handles weapi encryption and routing internally.
    """

    platform_id = "netease"

    def __init__(
        self,
        cookies: dict[str, str],
        proxy_url: str = DEFAULT_PROXY_URL,
    ) -> None:
        self._cookies = cookies
        self._base = proxy_url.rstrip("/")
        self._uid: str | None = None

    def _cookie_str(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    async def is_authenticated(self) -> bool:
        return bool(self._cookies.get("MUSIC_U"))

    async def search(self, query: str, limit: int = 30) -> list[Track]:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/cloudsearch",
                params={"keywords": query, "type": 1, "limit": limit, "cookie": self._cookie_str()},
            )
            resp.raise_for_status()
            data = resp.json()
        songs = data.get("result", {}).get("songs", [])
        return [self._song_to_track(s) for s in songs]

    async def get_stream_url(self, track: Track) -> str:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/song/url/v1",
                params={"id": track.id, "level": "exhigh", "cookie": self._cookie_str()},
            )
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data", [])
        if not items or not items[0].get("url"):
            raise RuntimeError(f"No stream URL for track {track.id}")
        return items[0]["url"]

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/lyric",
                params={"id": track.id, "cookie": self._cookie_str()},
            )
            resp.raise_for_status()
            data = resp.json()
        lrc_text = data.get("lrc", {}).get("lyric", "")
        if not lrc_text:
            return []
        return parse_lrc(lrc_text)

    async def get_library_playlists(self) -> list[Playlist]:
        uid = await self._get_uid()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/user/playlist",
                params={"uid": uid, "limit": 50, "cookie": self._cookie_str()},
            )
            resp.raise_for_status()
            data = resp.json()
        playlists = data.get("playlist", [])
        return [
            Playlist(
                id=str(p["id"]),
                platform="netease",
                name=p["name"],
                cover_url=p.get("coverImgUrl", ""),
                track_count=p.get("trackCount", 0),
            )
            for p in playlists
        ]

    async def get_home(self) -> list[tuple[str, list[Track]]]:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/recommend/songs",
                params={"cookie": self._cookie_str()},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
        songs = data.get("data", {}).get("dailySongs", [])
        tracks = [self._song_to_track(s) for s in songs]
        return [("每日推荐", tracks)] if tracks else []

    async def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/playlist/track/all",
                params={"id": playlist_id, "limit": 200, "cookie": self._cookie_str()},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        songs = data.get("songs", [])
        return [self._song_to_track(s) for s in songs]

    async def _get_uid(self) -> str:
        if self._uid:
            return self._uid
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{self._base}/user/account",
                params={"cookie": self._cookie_str()},
            )
            resp.raise_for_status()
            data = resp.json()
        self._uid = str(data.get("account", {}).get("id", ""))
        return self._uid

    @staticmethod
    def _song_to_track(song: dict) -> Track:
        artists = [a["name"] for a in song.get("ar", [])]
        album = song.get("al", {})
        return Track(
            id=str(song["id"]),
            platform="netease",
            title=song["name"],
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name", ""),
            album_cover_url=album.get("picUrl", ""),
            duration_ms=song.get("dt", 0),
        )
