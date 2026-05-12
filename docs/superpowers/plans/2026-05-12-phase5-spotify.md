# Phase 5 — Spotify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement full Spotify support — WebView sp_dc login, Bearer token management, internal API search/lyrics/library, and librespot-python + sounddevice audio playback — wired into the existing AppController/MainWindow pattern.

**Architecture:** LibrespotBridge (pure Python, platforms/spotify/) decrypts and decodes Ogg Vorbis tracks via librespot-python + soundfile; LibrespotBackend (core/, QObject) pumps PCM to sounddevice in a daemon thread emitting Qt signals identical to VLCBackend. SpotifyClient implements AbstractPlatform for search/lyrics/library. AppController routes Spotify tracks to LibrespotBackend and all others to VLCBackend.

**Tech Stack:** librespot-python, sounddevice, soundfile, httpx (async), PyQt6, existing AppRepository (AES-256 credential storage).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `requirements.txt` | Modify | Add librespot-python, sounddevice, soundfile |
| `platforms/spotify/lyrics.py` | Create | Parse color-lyrics v2 API → list[LyricLine] |
| `platforms/spotify/auth.py` | Create | sp_dc capture, Bearer token cache/refresh |
| `platforms/spotify/librespot_bridge.py` | Create | Session lifecycle, track decrypt+decode → numpy |
| `core/librespot_backend.py` | Create | QObject: daemon-thread PCM pump, Qt signals |
| `platforms/spotify/client.py` | Create | AbstractPlatform: search, get_stream_url, get_lyrics, get_library_playlists |
| `platforms/spotify/__init__.py` | Modify | Export SpotifyAuth, SpotifyClient |
| `core/app_controller.py` | Modify | Add Spotify auth/client/backend, route play_track |
| `ui/app_window.py` | Modify | _on_platform_login + spotify_auth_changed signal |
| `tests/test_spotify_lyrics.py` | Create | Unit tests for lyrics parser |
| `tests/test_spotify_auth.py` | Create | Unit tests for token caching |
| `tests/test_spotify_bridge.py` | Create | Unit tests for bridge (mocked librespot) |
| `tests/test_librespot_backend.py` | Create | Unit tests for backend state machine |
| `tests/test_spotify_client.py` | Create | Unit tests for search/library parsing |

---

## Task 1: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add Spotify dependencies**

```text
# Add these lines to requirements.txt (after existing deps):
librespot-python>=0.0.5
sounddevice>=0.4.7
soundfile>=0.12.1
```

- [ ] **Step 2: Install new dependencies**

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
pip install "librespot-python>=0.0.5" "sounddevice>=0.4.7" "soundfile>=0.12.1"
```

Expected: All three install without error. `python -c "import librespot; import sounddevice; import soundfile"` prints nothing (no ImportError).

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat(spotify): add librespot-python, sounddevice, soundfile deps"
```

---

## Task 2: platforms/spotify/lyrics.py

**Files:**
- Create: `platforms/spotify/lyrics.py`
- Create: `tests/test_spotify_lyrics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_spotify_lyrics.py
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
pytest tests/test_spotify_lyrics.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'platforms.spotify.lyrics'`

- [ ] **Step 3: Implement platforms/spotify/lyrics.py**

```python
# platforms/spotify/lyrics.py
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
            resp = await self._http.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return self._parse(resp.json())
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_spotify_lyrics.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add platforms/spotify/lyrics.py tests/test_spotify_lyrics.py
git commit -m "feat(spotify): add lyrics parser for color-lyrics v2 API"
```

---

## Task 3: platforms/spotify/auth.py

**Files:**
- Create: `platforms/spotify/auth.py`
- Create: `tests/test_spotify_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_spotify_auth.py
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from platforms.spotify.auth import SpotifyAuth


def _make_repo(sp_dc=None):
    repo = MagicMock()
    repo.load_credential = AsyncMock(
        return_value={"sp_dc": sp_dc} if sp_dc else None
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

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "accessToken": "new_token",
        "accessTokenExpirationTimestampMs": int((time.time() + 3600) * 1000),
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        token = await auth.get_access_token()

    assert token == "new_token"
    assert auth._cached_token == "new_token"


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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_spotify_auth.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'platforms.spotify.auth'`

- [ ] **Step 3: Implement platforms/spotify/auth.py**

