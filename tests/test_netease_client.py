import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from platforms.netease.client import NeteaseClient
from core.models import LyricLine, Playlist, Track


@pytest.fixture
def client():
    return NeteaseClient(cookies={"MUSIC_U": "fake", "__csrf": "fake"})


SEARCH_RESPONSE = {
    "result": {
        "songs": [
            {
                "id": 123456,
                "name": "Test Song",
                "ar": [{"name": "Artist A"}, {"name": "Artist B"}],
                "al": {"name": "Test Album", "picUrl": "https://example.com/cover.jpg"},
                "dt": 240000,
            }
        ]
    },
    "code": 200,
}


def _make_track(tid="123456"):
    return Track(
        id=tid,
        platform="netease",
        title="T",
        artist="A",
        artists=["A"],
        album="Alb",
        album_cover_url="",
        duration_ms=1000,
    )


async def test_search_returns_tracks(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = SEARCH_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        tracks = await client.search("Test Song")

    assert len(tracks) == 1
    t = tracks[0]
    assert isinstance(t, Track)
    assert t.id == "123456"
    assert t.title == "Test Song"
    assert t.platform == "netease"
    assert t.artist == "Artist A"
    assert t.artists == ["Artist A", "Artist B"]
    assert t.album == "Test Album"
    assert t.album_cover_url == "https://example.com/cover.jpg"
    assert t.duration_ms == 240000


async def test_search_posts_to_cloudsearch_endpoint(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = SEARCH_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch(
        "platforms.netease.client.weapi_encrypt",
        return_value={"params": "encrypted", "encSecKey": "key"},
    ) as encrypt, patch(
        "httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)
    ) as post:
        await client.search("Test Song", limit=10)

    encrypt.assert_called_once_with(
        {"s": "Test Song", "type": 1, "limit": 10, "offset": 0}
    )
    post.assert_awaited_once_with(
        "https://music.163.com/weapi/cloudsearch/pc",
        data={"params": "encrypted", "encSecKey": "key"},
    )


STREAM_RESPONSE = {
    "data": [{"url": "https://cdn.example.com/audio.mp3", "code": 200}],
    "code": 200,
}


async def test_get_stream_url(client):
    track = _make_track()
    mock_resp = MagicMock()
    mock_resp.json.return_value = STREAM_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        url = await client.get_stream_url(track)

    assert url == "https://cdn.example.com/audio.mp3"


async def test_get_stream_url_posts_to_player_endpoint(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = STREAM_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch(
        "platforms.netease.client.weapi_encrypt",
        return_value={"params": "encrypted", "encSecKey": "key"},
    ) as encrypt, patch(
        "httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)
    ) as post:
        await client.get_stream_url(_make_track("987654"))

    encrypt.assert_called_once_with(
        {
            "ids": [987654],
            "level": "exhigh",
            "encodeType": "flac",
            "csrf_token": "fake",
        }
    )
    post.assert_awaited_once_with(
        "https://music.163.com/weapi/song/enhance/player/url/v1",
        data={"params": "encrypted", "encSecKey": "key"},
    )


async def test_get_stream_url_raises_when_url_missing(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": [{"url": None}], "code": 200}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        with pytest.raises(RuntimeError, match="No stream URL for track 123456"):
            await client.get_stream_url(_make_track())


async def test_get_lyrics_delegates_to_lyrics_client(client):
    lyric_lines = [LyricLine(start_ms=0, end_ms=1000, text="Hello")]

    with patch(
        "platforms.netease.lyrics.NeteaseLyrics.get_lyrics",
        new=AsyncMock(return_value=lyric_lines),
    ) as get_lyrics:
        result = await client.get_lyrics(_make_track())

    assert result == lyric_lines
    get_lyrics.assert_awaited_once()


PLAYLIST_RESPONSE = {
    "playlist": [
        {
            "id": 111,
            "name": "Daily Mix",
            "coverImgUrl": "https://example.com/playlist.jpg",
            "trackCount": 42,
        },
        {
            "id": 222,
            "name": "No Cover",
        },
    ],
    "code": 200,
}


async def test_get_library_playlists_returns_playlists(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = PLAYLIST_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        playlists = await client.get_library_playlists()

    assert len(playlists) == 2
    first = playlists[0]
    assert isinstance(first, Playlist)
    assert first.id == "111"
    assert first.platform == "netease"
    assert first.name == "Daily Mix"
    assert first.cover_url == "https://example.com/playlist.jpg"
    assert first.track_count == 42
    assert first.tracks == []

    second = playlists[1]
    assert second.id == "222"
    assert second.cover_url == ""
    assert second.track_count == 0


async def test_get_library_playlists_posts_to_user_playlist_endpoint(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = PLAYLIST_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch.object(
        client, "_get_uid", new=AsyncMock(return_value="99999")
    ), patch(
        "platforms.netease.client.weapi_encrypt",
        return_value={"params": "encrypted", "encSecKey": "key"},
    ) as encrypt, patch(
        "httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)
    ) as post:
        await client.get_library_playlists()

    encrypt.assert_called_once_with(
        {"uid": "99999", "limit": 50, "offset": 0, "csrf_token": "fake"}
    )
    post.assert_awaited_once_with(
        "https://music.163.com/weapi/user/playlist",
        data={"params": "encrypted", "encSecKey": "key"},
    )


async def test_search_empty_result(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": {"songs": []}, "code": 200}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        tracks = await client.search("nonexistent")
    assert tracks == []


async def test_is_authenticated_false_when_no_music_u(client):
    empty_client = NeteaseClient(cookies={})
    result = await empty_client.is_authenticated()
    assert result is False


async def test_is_authenticated_true_when_cookie_present(client):
    result = await client.is_authenticated()
    assert result is True
