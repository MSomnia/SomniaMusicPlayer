# SomniaMusicPlayer Phase 2 — 网易云音乐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement NetEase Cloud Music (网易云) integration including: weapi/eapi encryption, WebView login + Cookie capture, search, audio stream URL retrieval + VLC playback, and lyrics fetch/parse. Wire all into a working NeteaseClient that implements AbstractPlatform.

**Architecture:**
- `platforms/netease/crypto.py` — Pure-Python weapi/eapi encryption (pycryptodome)
- `platforms/netease/auth.py` — Cookie capture using QWebEngineView CookieStore
- `platforms/netease/client.py` — httpx async API client (search, stream URL, lyrics URL)
- `platforms/netease/lyrics.py` — Lyrics API + LRC/TTML parse delegation
- `utils/lrc_parser.py` — LRC timestamp line parser → `list[LyricLine]`
- `db/repository.py` (extend) — AES-256 encrypted credential CRUD
- `ui/components/login_dialog.py` — QDialog wrapping QWebEngineView
- `core/vlc_backend.py` — python-vlc bridge connected to UnifiedPlayer

**Tech notes:**
- weapi: AES-128-CBC double-pass + RSA public-key padding (no padding — raw modpow via pycryptodome)
- Netease RSA public key modulus hardcoded (known public value)
- LRC: `[mm:ss.xxx]` line prefix regex
- Credential encryption key: PBKDF2-HMAC-SHA256 from a machine-stable seed (app name + platform)
- VLC events emitted on a background thread; must marshal back to Qt main thread via `QMetaObject.invokeMethod`

---

## Task 1: netease/crypto.py — Encryption

**Files:**
- Create: `platforms/netease/crypto.py`
- Create: `tests/test_netease_crypto.py`

### Step 1: Write failing tests

```python
# tests/test_netease_crypto.py
import json
from platforms.netease.crypto import weapi_encrypt, eapi_encrypt


def test_weapi_encrypt_returns_params_and_enc_sec_key():
    result = weapi_encrypt({"s": "hello", "type": 1, "limit": 5})
    assert "params" in result
    assert "encSecKey" in result
    assert isinstance(result["params"], str)
    assert isinstance(result["encSecKey"], str)


def test_weapi_encrypt_params_is_base64():
    import base64
    result = weapi_encrypt({"s": "hello"})
    # Should not raise
    base64.b64decode(result["params"])


def test_weapi_encrypt_different_calls_produce_different_params():
    r1 = weapi_encrypt({"s": "hello"})
    r2 = weapi_encrypt({"s": "hello"})
    # Random key means different ciphertext each call
    assert r1["params"] != r2["params"]


def test_eapi_encrypt_returns_params():
    result = eapi_encrypt("/api/cloudsearch/pc", {"s": "test", "type": 1})
    assert "params" in result
    assert isinstance(result["params"], str)


def test_eapi_encrypt_is_hex():
    result = eapi_encrypt("/api/song/lyric", {"id": 123})
    # Should be valid hex
    bytes.fromhex(result["params"])
```

### Step 2: Run to verify failure

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
pytest tests/test_netease_crypto.py -v
```

Expected: `ModuleNotFoundError: No module named 'platforms.netease.crypto'`

### Step 3: Write `platforms/netease/crypto.py`

### Step 4: Run tests — Expected: 5 PASSED

### Step 5: Commit

```bash
git add platforms/netease/crypto.py tests/test_netease_crypto.py
git commit -m "feat: add Netease weapi/eapi encryption (pycryptodome)"
```

---

## Task 2: utils/lrc_parser.py — LRC Parser

**Files:**
- Create: `utils/lrc_parser.py`
- Create: `tests/test_lrc_parser.py`

### Step 1: Write failing tests

```python
# tests/test_lrc_parser.py
from utils.lrc_parser import parse_lrc

LRC_SAMPLE = """
[00:12.34]First line
[00:16.00]Second line
[01:02.500]Third line
[99:99.999]Last line
""".strip()

def test_parse_returns_lyric_lines():
    from core.models import LyricLine
    lines = parse_lrc(LRC_SAMPLE)
    assert len(lines) == 4
    assert all(isinstance(l, LyricLine) for l in lines)

def test_first_line_text():
    lines = parse_lrc(LRC_SAMPLE)
    assert lines[0].text == "First line"

def test_timestamp_conversion_ms():
    lines = parse_lrc(LRC_SAMPLE)
    # [00:12.34] = 12340ms
    assert lines[0].start_ms == 12340
    # [00:16.00] = 16000ms
    assert lines[1].start_ms == 16000

def test_end_ms_is_next_start():
    lines = parse_lrc(LRC_SAMPLE)
    assert lines[0].end_ms == lines[1].start_ms

def test_last_line_end_ms():
    lines = parse_lrc(LRC_SAMPLE)
    # Last line end = start + 5000 (default padding)
    last = lines[-1]
    assert last.end_ms == last.start_ms + 5000

