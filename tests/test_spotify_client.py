from unittest.mock import AsyncMock, MagicMock, patch

import base64
import json
import httpx
from core.models import Track


def _make_client():
    from platforms.spotify.auth import SpotifyAuth
    from platforms.spotify.client import SpotifyClient

    mock_auth = MagicMock(spec=SpotifyAuth)
    mock_auth.get_access_token = AsyncMock(return_value="test_token")
    mock_auth.load_sp_dc = AsyncMock(return_value="test_sp_dc")
    return SpotifyClient(mock_auth), mock_auth


def _search_response(track_id="4iV5W9uYEdYUVa79Axb7Rh"):
    return {
        "data": {
            "searchV2": {
                "tracksV2": {
                    "items": [
                        {
                            "item": {
                                "data": {
                                    "id": track_id,
                                    "name": "Blinding Lights",
                                    "artists": {
                                        "items": [{"profile": {"name": "The Weeknd"}}]
                                    },
                                    "albumOfTrack": {
                                        "name": "After Hours",
                                        "coverArt": {
                                            "sources": [{"url": "https://i.scdn.co/image/abc"}]
                                        },
                                    },
                                    "duration": {"totalMilliseconds": 200040},
                                    "contentRating": {"label": "NONE"},
                                }
                            }
                        }
                    ]
                }
            }
        }
    }


def _webapi_search_response(track_id="4iV5W9uYEdYUVa79Axb7Rh"):
    return {
        "tracks": {
            "items": [
                {
                    "id": track_id,
                    "name": "Blinding Lights",
                    "artists": [{"name": "The Weeknd"}],
                    "album": {
                        "name": "After Hours",
                        "images": [{"url": "https://i.scdn.co/image/abc"}],
                    },
                    "duration_ms": 200040,
                    "explicit": False,
                }
            ]
        }
    }


def _suggestions_response(track_id="4iV5W9uYEdYUVa79Axb7Rh"):
    return {
        "data": {
            "searchV2": {
                "topResultsV2": {
                    "itemsV2": [
                        {
                            "item": {
                                "__typename": "TrackResponseWrapper",
                                "data": {
                                    "id": track_id,
                                    "uri": f"spotify:track:{track_id}",
                                    "name": "Blinding Lights",
                                    "artists": {
                                        "items": [{"profile": {"name": "The Weeknd"}}]
                                    },
                                    "albumOfTrack": {
                                        "name": "After Hours",
                                        "coverArt": {
                                            "sources": [{"url": "https://i.scdn.co/image/abc"}]
                                        },
                                    },
                                    "duration": {"totalMilliseconds": 200040},
                                    "contentRating": {"label": "NONE"},
                                },
                            }
                        }
                    ]
                }
            }
        }
    }


def test_parse_search_result():
    client, _ = _make_client()
    tracks = client._parse_search(_search_response())
    assert len(tracks) == 1
    track = tracks[0]
    assert track.id == "4iV5W9uYEdYUVa79Axb7Rh"
    assert track.platform == "spotify"
    assert track.title == "Blinding Lights"
    assert track.artist == "The Weeknd"
    assert track.artists == ["The Weeknd"]
    assert track.album == "After Hours"
    assert track.album_cover_url == "https://i.scdn.co/image/abc"
    assert track.duration_ms == 200040
    assert track.is_explicit is False


def test_parse_search_malformed_response():
    client, _ = _make_client()
    assert client._parse_search({"data": {}}) == []


def test_parse_search_missing_optional_fields():
    client, _ = _make_client()
    minimal_resp = {
        "data": {
            "searchV2": {
                "tracksV2": {
                    "items": [{"item": {"data": {"id": "x", "name": "X"}}}]
                }
            }
        }
    }
    tracks = client._parse_search(minimal_resp)
    assert len(tracks) == 1
    assert tracks[0].artist == ""
    assert tracks[0].album == ""
    assert tracks[0].duration_ms == 0


def test_parse_webapi_search_result():
    client, _ = _make_client()
    tracks = client._parse_webapi_search(_webapi_search_response())
    assert len(tracks) == 1
    track = tracks[0]
    assert track.id == "4iV5W9uYEdYUVa79Axb7Rh"
    assert track.platform == "spotify"
    assert track.title == "Blinding Lights"
    assert track.artist == "The Weeknd"
    assert track.artists == ["The Weeknd"]
    assert track.album == "After Hours"
    assert track.album_cover_url == "https://i.scdn.co/image/abc"
    assert track.duration_ms == 200040
    assert track.is_explicit is False


def test_parse_search_suggestions_result():
    client, _ = _make_client()
    tracks = client._parse_search_suggestions(_suggestions_response())
    assert len(tracks) == 1
    track = tracks[0]
    assert track.id == "4iV5W9uYEdYUVa79Axb7Rh"
    assert track.title == "Blinding Lights"
    assert track.artist == "The Weeknd"
    assert track.album == "After Hours"
    assert track.duration_ms == 200040