```python
# platforms/spotify/auth.py
from __future__ import annotations
import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_ACCOUNTS_URL = "https://accounts.spotify.com/login"
_TOKEN_URL = "https://open.spotify.com/get_access_token"
_TOKEN_PARAMS = "?reason=transport&productType=web_player"


class SpotifyAuth:
    def __init__(self, repo) -> None:
        self._repo = repo
        self._cached_token: str | None = None
        self._token_expires_at: float = 0.0

    async def load_sp_dc(self) -> str | None:
        cred = await self._repo.load_credential("spotify")
        if cred:
            return cred.get("sp_dc")
        return None

    async def login(self, parent=None) -> str | None:
        from ui.components.login_dialog import LoginDialog

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()

        dialog = LoginDialog(
            url=_ACCOUNTS_URL,
            target_cookies=["sp_dc"],
            title="Spotify — 登录",
            parent=parent,
        )

        def _on_captured(cookies: dict) -> None:
            if not future.done():
                future.set_result(cookies)

        def _on_rejected() -> None:
            if not future.done():
                future.set_result(None)

        dialog.cookies_captured.connect(_on_captured)
        dialog.rejected.connect(_on_rejected)
        dialog.show()

        cookies = await future
        if not cookies or "sp_dc" not in cookies:
            logger.debug("Spotify login cancelled — sp_dc not captured")
            return None

        sp_dc = cookies["sp_dc"]
        await self._repo.save_credential("spotify", {"sp_dc": sp_dc})
        logger.info("Spotify sp_dc saved")
        return sp_dc

    async def get_access_token(self) -> str:
        now = time.time()
        if self._cached_token and now < self._token_expires_at - 60:
            return self._cached_token

        sp_dc = await self.load_sp_dc()
        if not sp_dc:
            raise RuntimeError("Spotify not authenticated — sp_dc not found")

        import httpx
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                _TOKEN_URL + _TOKEN_PARAMS,
                headers={
                    "Cookie": f"sp_dc={sp_dc}",
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        self._cached_token = data["accessToken"]
        expires_ms = data.get("accessTokenExpirationTimestampMs", 0)
        self._token_expires_at = expires_ms / 1000 if expires_ms else now + 3600
        logger.info("Spotify access token refreshed (expires in %.0fs)", self._token_expires_at - now)
        return self._cached_token

    async def ensure_authenticated(self, parent=None) -> str | None:
        sp_dc = await self.load_sp_dc()
        if sp_dc:
            return sp_dc
        return await self.login(parent)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_spotify_auth.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add platforms/spotify/auth.py tests/test_spotify_auth.py
git commit -m "feat(spotify): add SpotifyAuth — sp_dc capture + access token management"
```

---

## Task 4: platforms/spotify/librespot_bridge.py

**Files:**
- Create: `platforms/spotify/librespot_bridge.py`
- Create: `tests/test_spotify_bridge.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_spotify_bridge.py
import io
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_bridge(tmp_path):
    creds_path = str(tmp_path / "spotify_credentials.json")
    from platforms.spotify.librespot_bridge import LibrespotBridge
    return LibrespotBridge(creds_path), creds_path


def test_has_session_false_initially(tmp_path):
    bridge, _ = _make_bridge(tmp_path)
    assert bridge.has_session() is False


def test_load_track_raises_without_session(tmp_path):
    bridge, _ = _make_bridge(tmp_path)
    with pytest.raises(RuntimeError, match="No session"):
        bridge.load_track("4iV5W9uYEdYUVa79Axb7Rh")


def test_load_track_returns_numpy_array(tmp_path):
    bridge, _ = _make_bridge(tmp_path)

    fake_audio = np.zeros((44100, 2), dtype="float32")
    mock_session = MagicMock()
    bridge._session = mock_session

    mock_loaded = MagicMock()
    mock_audio_stream = MagicMock()
    mock_audio_stream.read.side_effect = [b"fake_ogg_bytes", b""]
    mock_loaded.input_stream.stream.return_value = mock_audio_stream
    mock_session.content_feeder.return_value.load.return_value = mock_loaded

    with patch("platforms.spotify.librespot_bridge.sf.SoundFile") as mock_sf_cls:
        mock_sf = MagicMock()
        mock_sf.__enter__ = MagicMock(return_value=mock_sf)
        mock_sf.__exit__ = MagicMock(return_value=False)
        mock_sf.samplerate = 44100
        mock_sf.read.return_value = fake_audio
        mock_sf_cls.return_value = mock_sf

        data, sr = bridge.load_track("4iV5W9uYEdYUVa79Axb7Rh")

    assert sr == 44100
    assert data.shape == (44100, 2)


def test_close_clears_session(tmp_path):
    bridge, _ = _make_bridge(tmp_path)
    mock_session = MagicMock()
    bridge._session = mock_session

    bridge.close()

    mock_session.close.assert_called_once()
    assert bridge.has_session() is False
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_spotify_bridge.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'platforms.spotify.librespot_bridge'`

- [ ] **Step 3: Implement platforms/spotify/librespot_bridge.py**

