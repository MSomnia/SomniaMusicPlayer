from __future__ import annotations
import httpx
from core.models import Track, Playlist, LyricLine
from platforms.base import AbstractPlatform
from platforms.netease.crypto import weapi_encrypt

_BASE_URL = "https://music.163.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
    "Origin": "https://music.163.com",
    "Content-Type": "application/x-www-form-urlencoded",
}


class NeteaseClient(AbstractPlatform):
    platform_id = "netease"

    def __init__(self, cookies: dict[str, str]) -> None:
        self._cookies = cookies

    async def is_authenticated(self) -> bool:
        return bool(self._cookies.get("MUSIC_U"))

    async def search(self, query: str, limit: int = 30) -> list[Track]:
        payload = weapi_encrypt({"s": query, "type": 1, "limit": limit, "offset": 0})
        async with httpx.AsyncClient(
            headers=_HEADERS, cookies=self._cookies
        ) as http:
            resp = await http.post(
                f"{_BASE_URL}/weapi/cloudsearch/pc", data=payload
            )
            resp.raise_for_status()
            if not resp.content:
                return []
            data = resp.json()
        songs = data.get("result", {}).get("songs", [])
        return [self._song_to_track(s) for s in songs]

    async def get_stream_url(self, track: Track) -> str:
        payload = weapi_encrypt({
            "ids": [int(track.id)],
            "level": "exhigh",
            "encodeType": "flac",
            "csrf_token": self._cookies.get("__csrf", ""),
        })
        async with httpx.AsyncClient(
            headers=_HEADERS, cookies=self._cookies
        ) as http:
            resp = await http.post(
                f"{_BASE_URL}/weapi/song/enhance/player/url/v1", data=payload
            )
            resp.raise_for_status()
            if not resp.content:
                raise RuntimeError(f"Empty response for track {track.id}")
            data = resp.json()
        items = data.get("data", [])
        if not items or not items[0].get("url"):
            raise RuntimeError(f"No stream URL for track {track.id}")
        return items[0]["url"]

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        from platforms.netease.lyrics import NeteaseLyrics
        return await NeteaseLyrics(self._cookies).get_lyrics(track)

    async def get_library_playlists(self) -> list[Playlist]:
        uid = await self._get_uid()
        payload = weapi_encrypt({
            "uid": uid,
            "limit": 50,
            "offset": 0,
            "csrf_token": self._cookies.get("__csrf", ""),
        })
        async with httpx.AsyncClient(
            headers=_HEADERS, cookies=self._cookies
        ) as http:
            resp = await http.post(
                f"{_BASE_URL}/weapi/user/playlist", data=payload
            )
            resp.raise_for_status()
            if not resp.content:
                return []
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

    async def _get_uid(self) -> str:
        payload = weapi_encrypt({"csrf_token": self._cookies.get("__csrf", "")})
        async with httpx.AsyncClient(
            headers=_HEADERS, cookies=self._cookies
        ) as http:
            resp = await http.post(
                f"{_BASE_URL}/weapi/nuser/account/get", data=payload
            )
            resp.raise_for_status()
            if not resp.content:
                return ""
            data = resp.json()
        return str(data.get("account", {}).get("id", ""))

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