def test_empty_lrc():
    assert parse_lrc("") == []

def test_lines_without_timestamp_are_skipped():
    lrc = "[00:01.00]A line\nNo timestamp here\n[00:03.00]Another"
    lines = parse_lrc(lrc)
    assert len(lines) == 2

def test_words_list_is_empty_for_plain_lrc():
    lines = parse_lrc(LRC_SAMPLE)
    for line in lines:
        assert line.words == []
```

### Step 2: Run to verify failure

```bash
pytest tests/test_lrc_parser.py -v
```

### Step 3: Write `utils/lrc_parser.py`

### Step 4: Run tests — Expected: 8 PASSED

### Step 5: Commit

```bash
git add utils/lrc_parser.py tests/test_lrc_parser.py
git commit -m "feat: add LRC timestamp parser returning LyricLine list"
```

---

## Task 3: Repository Credential CRUD (AES-256)

**Files:**
- Extend: `db/repository.py`
- Extend: `db/schema.sql` (already has credentials table)
- Create: `tests/test_repository_credentials.py`

### Step 1: Write failing tests

```python
# tests/test_repository_credentials.py
import pytest
from pathlib import Path
from db.repository import AppRepository


@pytest.fixture
def repo(tmp_path):
    return AppRepository(db_path=tmp_path / "test.db")


async def test_save_and_load_credentials(repo):
    await repo.init()
    payload = {"MUSIC_U": "abc123", "__csrf": "xyz"}
    await repo.save_credential("netease", payload)
    loaded = await repo.load_credential("netease")
    assert loaded == payload
    await repo.close()


async def test_load_missing_credential_returns_none(repo):
    await repo.init()
    assert await repo.load_credential("netease") is None
    await repo.close()


async def test_overwrite_credential(repo):
    await repo.init()
    await repo.save_credential("netease", {"old": "value"})
    await repo.save_credential("netease", {"new": "value"})
    loaded = await repo.load_credential("netease")
    assert loaded == {"new": "value"}
    await repo.close()


async def test_credential_is_encrypted_at_rest(repo):
    await repo.init()
    await repo.save_credential("netease", {"secret": "s3cr3t"})
    # Read raw blob — must NOT contain the secret in plaintext
    async with repo._db.execute(
        "SELECT data FROM credentials WHERE platform = ?", ("netease",)
    ) as cur:
        row = await cur.fetchone()
    assert b"s3cr3t" not in row[0]
    await repo.close()
```

### Step 2: Run to verify failure

```bash
pytest tests/test_repository_credentials.py -v
```

### Step 3: Add `save_credential` / `load_credential` to `db/repository.py`

### Step 4: Run tests — Expected: 4 PASSED

### Step 5: Commit

```bash
git add db/repository.py tests/test_repository_credentials.py
git commit -m "feat: add AES-256 encrypted credential storage to AppRepository"
```

---

## Task 4: platforms/netease/client.py — API Client

**Files:**
- Create: `platforms/netease/client.py`
- Create: `tests/test_netease_client.py`

### Step 1: Write failing tests (mocked httpx)

```python
# tests/test_netease_client.py
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from platforms.netease.client import NeteaseClient
from core.models import Track


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
    assert t.duration_ms == 240000


STREAM_RESPONSE = {
    "data": [{"url": "https://cdn.example.com/audio.mp3", "code": 200}],
    "code": 200,
}


async def test_get_stream_url(client):
    from core.models import Track
    track = Track(
        id="123456", platform="netease", title="T", artist="A",
        artists=["A"], album="Alb", album_cover_url="", duration_ms=1000,
    )
    mock_resp = MagicMock()
    mock_resp.json.return_value = STREAM_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        url = await client.get_stream_url(track)

    assert url == "https://cdn.example.com/audio.mp3"