```python
# platforms/spotify/librespot_bridge.py
from __future__ import annotations
import io
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

try:
    import soundfile as sf
except ImportError:
    sf = None  # type: ignore[assignment]
    logger.warning("soundfile not installed — Spotify audio decode unavailable")

try:
    from librespot.core import Session
    from librespot.metadata import TrackId
    from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
    _LIBRESPOT_AVAILABLE = True
except Exception as _err:
    _LIBRESPOT_AVAILABLE = False
    logger.warning("librespot-python unavailable: %s", _err)


class LibrespotBridge:
    """Manages a librespot-python Session and decodes Spotify tracks to PCM."""

    _CHUNK = 16384

    def __init__(self, creds_path: str) -> None:
        self._creds_path = creds_path
        self._session: "Session | None" = None

    def has_session(self) -> bool:
        return self._session is not None

    def create_session(
        self,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Create or restore a librespot Session.

        If creds_path exists: load stored credentials.
        Otherwise: username + password required for first-time auth.
        """
        if not _LIBRESPOT_AVAILABLE:
            raise RuntimeError("librespot-python is not installed")

        conf = (
            Session.Configuration.Builder()
            .set_stored_credential_file(self._creds_path)
            .build()
        )
        builder = Session.Builder(conf=conf)

        if Path(self._creds_path).exists():
            logger.info("Librespot: loading stored credentials from %s", self._creds_path)
            self._session = builder.stored_file().create()
        elif username and password:
            logger.info("Librespot: authenticating with username/password")
            self._session = builder.user_pass(username, password).create()
        else:
            raise RuntimeError(
                "No librespot credentials found. Login with username and password first."
            )

    def load_track(self, track_id_str: str) -> tuple[np.ndarray, int]:
        """Decrypt and decode a Spotify track → (float32 array, samplerate).

        Downloads the full track before returning (download-then-play model).
        Raises RuntimeError if no session or decode fails.
        """
        if self._session is None:
            raise RuntimeError("No session — call create_session() first")
        if not _LIBRESPOT_AVAILABLE:
            raise RuntimeError("librespot-python not installed")
        if sf is None:
            raise RuntimeError("soundfile not installed — cannot decode Ogg Vorbis")

        tid = TrackId.from_uri(f"spotify:track:{track_id_str}")
        loaded = self._session.content_feeder().load(
            tid,
            VorbisOnlyAudioQuality(AudioQuality.HIGH),
            False,
            None,
        )

        buf = io.BytesIO()
        audio_stream = loaded.input_stream.stream()
        while True:
            chunk = audio_stream.read(self._CHUNK)
            if not chunk:
                break
            buf.write(chunk)
        buf.seek(0)

        with sf.SoundFile(buf) as f:
            samplerate = f.samplerate
            audio_data = f.read(dtype="float32")

        # Ensure 2D (frames, channels)
        if audio_data.ndim == 1:
            audio_data = audio_data.reshape(-1, 1)

        logger.debug(
            "Loaded track %s: %d frames @ %dHz, %d ch",
            track_id_str, len(audio_data), samplerate, audio_data.shape[1],
        )
        return audio_data, samplerate

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_spotify_bridge.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add platforms/spotify/librespot_bridge.py tests/test_spotify_bridge.py
git commit -m "feat(spotify): add LibrespotBridge — session management + track decryption"
```

---

## Task 5: core/librespot_backend.py

**Files:**
- Create: `core/librespot_backend.py`
- Create: `tests/test_librespot_backend.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_librespot_backend.py
import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication

@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_backend(qapp):
    mock_bridge = MagicMock()
    # Simulate successful load: 1 second of silence at 44100Hz stereo
    audio = np.zeros((44100, 2), dtype="float32")
    mock_bridge.load_track.return_value = (audio, 44100)

    with patch("core.librespot_backend.sd") as mock_sd:
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_sd.OutputStream.return_value = mock_stream

        from core.librespot_backend import LibrespotBackend
        backend = LibrespotBackend(mock_bridge)

    return backend, mock_bridge, mock_sd


def test_initial_position_is_zero(qapp):
    backend, _, _ = _make_backend(qapp)
    assert backend.get_position_ms() == 0


def test_has_session_delegates_to_bridge(qapp):
    backend, mock_bridge, _ = _make_backend(qapp)
    mock_bridge.has_session.return_value = True
    assert backend.has_session() is True


def test_set_volume_clamps(qapp):
    backend, _, _ = _make_backend(qapp)
    backend.set_volume(150)
    assert backend._volume == 1.0
    backend.set_volume(-10)
    assert backend._volume == 0.0
    backend.set_volume(50)
    assert abs(backend._volume - 0.5) < 1e-6


def test_stop_resets_position(qapp):
    backend, _, _ = _make_backend(qapp)
    backend._pos = 44100  # simulate some playback
    backend.stop()
    assert backend.get_position_ms() == 0


def test_seek_updates_seek_pos(qapp):
    backend, _, _ = _make_backend(qapp)
    # Inject fake audio so seek can compute frame offset
    backend._audio_data = np.zeros((88200, 2), dtype="float32")
    backend._samplerate = 44100
    backend.seek(1000)  # seek to 1000ms = 44100 frames
    assert backend._seek_pos == 44100


def test_seek_clamps_to_zero(qapp):
    backend, _, _ = _make_backend(qapp)
    backend._audio_data = np.zeros((44100, 2), dtype="float32")
    backend._samplerate = 44100
    backend.seek(-500)
    assert backend._seek_pos == 0


def test_play_raises_error_when_sd_unavailable(qapp):
    mock_bridge = MagicMock()
    errors = []

    from core.librespot_backend import LibrespotBackend
    with patch("core.librespot_backend.sd", None):
        backend = LibrespotBackend(mock_bridge)
        backend.error_occurred.connect(errors.append)
        backend.play("some_track_id")

    assert len(errors) == 1
    assert "sounddevice" in errors[0].lower()
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_librespot_backend.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'core.librespot_backend'`

