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
