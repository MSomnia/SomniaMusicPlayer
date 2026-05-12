import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from platforms.ytmusic.lyrics import LRCLibClient
from core.models import Track


def _track(title="Hello", artist="Adele"):
    return Track(
        id="dQw4w9WgXcQ", platform="ytmusic",
        title=title, artist=artist, artists=[artist],
        album="Album", album_cover_url="", duration_ms=210000,
    )


async def test_get_lyrics_returns_synced_lines():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"syncedLyrics": "[00:01.00]Hello\n[00:03.00]World\n", "plainLyrics": "Hello\nWorld"}
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert len(lines) == 2
    assert lines[0].text == "Hello"
    assert lines[0].start_ms == 1000
    assert lines[1].text == "World"
    assert lines[1].start_ms == 3000


async def test_get_lyrics_empty_response_returns_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert lines == []


async def test_get_lyrics_no_synced_falls_back_to_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"syncedLyrics": None, "plainLyrics": "Hello"}]
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert lines == []


async def test_get_lyrics_http_error_returns_empty():
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=Exception("timeout"))):
        client = LRCLibClient()
        lines = await client.get_lyrics(_track())

    assert lines == []