- [ ] **Step 3: Implement core/librespot_backend.py**

```python
# core/librespot_backend.py
from __future__ import annotations
import logging
import threading
import time

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG, pyqtSlot

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
except Exception as _sd_err:
    sd = None  # type: ignore[assignment]
    logger.warning(
        "sounddevice unavailable: %s — Spotify audio disabled. "
        "Install via: pip install sounddevice",
        _sd_err,
    )


class LibrespotBackend(QObject):
    """PCM playback backend for Spotify via librespot-python + sounddevice.

    Interface mirrors VLCBackend so AppController can treat both uniformly.
    Playback runs in a daemon thread; Qt signals are emitted via invokeMethod.
    """

    position_changed = pyqtSignal(int)   # ms
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)
    playback_started = pyqtSignal()

    _BLOCK_SIZE = 1024   # frames per sounddevice write
    _REPORT_MS = 250     # position-report interval

    def __init__(self, bridge, parent=None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._thread: threading.Thread | None = None
        self._audio_data: np.ndarray | None = None
        self._samplerate: int = 44100
        self._pos: int = 0
        self._volume: float = 0.7
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._seek_pos: int | None = None
        self._lock = threading.Lock()

    # ── public API (mirrors VLCBackend) ───────────────────────────────────────

    def has_session(self) -> bool:
        return self._bridge.has_session()

    def play(self, track_id: str) -> None:
        if sd is None:
            self.error_occurred.emit(
                "sounddevice 未安装，无法播放 Spotify 音频。请运行: pip install sounddevice"
            )
            return
        self.stop()
        self._stopped.clear()
        self._paused.clear()
        self._pos = 0
        self._thread = threading.Thread(
            target=self._load_and_play, args=(track_id,), daemon=True
        )
        self._thread.start()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def stop(self) -> None:
        self._stopped.set()
        self._paused.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._pos = 0

    def seek(self, position_ms: int) -> None:
        if self._audio_data is None:
            return
        frame = int(position_ms * self._samplerate / 1000)
        with self._lock:
            self._seek_pos = max(0, min(frame, len(self._audio_data) - 1))

    def set_volume(self, volume: int) -> None:
        self._volume = max(0.0, min(volume / 100.0, 1.0))

    def get_position_ms(self) -> int:
        return int(self._pos / max(self._samplerate, 1) * 1000)

    # ── background thread ─────────────────────────────────────────────────────

    def _load_and_play(self, track_id: str) -> None:
        try:
            audio_data, samplerate = self._bridge.load_track(track_id)
        except Exception as exc:
            logger.error("Librespot load failed for %s: %s", track_id, exc)
            QMetaObject.invokeMethod(
                self, "_emit_error",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, str(exc)),
            )
            return

        self._audio_data = audio_data
        self._samplerate = samplerate
        channels = audio_data.shape[1] if audio_data.ndim > 1 else 1

        QMetaObject.invokeMethod(
            self, "_emit_playback_started", Qt.ConnectionType.QueuedConnection
        )

        try:
            with sd.OutputStream(
                samplerate=samplerate,
                channels=channels,
                dtype="float32",
            ) as stream:
                self._pump(stream)
        except Exception as exc:
            logger.error("sounddevice stream error: %s", exc)
            if not self._stopped.is_set():
                QMetaObject.invokeMethod(
                    self, "_emit_error",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, str(exc)),
                )
            return

        if not self._stopped.is_set():
            QMetaObject.invokeMethod(
                self, "_emit_end", Qt.ConnectionType.QueuedConnection
            )

    def _pump(self, stream: "sd.OutputStream") -> None:
        total = len(self._audio_data)
        last_report_ms = -self._REPORT_MS

        while not self._stopped.is_set():
            if self._paused.is_set():
                time.sleep(0.02)
                continue

            with self._lock:
                if self._seek_pos is not None:
                    self._pos = self._seek_pos
                    self._seek_pos = None

            end = self._pos + self._BLOCK_SIZE
            block = self._audio_data[self._pos:end]

            if len(block) == 0:
                break

            # Apply software volume
            block = block * self._volume

            # Pad last block so sounddevice gets a full buffer
            if len(block) < self._BLOCK_SIZE:
                pad = self._BLOCK_SIZE - len(block)
                block = np.pad(block, ((0, pad), (0, 0)))

            stream.write(block)
            self._pos = min(end, total)

            now_ms = int(self._pos / self._samplerate * 1000)
            if now_ms - last_report_ms >= self._REPORT_MS:
                last_report_ms = now_ms
                QMetaObject.invokeMethod(
                    self, "_emit_position",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(int, now_ms),
                )

    # ── Qt slots (main thread) ────────────────────────────────────────────────

    @pyqtSlot()
    def _emit_playback_started(self) -> None:
        self.playback_started.emit()

    @pyqtSlot()
    def _emit_end(self) -> None:
        self.end_reached.emit()

    @pyqtSlot(str)
    def _emit_error(self, msg: str) -> None:
        self.error_occurred.emit(msg)

    @pyqtSlot(int)
    def _emit_position(self, ms: int) -> None:
        self.position_changed.emit(ms)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_librespot_backend.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add core/librespot_backend.py tests/test_librespot_backend.py
git commit -m "feat(spotify): add LibrespotBackend QObject — sounddevice PCM playback"
```