async def test_is_authenticated_true_with_sp_dc():
    client, _ = _make_client()
    assert await client.is_authenticated() is True


async def test_is_authenticated_false_without_sp_dc():
    client, mock_auth = _make_client()
    mock_auth.load_sp_dc = AsyncMock(return_value=None)
    assert await client.is_authenticated() is False


async def test_get_stream_url_returns_spotify_uri():
    client, _ = _make_client()
    track = Track(
        id="abc123",
        platform="spotify",
        title="Test",
        artist="A",
        artists=["A"],
        album="B",
        album_cover_url="",
        duration_ms=1000,
    )
    assert await client.get_stream_url(track) == "spotify:track:abc123"


async def test_search_returns_tracks():
    client, _ = _make_client()
    client._client_token = "client_token"
    mock_resp = MagicMock()
    mock_resp.json.return_value = _suggestions_response()
    mock_resp.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_resp)
    with patch("httpx.AsyncClient.post", new=mock_post):
        tracks = await client.search("Blinding Lights")

    assert len(tracks) == 1
    assert tracks[0].title == "Blinding Lights"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["operationName"] == "searchSuggestions"
    assert payload["variables"]["query"] == "Blinding Lights"


async def test_search_returns_empty_on_error():
    client, _ = _make_client()
    client._client_token = "client_token"
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=Exception("timeout"))):
        tracks = await client.search("anything")
    assert tracks == []


async def test_search_handles_rate_limit():
    client, _ = _make_client()
    client._client_token = "client_token"
    request = httpx.Request("GET", "https://api.spotify.com/v1/search")
    response = httpx.Response(429, headers={"Retry-After": "7"}, request=request)
    error = httpx.HTTPStatusError("rate limited", request=request, response=response)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=error)), \
         patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        tracks = await client.search("anything")

    assert tracks == []
    assert client._rate_limited_until > 0
    mock_sleep.assert_awaited_once_with(2)


async def test_search_uses_cache_for_same_query():
    client, _ = _make_client()
    client._client_token = "client_token"
    mock_resp = MagicMock()
    mock_resp.json.return_value = _webapi_search_response()
    mock_resp.raise_for_status = MagicMock()

    mock_post = AsyncMock(return_value=mock_resp)
    with patch("httpx.AsyncClient.post", new=mock_post):
        first = await client.search("Blinding Lights")
        second = await client.search("blinding lights")

    assert first == second
    mock_post.assert_awaited_once()


async def test_get_client_token_parses_response():
    client, _ = _make_client()
    client._client_version = "1.2.90.356.gc7ecdb13"
    mock_http = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"granted_token": {"token": "ctok"}}
    mock_resp.raise_for_status = MagicMock()
    mock_http.post = AsyncMock(return_value=mock_resp)

    token = await client._get_client_token(mock_http)

    assert token == "ctok"
    assert mock_http.post.call_args.args[0] == "https://clienttoken.spotify.com/v1/clienttoken"


async def test_get_client_version_from_app_server_config():
    encoded = base64.b64encode(
        json.dumps({"clientVersion": "1.2.90.356.gc7ecdb13"}).encode("utf-8")
    ).decode("ascii")
    mock_http = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = f'<script id="appServerConfig" type="text/plain">{encoded}</script>'
    mock_resp.raise_for_status = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    client, _ = _make_client()

    version = await client._get_client_version(mock_http)

    assert version == "1.2.90.356.gc7ecdb13"


async def test_get_library_playlists_returns_playlists():
    from platforms.spotify.client import SpotifyClient

    # _parse_library_v3 is a static method — test it directly without HTTP mocking
    raw = {
        "data": {
            "me": {
                "libraryV3": {
                    "items": [
                        {
                            "item": {
                                "data": {
                                    "__typename": "Playlist",
                                    "uri": "spotify:playlist:PL1",
                                    "name": "My Mix",
                                    "images": {"items": [{"sources": [{"url": "https://i.scdn.co/pl.jpg"}]}]},
                                    "tracks": {"totalCount": 25},
                                }
                            }
                        }
                    ]
                }
            }
        }
    }
    playlists = SpotifyClient._parse_library_v3(raw)

    assert len(playlists) == 1
    assert playlists[0].id == "PL1"
    assert playlists[0].platform == "spotify"
    assert playlists[0].name == "My Mix"
    assert playlists[0].track_count == 25


def test_to_playlist():
    from platforms.spotify.client import SpotifyClient

    playlist = SpotifyClient._to_playlist({
        "id": "PL1",
        "name": "My Mix",
        "images": [{"url": "https://i.scdn.co/pl.jpg"}],
        "tracks": {"total": 25},
    })

    assert playlist.id == "PL1"
    assert playlist.platform == "spotify"
    assert playlist.name == "My Mix"
    assert playlist.cover_url == "https://i.scdn.co/pl.jpg"
    assert playlist.track_count == 25
