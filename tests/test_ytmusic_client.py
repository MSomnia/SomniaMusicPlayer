import json, pytest
from unittest.mock import MagicMock, patch
from core.models import Track, Artist


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


ARTIST_SEARCH_RESULT = [
    {
        "browseId": "UCVnWg1HM4tKcBbFAFpGfqCg",
        "artist": "Taylor Swift",
        "thumbnails": [
            {"url": "https://example.com/ts_small.jpg", "width": 100, "height": 100},
            {"url": "https://example.com/ts_large.jpg", "width": 576, "height": 576},
        ],
        "resultType": "artist",
    }
]

ARTIST_DATA = {
    "name": "Taylor Swift",
    "thumbnails": [
        {"url": "https://example.com/ts_large.jpg", "width": 576, "height": 576},
    ],
    "songs": {
        "results": [
            {
                "videoId": "abc123",
                "title": "Anti-Hero",
                "artists": [{"name": "Taylor Swift", "id": "UCVnWg1HM4tKcBbFAFpGfqCg"}],
                "album": {"name": "Midnights", "id": "alb001"},
                "thumbnails": [{"url": "https://example.com/midnights.jpg"}],
                "duration_seconds": 200,
            }
        ]
    },
}


async def test_ytmusic_search_artist():
    client = _make_client()
    with patch.object(client._ytm, "search", return_value=ARTIST_SEARCH_RESULT):
        artist = await client.search_artist("Taylor Swift")

    assert artist is not None
    assert isinstance(artist, Artist)
    assert artist.id == "UCVnWg1HM4tKcBbFAFpGfqCg"
    assert artist.name == "Taylor Swift"
    assert artist.image_url == "https://example.com/ts_large.jpg"
    assert artist.platform == "ytmusic"


async def test_ytmusic_search_artist_returns_none_on_empty():
    client = _make_client()
    with patch.object(client._ytm, "search", return_value=[]):
        artist = await client.search_artist("nonexistent_xyz")

    assert artist is None


async def test_ytmusic_get_artist_top_tracks():
    client = _make_client()
    with patch.object(client._ytm, "get_artist", return_value=ARTIST_DATA):
        tracks = await client.get_artist_top_tracks("UCVnWg1HM4tKcBbFAFpGfqCg")

    assert len(tracks) == 1
    assert tracks[0].title == "Anti-Hero"
    assert tracks[0].platform == "ytmusic"
