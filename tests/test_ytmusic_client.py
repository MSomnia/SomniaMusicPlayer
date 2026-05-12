import json, pytest
from unittest.mock import MagicMock, patch
from core.models import Track


def _make_client():
    from platforms.ytmusic.client import YTMusicClient
    headers = {"Cookie": "SAPISID=x", "X-Goog-AuthUser": "0"}
    with patch("ytmusicapi.YTMusic.__init__", return_value=None):
        client = YTMusicClient(headers)
        client._ytm = MagicMock()
        return client


def _yt_song(video_id="abc123"):
    return {
        "videoId": video_id,
        "title": "Test Song",
        "artists": [{"name": "Test Artist", "id": "A1"}],
        "album": {"name": "Test Album", "id": "AL1"},
        "duration_seconds": 210,
        "thumbnails": [
            {"url": "http://img/small.jpg", "width": 60, "height": 60},
            {"url": "http://img/large.jpg", "width": 226, "height": 226},
        ],
    }


async def test_search_returns_tracks():
    client = _make_client()
    client._ytm.search.return_value = [_yt_song("abc")]

    tracks = await client.search("test query", limit=5)

    client._ytm.search.assert_called_once_with("test query", filter="songs", limit=5)
    assert len(tracks) == 1
    t = tracks[0]
    assert t.id == "abc"
    assert t.platform == "ytmusic"
    assert t.title == "Test Song"
    assert t.artist == "Test Artist"
    assert t.album == "Test Album"
    assert t.duration_ms == 210_000
    assert t.album_cover_url == "http://img/large.jpg"


async def test_search_empty_result():
    client = _make_client()
    client._ytm.search.return_value = []
    tracks = await client.search("nothing")
    assert tracks == []


async def test_search_missing_fields_handled():
    client = _make_client()
    minimal = {"videoId": "z", "title": "X"}
    client._ytm.search.return_value = [minimal]
    tracks = await client.search("x")
    assert tracks[0].artist == ""
    assert tracks[0].album == ""
    assert tracks[0].duration_ms == 0


async def test_is_authenticated():
    client = _make_client()
    assert await client.is_authenticated() is True


async def test_get_library_playlists_returns_list():
    client = _make_client()
    client._ytm.get_liked_songs.return_value = None  # no liked songs
    client._ytm.get_library_playlists.return_value = [
        {"playlistId": "PL1", "title": "My Mix",
         "thumbnails": [{"url": "http://t.jpg"}], "count": 12}
    ]
    playlists = await client.get_library_playlists()
    assert len(playlists) == 1
    assert playlists[0].id == "PL1"
    assert playlists[0].name == "My Mix"
    assert playlists[0].platform == "ytmusic"


async def test_get_library_playlists_includes_liked_songs():
    client = _make_client()
    client._ytm.get_liked_songs.return_value = {"trackCount": 42, "tracks": []}
    client._ytm.get_library_playlists.return_value = []
    playlists = await client.get_library_playlists()
    assert len(playlists) == 1
    assert playlists[0].id == "LM"
    assert playlists[0].name == "喜欢的歌曲"
    assert playlists[0].track_count == 42