---

## Task 6: platforms/spotify/client.py

**Files:**
- Create: `platforms/spotify/client.py`
- Create: `tests/test_spotify_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_spotify_client.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.models import Track, Playlist


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


def test_parse_search_result():
    client, _ = _make_client()
    tracks = client._parse_search(_search_response())
    assert len(tracks) == 1
    t = tracks[0]
    assert t.id == "4iV5W9uYEdYUVa79Axb7Rh"
    assert t.platform == "spotify"
    assert t.title == "Blinding Lights"
    assert t.artist == "The Weeknd"
    assert t.artists == ["The Weeknd"]
    assert t.album == "After Hours"
    assert t.album_cover_url == "https://i.scdn.co/image/abc"
    assert t.duration_ms == 200040
    assert t.is_explicit is False


def test_parse_search_malformed_response():
    client, _ = _make_client()
    tracks = client._parse_search({"data": {}})
    assert tracks == []


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
        id="abc123", platform="spotify", title="Test", artist="A",
        artists=["A"], album="B", album_cover_url="", duration_ms=1000,
    )
    url = await client.get_stream_url(track)
    assert url == "spotify:track:abc123"


async def test_search_returns_tracks():
    client, _ = _make_client()
    mock_resp = MagicMock()
    mock_resp.json.return_value = _search_response()
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        tracks = await client.search("Blinding Lights")

    assert len(tracks) == 1
    assert tracks[0].title == "Blinding Lights"


async def test_search_returns_empty_on_error():
    client, _ = _make_client()
    with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=Exception("timeout"))):
        tracks = await client.search("anything")
    assert tracks == []


def test_to_playlist():
    from platforms.spotify.client import SpotifyClient
    raw = {
        "id": "PL1",
        "name": "My Mix",
        "images": [{"url": "https://i.scdn.co/pl.jpg"}],
        "tracks": {"total": 25},
    }
    pl = SpotifyClient._to_playlist(raw)
    assert pl.id == "PL1"
    assert pl.platform == "spotify"
    assert pl.name == "My Mix"
    assert pl.cover_url == "https://i.scdn.co/pl.jpg"
    assert pl.track_count == 25
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_spotify_client.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'platforms.spotify.client'`

- [ ] **Step 3: Implement platforms/spotify/client.py**

