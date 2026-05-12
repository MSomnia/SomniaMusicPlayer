from __future__ import annotations
import logging
from core.models import LyricLine, LyricWord

logger = logging.getLogger(__name__)

_ENDPOINT = "https://spclient.wg.spotify.com/color-lyrics/v2/track/{track_id}"
_HEADERS = {
    "App-Platform": "WebPlayer",
    "Spotify-App-Version": "1.2.50.248",
}


class SpotifyLyrics:
    def __init__(self, http_client) -> None:
        self._http = http_client

    async def fetch(self, track_id: str, token: str) -> list[LyricLine]:
        url = _ENDPOINT.format(track_id=track_id)
        headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
        try:
            resp = await self._http.get(
                url,
                headers={**headers, "Accept": "application/json"},
                timeout=10.0,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            try:
                data = resp.json()
            except UnicodeDecodeError:
                logger.warning("Spotify lyrics response was not valid UTF-8 JSON")
                return []
            return self._parse(data)
        except Exception as exc:
            logger.warning("Spotify lyrics fetch failed: %s", exc)
            return []

    @staticmethod
    def _parse(data: dict) -> list[LyricLine]:
        lyrics = data.get("lyrics", {})
        lines_raw = lyrics.get("lines", [])
        sync_type = lyrics.get("syncType", "LINE_SYNCED")
        result = []

        for i, line in enumerate(lines_raw):
            start_ms = int(line.get("startTimeMs", 0))
            end_ms_raw = line.get("endTimeMs", "0")
            if end_ms_raw and int(end_ms_raw) > 0:
                end_ms = int(end_ms_raw)
            elif i + 1 < len(lines_raw):
                end_ms = int(lines_raw[i + 1].get("startTimeMs", start_ms + 5000))
            else:
                end_ms = start_ms + 5000

            text = line.get("words", "") or ""
            syllables = line.get("syllables", []) or []

            if syllables and sync_type == "WORD_SYNCED":
                words = [
                    LyricWord(
                        start_ms=int(s.get("startTimeMs", start_ms)),
                        end_ms=int(s.get("endTimeMs", end_ms)),
                        text=s.get("text", s.get("word", "")),
                    )
                    for s in syllables
                ]
            else:
                words = []

            result.append(LyricLine(start_ms=start_ms, end_ms=end_ms, text=text, words=words))

        return result
