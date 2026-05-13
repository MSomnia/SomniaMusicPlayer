import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from platforms.netease.proxy_client import NeteaseProxyClient
from core.models import Artist, Track


@pytest.fixture
def client():
    return NeteaseProxyClient(
        cookies={"MUSIC_U": "fake", "__csrf": "fake"},
        proxy_url="http://localhost:3000",
    )


ARTIST_SEARCH_RESPONSE = {
    "result": {
        "artists": [
            {"id": 6452, "name": "周杰伦", "picUrl": "https://example.com/jay.jpg"}
        ]
    },
    "code": 200,
}

ARTIST_SONGS_RESPONSE = {
    "hotSongs": [
        {
            "id": 186001,
            "name": "青花瓷",
            "ar": [{"name": "周杰伦"}],
            "al": {"name": "我很忙", "picUrl": "https://example.com/album.jpg"},
            "dt": 237000,
        }
    ]
}


async def test_search_artist_returns_artist(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = ARTIST_SEARCH_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        artist = await client.search_artist("周杰伦")

    assert artist is not None
    assert isinstance(artist, Artist)
    assert artist.id == "6452"
    assert artist.name == "周杰伦"
    assert artist.image_url == "https://example.com/jay.jpg"
    assert artist.platform == "netease"


async def test_search_artist_returns_none_on_empty(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": {"artists": []}, "code": 200}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        artist = await client.search_artist("nonexistent")

    assert artist is None


async def test_get_artist_top_tracks(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = ARTIST_SONGS_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        tracks = await client.get_artist_top_tracks("6452")

    assert len(tracks) == 1
    assert tracks[0].title == "青花瓷"
    assert tracks[0].platform == "netease"