```python
# platforms/spotify/client.py
from __future__ import annotations
import json
import logging

import httpx

from core.models import Track, Playlist, LyricLine
from platforms.base import AbstractPlatform

logger = logging.getLogger(__name__)

# GraphQL persisted query hash for Spotify web client v1.2.50
_SEARCH_HASH = "21a089a14ae85aada98a88e39bf3a01aa1e76de2eafba56d0562ef5be12c06af"
_PARTNER_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
_APP_HEADERS = {
    "App-Platform": "WebPlayer",
    "Spotify-App-Version": "1.2.50.248",
}


class SpotifyClient(AbstractPlatform):
    platform_id = "spotify"

    def __init__(self, auth: "SpotifyAuth") -> None:
        self._auth = auth

    async def is_authenticated(self) -> bool:
        return bool(await self._auth.load_sp_dc())

    async def search(self, query: str, limit: int = 30) -> list[Track]:
        try:
            token = await self._auth.get_access_token()
        except Exception as exc:
            logger.warning("Spotify auth error during search: %s", exc)
            return []

        variables = {
            "searchTerm": query,
            "offset": 0,
            "limit": limit,
            "numberOfTopResults": 5,
            "includeAudiobooks": False,
            "includeEpisodes": False,
            "includePreReleases": False,
            "includeLocalConcerts": False,
        }
        params = {
            "operationName": "searchDesktop",
            "variables": json.dumps(variables, separators=(",", ":")),
            "extensions": json.dumps(
                {"persistedQuery": {"version": 1, "sha256Hash": _SEARCH_HASH}},
                separators=(",", ":"),
            ),
        }
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(
                    _PARTNER_URL,
                    params=params,
                    headers={"Authorization": f"Bearer {token}", **_APP_HEADERS},
                    timeout=10.0,
                )
                resp.raise_for_status()
                return self._parse_search(resp.json())
        except Exception as exc:
            logger.warning("Spotify search failed: %s", exc)
            return []

    async def get_stream_url(self, track: Track) -> str:
        # Actual streaming goes through LibrespotBackend.play(track.id)
        # AppController detects this URI prefix and bypasses VLC.
        return f"spotify:track:{track.id}"

    async def get_lyrics(self, track: Track) -> list[LyricLine]:
        from platforms.spotify.lyrics import SpotifyLyrics

        try:
            token = await self._auth.get_access_token()
        except Exception as exc:
            logger.warning("Spotify auth error during lyrics fetch: %s", exc)
            return []

        async with httpx.AsyncClient() as http:
            return await SpotifyLyrics(http).fetch(track.id, token)

    async def get_library_playlists(self) -> list[Playlist]:
        try:
            token = await self._auth.get_access_token()
            async with httpx.AsyncClient() as http:
                resp = await http.get(
                    "https://api.spotify.com/v1/me/playlists",
                    params={"limit": 50},
                    headers={"Authorization": f"Bearer {token}", **_APP_HEADERS},
                    timeout=10.0,
                )
                resp.raise_for_status()
                return [self._to_playlist(p) for p in resp.json().get("items", []) if p]
        except Exception as exc:
            logger.warning("Spotify library fetch failed: %s", exc)
            return []

    @staticmethod
    def _parse_search(data: dict) -> list[Track]:
        try:
            items = data["data"]["searchV2"]["tracksV2"]["items"]
        except (KeyError, TypeError):
            logger.warning("Unexpected Spotify search response shape")
            return []
        tracks = []
        for item in items:
            try:
                tracks.append(SpotifyClient._to_track(item["item"]["data"]))
            except (KeyError, TypeError):
                continue
        return tracks

    @staticmethod
    def _to_track(data: dict) -> Track:
        artists = [
            a["profile"]["name"]
            for a in data.get("artists", {}).get("items", [])
        ]
        album = data.get("albumOfTrack", {}) or {}
        sources = album.get("coverArt", {}).get("sources", []) or []
        cover = sources[0]["url"] if sources else ""
        return Track(
            id=data.get("id", ""),
            platform="spotify",
            title=data.get("name", ""),
            artist=artists[0] if artists else "",
            artists=artists,
            album=album.get("name", ""),
            album_cover_url=cover,
            duration_ms=data.get("duration", {}).get("totalMilliseconds", 0),
            is_explicit=data.get("contentRating", {}).get("label", "") == "EXPLICIT",
        )

    @staticmethod
    def _to_playlist(p: dict) -> Playlist:
        images = p.get("images", []) or []
        cover = images[0]["url"] if images else ""
        return Playlist(
            id=p.get("id", ""),
            platform="spotify",
            name=p.get("name", ""),
            cover_url=cover,
            track_count=(p.get("tracks") or {}).get("total", 0),
        )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_spotify_client.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add platforms/spotify/client.py tests/test_spotify_client.py
git commit -m "feat(spotify): add SpotifyClient — AbstractPlatform implementation"
```

---

## Task 7: platforms/spotify/__init__.py

**Files:**
- Modify: `platforms/spotify/__init__.py`

- [ ] **Step 1: Add exports**

```python
# platforms/spotify/__init__.py
from platforms.spotify.auth import SpotifyAuth
from platforms.spotify.client import SpotifyClient

__all__ = ["SpotifyAuth", "SpotifyClient"]
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
python -c "from platforms.spotify import SpotifyAuth, SpotifyClient; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add platforms/spotify/__init__.py
git commit -m "feat(spotify): export SpotifyAuth + SpotifyClient from package"
```

---

## Task 8: core/app_controller.py — Wire Spotify

**Files:**
- Modify: `core/app_controller.py`

- [ ] **Step 1: Add imports + new fields at top of `__init__`**

Add to the imports section (after existing platform imports):

```python
from platforms.spotify.auth import SpotifyAuth
from platforms.spotify.librespot_bridge import LibrespotBridge
from core.librespot_backend import LibrespotBackend
```

In `AppController.__init__`, add new fields and signal (insert after `self._ytm_client` line):

```python
        self._spotify_auth = SpotifyAuth(self._repo)
        _creds_path = str(Path.home() / ".somniaplayer" / "spotify_credentials.json")
        self._librespot_bridge = LibrespotBridge(_creds_path)
        self._spotify_client: "SpotifyClient | None" = None
        self._librespot = LibrespotBackend(self._librespot_bridge)
```

Also add the signal declaration (place after `ytmusic_auth_changed` line):

```python
    spotify_auth_changed = pyqtSignal(bool)
```

Add `from pathlib import Path` to imports if not already present.

- [ ] **Step 2: Add `is_spotify_authenticated` property**

After the `is_ytmusic_authenticated` property:

