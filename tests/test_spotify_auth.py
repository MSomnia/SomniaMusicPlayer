import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from platforms.spotify.auth import SpotifyAuth


def _make_repo(sp_dc=None):
    repo = MagicMock()
    repo.load_credential = AsyncMock(
        return_value={"sp_dc": sp_dc, "sp_key": "test_sp_key"} if sp_dc else None
    )
    repo.save_credential = AsyncMock()
    return repo


async def test_load_sp_dc_returns_none_when_missing():
    repo = _make_repo(sp_dc=None)
    auth = SpotifyAuth(repo)
    result = await auth.load_sp_dc()
    assert result is None


async def test_load_sp_dc_returns_value_when_present():
    repo = _make_repo(sp_dc="abc123")
    auth = SpotifyAuth(repo)
    result = await auth.load_sp_dc()
    assert result == "abc123"


async def test_get_access_token_uses_cache():
    repo = _make_repo(sp_dc="test_sp_dc")
    auth = SpotifyAuth(repo)
    auth._cached_token = "cached_token"
    auth._token_expires_at = time.time() + 3600

    token = await auth.get_access_token()
    assert token == "cached_token"


async def test_get_access_token_fetches_when_expired():
    repo = _make_repo(sp_dc="test_sp_dc")
    auth = SpotifyAuth(repo)
    auth._cached_token = "old_token"
    auth._token_expires_at = time.time() - 1  # expired

    mock_time_resp = MagicMock()
    mock_time_resp.json.return_value = {"serverTime": 1_700_000_000}
    mock_time_resp.raise_for_status = MagicMock()

    mock_token_resp = MagicMock()
    mock_token_resp.json.return_value = {
        "accessToken": "new_token",
        "accessTokenExpirationTimestampMs": int((time.time() + 3600) * 1000),
    }
    mock_token_resp.raise_for_status = MagicMock()
    mock_home_resp = MagicMock()
    mock_home_resp.text = '<script src="https://open.spotifycdn.com/cdn/build/web-player/web-player.abc.js"></script>'
    mock_home_resp.raise_for_status = MagicMock()
    mock_js_resp = MagicMock()
    mock_js_resp.text = "let e4=[{secret:'abc',version:61}];var te=r(1);"
    mock_js_resp.raise_for_status = MagicMock()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=[mock_time_resp, mock_home_resp, mock_js_resp, mock_token_resp]),
    ):
        token = await auth.get_access_token()

    assert token == "new_token"
    assert auth._cached_token == "new_token"


async def test_get_access_token_falls_back_when_server_time_missing():
    repo = _make_repo(sp_dc="test_sp_dc")
    auth = SpotifyAuth(repo)

    mock_time_resp = MagicMock()
    mock_time_resp.raise_for_status.side_effect = RuntimeError("404")

    mock_token_resp = MagicMock()
    mock_token_resp.json.return_value = {
        "accessToken": "new_token",
        "accessTokenExpirationTimestampMs": int((time.time() + 3600) * 1000),
    }
    mock_token_resp.raise_for_status = MagicMock()
    mock_home_resp = MagicMock()
    mock_home_resp.text = '<script src="https://open.spotifycdn.com/cdn/build/web-player/web-player.abc.js"></script>'
    mock_home_resp.raise_for_status = MagicMock()
    mock_js_resp = MagicMock()
    mock_js_resp.text = "let e4=[{secret:'abc',version:61}];var te=r(1);"
    mock_js_resp.raise_for_status = MagicMock()

    with patch(
        "httpx.AsyncClient.get",
        new=AsyncMock(side_effect=[mock_time_resp, mock_home_resp, mock_js_resp, mock_token_resp]),
    ):
        token = await auth.get_access_token()

    assert token == "new_token"


def test_generate_totp_is_six_digits():
    auth = SpotifyAuth(_make_repo(sp_dc="test_sp_dc"))
    value = auth._generate_totp(1_700_000_000)
    assert len(value) == 6
    assert value.isdigit()


def test_extract_totp_config_from_web_player_bundle():
    source = """his.period=s}}var e8=r(1158);let e4=[
        {secret:',7/*F("rLJ2oxaKL^f+E1xvP@N',version:61},
        {secret:'old',version:60}
    ];var te=r(84686).Buffer;"""
    secret, version = SpotifyAuth._extract_totp_config(source)
    assert version == 61
    assert isinstance(secret, bytes)
    assert secret


async def test_get_access_token_raises_without_sp_dc():
    repo = _make_repo(sp_dc=None)
    auth = SpotifyAuth(repo)

    with pytest.raises(RuntimeError, match="not authenticated"):
        await auth.get_access_token()


async def test_ensure_authenticated_returns_existing():
    repo = _make_repo(sp_dc="existing")
    auth = SpotifyAuth(repo)
    result = await auth.ensure_authenticated()
    assert result == "existing"
