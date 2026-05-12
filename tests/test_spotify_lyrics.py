import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from platforms.spotify.lyrics import SpotifyLyrics
from core.models import LyricLine, LyricWord


_LINE_SYNCED_RESPONSE = {
    "lyrics": {
        "syncType": "LINE_SYNCED",
        "lines": [
            {"startTimeMs": "1000", "words": "Hello world", "syllables": [], "endTimeMs": "0"},
            {"startTimeMs": "5000", "words": "Second line", "syllables": [], "endTimeMs": "9000"},
        ],
    }
}

_WORD_SYNCED_RESPONSE = {
    "lyrics": {
        "syncType": "WORD_SYNCED",
        "lines": [
            {
                "startTimeMs": "1000",
                "words": "Hello world",
                "syllables": [
                    {"startTimeMs": "1000", "endTimeMs": "1500", "text": "Hello"},
                    {"startTimeMs": "2000", "endTimeMs": "2500", "text": "world"},
                ],
                "endTimeMs": "3000",
            }
        ],
    }
}


def test_parse_line_synced():
    lines = SpotifyLyrics._parse(_LINE_SYNCED_RESPONSE)
    assert len(lines) == 2
    assert lines[0].start_ms == 1000
    assert lines[0].text == "Hello world"
    assert lines[0].words == []
    # end_ms from next line's startTimeMs
    assert lines[0].end_ms == 5000
    # last line: endTimeMs is 9000
    assert lines[1].end_ms == 9000


def test_parse_word_synced():
    lines = SpotifyLyrics._parse(_WORD_SYNCED_RESPONSE)
    assert len(lines) == 1
    assert lines[0].text == "Hello world"
    assert len(lines[0].words) == 2
    assert lines[0].words[0].text == "Hello"
    assert lines[0].words[0].start_ms == 1000
    assert lines[0].words[1].text == "world"
    assert lines[0].words[1].end_ms == 2500


def test_parse_empty_response():
    lines = SpotifyLyrics._parse({})
    assert lines == []


def test_parse_last_line_fallback_end_ms():
    data = {
        "lyrics": {
            "syncType": "LINE_SYNCED",
            "lines": [{"startTimeMs": "3000", "words": "Only line", "syllables": [], "endTimeMs": "0"}],
        }
    }
    lines = SpotifyLyrics._parse(data)
    assert lines[0].end_ms == 8000  # 3000 + 5000 fallback


async def test_fetch_returns_lines_on_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _LINE_SYNCED_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)

    lyrics = SpotifyLyrics(mock_http)
    lines = await lyrics.fetch("TRACK123", "tok_abc")

    assert len(lines) == 2
    mock_http.get.assert_called_once()
    call_kwargs = mock_http.get.call_args
    assert "TRACK123" in call_kwargs[0][0]
    assert "Bearer tok_abc" in call_kwargs[1]["headers"]["Authorization"]


async def test_fetch_returns_empty_on_404():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)

    lyrics = SpotifyLyrics(mock_http)
    lines = await lyrics.fetch("TRACK123", "tok")
    assert lines == []


async def test_fetch_returns_empty_on_error():
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=Exception("timeout"))

    lyrics = SpotifyLyrics(mock_http)
    lines = await lyrics.fetch("TRACK123", "tok")
    assert lines == []