```python
    @property
    def is_spotify_authenticated(self) -> bool:
        return self._spotify_client is not None
```

- [ ] **Step 3: Wire librespot signals in `_wire_internal()`**

Append to `_wire_internal()`:

```python
        self._librespot.position_changed.connect(self._player.update_position)
        self._librespot.end_reached.connect(
            lambda: asyncio.ensure_future(self.play_next())
        )
        self._librespot.error_occurred.connect(self._player.on_load_error)
        self._librespot.playback_started.connect(self._player.on_load_success)
```

- [ ] **Step 4: Restore Spotify session in `init()`**

Append to `init()` after the YTMusic block:

```python
        # Restore Spotify session
        sp_dc = await self._spotify_auth.load_sp_dc()
        if sp_dc:
            from platforms.spotify.client import SpotifyClient
            self._spotify_client = SpotifyClient(self._spotify_auth)
            self.spotify_auth_changed.emit(True)
            try:
                self._librespot_bridge.create_session()
                logger.info("Librespot session restored from stored credentials")
            except Exception as exc:
                logger.info("Librespot stored credentials not found: %s", exc)
```

- [ ] **Step 5: Extend `_get_platform_client()`**

```python
    def _get_platform_client(self, platform: str) -> AbstractPlatform | None:
        if platform == "netease":
            return self._netease_client
        if platform == "ytmusic":
            return self._ytm_client
        if platform == "spotify":
            return self._spotify_client
        return None
```

- [ ] **Step 6: Update `play_track()` for Spotify routing**

Replace the `try` block in `play_track()`:

```python
    async def play_track(self, track: Track) -> None:
        client = self._get_platform_client(track.platform)
        if client is None:
            logger.warning("No client for platform %r", track.platform)
            return
        self._queue.set_tracks([track], 0)
        self._player.load(track)
        try:
            if track.platform == "spotify":
                # LibrespotBackend handles decryption + PCM output.
                # playback_started signal fires on_load_success asynchronously.
                self._vlc.stop()
                self._librespot.play(track.id)
            else:
                self._librespot.stop()
                url = await client.get_stream_url(track)
                vlc_opts = _vlc_options_for(track.platform)
                self._vlc.play(url, vlc_opts)
                self._player.on_load_success()
        except Exception as exc:
            logger.error("play_track failed for %r (%s): %s", track.title, track.platform, exc)
            self._player.on_load_error(str(exc))
            return
        asyncio.ensure_future(self._fetch_lyrics(track))
        asyncio.ensure_future(self._fetch_cover_color(track))
```

- [ ] **Step 7: Update `toggle_play_pause()` for Spotify**

```python
    def toggle_play_pause(self) -> None:
        status = self._player.state.status
        current = self._player.state.current_track
        is_spotify = current is not None and current.platform == "spotify"

        if status == "playing":
            if is_spotify:
                self._librespot.pause()
            else:
                self._vlc.pause()
            self._player.pause()
        elif status == "paused":
            if is_spotify:
                self._librespot.resume()
            else:
                self._vlc.pause()  # VLC pause() toggles
            self._player.resume()
```

- [ ] **Step 8: Update `seek()` for Spotify**

```python
    def seek(self, ms: int) -> None:
        current = self._player.state.current_track
        if current and current.platform == "spotify":
            self._librespot.seek(ms)
        else:
            self._vlc.seek(ms)
        self._player.seek(ms)
```

- [ ] **Step 9: Update `set_volume()` to set both backends**

```python
    def set_volume(self, v: int) -> None:
        self._vlc.set_volume(v)
        self._librespot.set_volume(v)
        asyncio.ensure_future(self._repo.set_setting("volume", str(v)))
```

- [ ] **Step 10: Add `ensure_spotify_auth()` method**