async def test_search_empty_result(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": {"songs": []}, "code": 200}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        tracks = await client.search("nonexistent")
    assert tracks == []
```

### Step 2: Run to verify failure

```bash
pytest tests/test_netease_client.py -v
```

### Step 3: Write `platforms/netease/client.py`

### Step 4: Run tests — Expected: 3 PASSED

### Step 5: Commit

```bash
git add platforms/netease/client.py tests/test_netease_client.py
git commit -m "feat: add NeteaseClient with search and stream URL (mocked tests)"
```

---

## Task 5: Login Dialog + Auth

**Files:**
- Create: `ui/components/login_dialog.py`
- Create: `platforms/netease/auth.py`

### Step 1: Write `ui/components/login_dialog.py`

QDialog with embedded QWebEngineView, emits `cookies_captured(dict)` signal when target cookies are detected.

### Step 2: Write `platforms/netease/auth.py`

Opens LoginDialog with `music.163.com`, waits for `MUSIC_U` + `__csrf` cookies, saves via AppRepository.

### Step 3: Smoke test (manual — no automated test for WebView)

```bash
# Verify no import errors
python3 -c "from ui.components.login_dialog import LoginDialog; from platforms.netease.auth import NeteaseAuth; print('OK')"
```

### Step 4: Commit

```bash
git add ui/components/login_dialog.py platforms/netease/auth.py
git commit -m "feat: add WebView login dialog and Netease auth Cookie capture"
```

---

## Task 6: netease/lyrics.py + tests

**Files:**
- Create: `platforms/netease/lyrics.py`
- Create: `tests/test_netease_lyrics.py`

### Step 1: Write failing tests

```python
# tests/test_netease_lyrics.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from platforms.netease.lyrics import NeteaseLyrics
from core.models import LyricLine, Track


@pytest.fixture
def lyrics_client():
    return NeteaseLyrics(cookies={"MUSIC_U": "fake", "__csrf": "fake"})


def _make_track(tid="123"):
    return Track(id=tid, platform="netease", title="T", artist="A",
                 artists=["A"], album="Alb", album_cover_url="", duration_ms=180000)


LRC_BODY = "[00:01.00]Hello\n[00:03.00]World\n"
LYRICS_RESPONSE = {
    "lrc": {"lyric": LRC_BODY},
    "klyric": {"lyric": ""},
    "code": 200,
}


async def test_get_lyrics_returns_lyric_lines(lyrics_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = LYRICS_RESPONSE
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        lines = await lyrics_client.get_lyrics(_make_track())

    assert len(lines) == 2
    assert lines[0].text == "Hello"
    assert lines[1].text == "World"


async def test_get_lyrics_no_lrc_returns_empty(lyrics_client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"lrc": {"lyric": ""}, "code": 200}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        lines = await lyrics_client.get_lyrics(_make_track())

    assert lines == []
```

### Step 2: Run to verify failure

```bash
pytest tests/test_netease_lyrics.py -v
```

### Step 3: Write `platforms/netease/lyrics.py`

### Step 4: Run tests — Expected: 2 PASSED

### Step 5: Commit

```bash
git add platforms/netease/lyrics.py tests/test_netease_lyrics.py
git commit -m "feat: add NeteaseLyrics client with LRC parsing"
```

---

## Task 7: core/vlc_backend.py — VLC Audio Backend

**Files:**
- Create: `core/vlc_backend.py`
- Create: `tests/test_vlc_backend.py`

### Step 1: Write failing tests (mock vlc)

```python
# tests/test_vlc_backend.py
import pytest
from unittest.mock import MagicMock, patch, call
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_vlc_backend_play_calls_vlc(qapp):
    with patch("core.vlc_backend.vlc") as mock_vlc:
        mock_instance = MagicMock()
        mock_player = MagicMock()
        mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player

        from importlib import reload
        import core.vlc_backend
        reload(core.vlc_backend)
        from core.vlc_backend import VLCBackend

        backend = VLCBackend()
        backend.play("https://example.com/audio.mp3")
        mock_instance.media_new.assert_called_once()
        mock_player.play.assert_called_once()


def test_vlc_backend_pause_calls_vlc(qapp):
    with patch("core.vlc_backend.vlc") as mock_vlc:
        mock_instance = MagicMock()
        mock_player = MagicMock()
        mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player

        from importlib import reload
        import core.vlc_backend
        reload(core.vlc_backend)
        from core.vlc_backend import VLCBackend

        backend = VLCBackend()
        backend.pause()
        mock_player.pause.assert_called_once()


def test_vlc_backend_stop_calls_vlc(qapp):
    with patch("core.vlc_backend.vlc") as mock_vlc:
        mock_instance = MagicMock()
        mock_player = MagicMock()
        mock_vlc.Instance.return_value = mock_instance
        mock_instance.media_player_new.return_value = mock_player

        from importlib import reload
        import core.vlc_backend
        reload(core.vlc_backend)
        from core.vlc_backend import VLCBackend

        backend = VLCBackend()
        backend.stop()
        mock_player.stop.assert_called_once()
```

### Step 2: Run to verify failure

```bash
pytest tests/test_vlc_backend.py -v
```

### Step 3: Write `core/vlc_backend.py`

### Step 4: Run tests — Expected: 3 PASSED

### Step 5: Commit

```bash
git add core/vlc_backend.py tests/test_vlc_backend.py
git commit -m "feat: add VLCBackend audio player bridge"
```

---

## Final: Full Test Suite

```bash
pytest -v
```

Expected: All Phase 1 + Phase 2 tests PASSED (47 + ~25 new = ~72 total).

---

## Self-Review Checklist

### Spec Coverage (spec.md §11 Phase 2)
- [ ] WebView 登录弹窗 + Cookie 捕获 → Task 5
- [ ] weapi/eapi 加密算法实现 → Task 1
- [ ] 搜索功能（返回结果列表） → Task 4
- [ ] 获取音频流 URL + VLC 播放 → Task 4 + Task 7
- [ ] 歌词获取 + LRC/逐字解析 → Task 6 + Task 2
