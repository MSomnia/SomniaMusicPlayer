from __future__ import annotations
import httpx
from core.models import LyricLine, Track
from platforms.netease.crypto import weapi_encrypt
from utils.lrc_parser import parse_lrc

_BASE_URL = "https://music.163.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
    "Content-Type": "application/x-www-form-urlencoded",
}


class NeteaseLyrics:
    def __init__(self, cookies: dict[str, str]) -> None:
        self._cookies = cookies

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        payload = weapi_encrypt({
            "id": int(track.id),
            "lv": 1,
            "kv": 1,
            "csrf_token": self._cookies.get("__csrf", ""),
        })
        async with httpx.AsyncClient(
            headers=_HEADERS, cookies=self._cookies
        ) as http:
            resp = await http.post(
                f"{_BASE_URL}/weapi/song/lyric/v1", data=payload
            )
            resp.raise_for_status()
            if not resp.content:
                return []
            data = resp.json()
        lrc_text = data.get("lrc", {}).get("lyric", "")
        if not lrc_text:
            return []
        return parse_lrc(lrc_text)