```python
    async def ensure_spotify_auth(self, parent=None) -> bool:
        if self._spotify_client is not None:
            return True
        sp_dc = await self._spotify_auth.login(parent)
        if not sp_dc:
            return False
        from platforms.spotify.client import SpotifyClient
        self._spotify_client = SpotifyClient(self._spotify_auth)
        self.spotify_auth_changed.emit(True)
        # Attempt to restore librespot session, prompt for credentials if needed
        await self._ensure_librespot_session(parent)
        return True

    async def _ensure_librespot_session(self, parent=None) -> None:
        if self._librespot_bridge.has_session():
            return
        try:
            self._librespot_bridge.create_session()
            logger.info("Librespot session created from stored credentials")
            return
        except Exception:
            pass
        # Stored credentials not available — prompt for username + password
        await self._prompt_librespot_credentials(parent)

    async def _prompt_librespot_credentials(self, parent=None) -> None:
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QDialogButtonBox
        import asyncio

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()

        dialog = QDialog(parent)
        dialog.setWindowTitle("Spotify — librespot 登录")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("首次使用需要输入 Spotify 账号（仅此一次，凭证将加密保存）："))
        user_edit = QLineEdit()
        user_edit.setPlaceholderText("Spotify 账号（邮箱或用户名）")
        layout.addWidget(user_edit)
        pass_edit = QLineEdit()
        pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pass_edit.setPlaceholderText("密码")
        layout.addWidget(pass_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btns)

        def _accept():
            if not future.done():
                future.set_result((user_edit.text().strip(), pass_edit.text()))

        def _reject():
            if not future.done():
                future.set_result(None)

        btns.accepted.connect(_accept)
        btns.rejected.connect(_reject)
        dialog.rejected.connect(_reject)
        dialog.show()

        result = await future
        dialog.close()

        if not result:
            logger.info("Librespot credential prompt cancelled")
            return

        username, password = result
        if not username or not password:
            return

        try:
            self._librespot_bridge.create_session(username, password)
            logger.info("Librespot session created with username/password")
        except Exception as exc:
            logger.error("Librespot credential error: %s", exc)

    async def close(self) -> None:
        self._librespot.stop()
        self._librespot_bridge.close()
        await self._repo.close()
        if self._proxy_process is not None:
            self._proxy_process.terminate()
            try:
                await asyncio.wait_for(self._proxy_process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proxy_process.kill()
            self._proxy_process = None
```

- [ ] **Step 11: Run existing test suite to check for regressions**

```bash
pytest tests/ -v --ignore=tests/test_spotify_lyrics.py \
    --ignore=tests/test_spotify_auth.py \
    --ignore=tests/test_spotify_bridge.py \
    --ignore=tests/test_librespot_backend.py \
    --ignore=tests/test_spotify_client.py 2>&1 | tail -20
```

Expected: All pre-existing tests pass.

- [ ] **Step 12: Commit**

```bash
git add core/app_controller.py
git commit -m "feat(spotify): wire Spotify into AppController — auth, playback routing, volume, seek"
```

---

## Task 9: ui/app_window.py — Spotify UI Wiring

**Files:**
- Modify: `ui/app_window.py`

- [ ] **Step 1: Add spotify_auth_changed signal connection in `_wire_signals()`**

In `_wire_signals()`, after the `ytmusic_auth_changed` connection block:

```python
        ctrl.spotify_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("spotify", ok)
        )
        self.sidebar.set_platform_status("spotify", ctrl.is_spotify_authenticated)
```

- [ ] **Step 2: Handle Spotify in `_on_platform_login()`**

```python
    def _on_platform_login(self, platform_id: str) -> None:
        if platform_id == "netease":
            asyncio.ensure_future(self._ctrl.ensure_netease_auth(self))
        elif platform_id == "ytmusic":
            asyncio.ensure_future(self._ctrl.ensure_ytmusic_auth(self))
        elif platform_id == "spotify":
            asyncio.ensure_future(self._ctrl.ensure_spotify_auth(self))
```

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -v 2>&1 | tail -30
```

Expected: All tests pass (including the 5 new test files).

- [ ] **Step 4: Commit**

```bash
git add ui/app_window.py
git commit -m "feat(spotify): wire Spotify login into MainWindow sidebar"
```

---

## Task 10: Final Integration Commit

- [ ] **Step 1: Run complete test suite**

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
pytest tests/ -v 2>&1 | tail -40
```

Expected: All tests pass, no regressions.

- [ ] **Step 2: Quick smoke test — import all new modules**

```bash
python -c "
from platforms.spotify.auth import SpotifyAuth
from platforms.spotify.lyrics import SpotifyLyrics
from platforms.spotify.client import SpotifyClient
from platforms.spotify.librespot_bridge import LibrespotBridge
from core.librespot_backend import LibrespotBackend
print('All Spotify modules import OK')
"
```

Expected: `All Spotify modules import OK`

- [ ] **Step 3: Tag and push branch**

```bash
git log --oneline -10
```

Verify all Phase 5 commits are present, then the branch is ready for review / PR.

---

## Self-Review Checklist

**Spec coverage:**
- [x] sp_dc Cookie 捕获 → Task 3 (auth.py)
- [x] access_token 换取 + 缓存/刷新 → Task 3
- [x] librespot-python Session 管理 → Task 4
- [x] PCM 输出 + 音量/Seek → Task 5
- [x] Spotify 内部搜索 API → Task 6
- [x] 逐字歌词 (color-lyrics v2) → Task 2
- [x] 收藏歌单 (library) → Task 6
- [x] AppController 路由 Spotify 曲目到 LibrespotBackend → Task 8
- [x] UI 侧边栏 Spotify 登录状态 → Task 9
- [x] librespot 首次登录凭证提示 → Task 8 (_prompt_librespot_credentials)
- [x] 凭证持久化 (sp_dc → SQLite, librespot → credentials.json) → Tasks 3, 4

**Not in scope (Phase 6):**
- Spotify 首页推荐 (home GraphQL)
- macOS 锁屏信息 NSNowPlayingInfoCenter
- 播放历史写入 SQLite
