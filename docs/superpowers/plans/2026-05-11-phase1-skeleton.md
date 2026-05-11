# SomniaMusicPlayer Phase 1 — 基础骨架 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the runnable application skeleton with main window layout (sidebar + content + bottom bar), theme system, shared data models, player state machine, queue management, and async database initialization — all wired through a qasync event loop.

**Architecture:** PyQt6 QMainWindow with fixed 200px sidebar, flex main content area (QStackedWidget), and persistent 90px bottom NowPlayingBar. All async I/O runs in asyncio coroutines bridged to Qt via qasync. aiosqlite manages SQLite at `~/.somniaplayer/app.db`. Data models are plain dataclasses in `core/models.py`. The player state machine (`core/player.py`) emits Qt signals on every state change; platform backends are plugged in during later phases.

**Tech Stack:** Python 3.12, PyQt6 6.7+, qasync 0.27+, aiosqlite 0.20+, pycryptodome 3.20+ (prepared for Phase 2), pytest + pytest-asyncio + pytest-qt

---

## File Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | All runtime + dev dependencies |
| `pytest.ini` | pytest + asyncio_mode config |
| `core/__init__.py` | Package marker |
| `core/models.py` | Track, LyricWord, LyricLine, Playlist, PlayerState dataclasses |
| `core/player.py` | UnifiedPlayer QObject — state machine + Qt signals |
| `core/queue.py` | PlayQueue — ordered track list with next/prev/shuffle |
| `core/lyrics_engine.py` | Skeleton placeholder (implemented Phase 3) |
| `db/__init__.py` | Package marker |
| `db/schema.sql` | CREATE TABLE statements for credentials/history/settings |
| `db/repository.py` | AppRepository — async init, settings CRUD |
| `ui/__init__.py` | Package marker |
| `ui/theme.py` | COLORS dict + FONTS dict (spec §5.2–5.3) |
| `ui/app_window.py` | MainWindow — wires sidebar + QStackedWidget + NowPlayingBar |
| `ui/components/__init__.py` | Package marker |
| `ui/components/sidebar.py` | SidebarWidget (200px, nav signals, platform rows) |
| `ui/components/now_playing_bar.py` | NowPlayingBar (90px, playback controls + progress + volume) |
| `platforms/__init__.py` | Package marker |
| `platforms/base.py` | AbstractPlatform ABC |
| `utils/__init__.py` | Package marker |
| `main.py` | QApplication + qasync event loop + DB init + MainWindow |
| `tests/__init__.py` | Package marker |
| `tests/test_models.py` | Dataclass field defaults |
| `tests/test_theme.py` | All required color/font keys present |
| `tests/test_repository.py` | DB creation, default settings seed, CRUD |
| `tests/test_player.py` | All state machine transitions |
| `tests/test_queue.py` | Queue navigation and edge cases |
| `tests/test_ui_components.py` | Smoke tests: widget creation + signals |

---

## Task 1: Project Structure & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `core/__init__.py`, `db/__init__.py`, `ui/__init__.py`, `ui/components/__init__.py`, `platforms/__init__.py`, `utils/__init__.py`, `tests/__init__.py`
- Create: `assets/icons/.gitkeep`, `assets/fonts/.gitkeep`

- [ ] **Step 1: Create directory tree**

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
mkdir -p core db ui/components ui/pages platforms/spotify platforms/ytmusic platforms/netease utils assets/icons assets/fonts tests
```

- [ ] **Step 2: Create all `__init__.py` files**

```bash
touch core/__init__.py db/__init__.py ui/__init__.py ui/components/__init__.py ui/pages/__init__.py \
      platforms/__init__.py platforms/spotify/__init__.py platforms/ytmusic/__init__.py \
      platforms/netease/__init__.py utils/__init__.py tests/__init__.py
touch assets/icons/.gitkeep assets/fonts/.gitkeep
```

- [ ] **Step 3: Write `requirements.txt`**

```
PyQt6>=6.7.0
PyQt6-WebEngine>=6.7.0
qasync>=0.27.0
httpx[http2]>=0.27.0
ytmusicapi>=1.7.0
python-vlc>=3.0.20122
yt-dlp>=2024.5.0
colorthief>=0.2.1
aiosqlite>=0.20.0
pycryptodome>=3.20.0
sounddevice>=0.4.7
Pillow>=10.3.0

# Dev
pytest>=8.2.0
pytest-asyncio>=0.23.0
pytest-qt>=4.4.0
```

- [ ] **Step 4: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: Install dependencies**

```bash
pip install PyQt6 PyQt6-WebEngine qasync aiosqlite pycryptodome Pillow \
            pytest pytest-asyncio pytest-qt
```

Expected: packages install without error.

- [ ] **Step 6: Commit**

```bash
git init
git add requirements.txt pytest.ini core/ db/ ui/ platforms/ utils/ assets/ tests/
git commit -m "chore: initialize project structure and dependencies"
```

---

## Task 2: Data Models

**Files:**
- Create: `core/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from core.models import Track, LyricWord, LyricLine, Playlist, PlayerState


def test_track_required_fields_and_defaults():
    t = Track(
        id="123", platform="netease", title="Song",
        artist="Artist", artists=["Artist"], album="Album",
        album_cover_url="https://example.com/cover.jpg",
        duration_ms=240000,
    )
    assert t.is_explicit is False
    assert t.stream_url is None
    assert t.platform == "netease"


def test_lyric_word_fields():
    w = LyricWord(start_ms=0, end_ms=500, text="Hello")
    assert w.text == "Hello"


def test_lyric_line_default_words():
    line = LyricLine(start_ms=0, end_ms=4000, text="Hello world")
    assert line.words == []


def test_playlist_default_tracks():
    pl = Playlist(id="p1", platform="spotify", name="My Mix",
                  cover_url="", track_count=10)
    assert pl.tracks == []


def test_player_state_defaults():
    state = PlayerState()
    assert state.status == "idle"
    assert state.current_track is None
    assert state.position_ms == 0
    assert state.duration_ms == 0
    assert state.volume == 70
    assert state.shuffle is False
    assert state.repeat_mode == "none"
    assert state.queue == []
    assert state.queue_index == -1
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.models'`

- [ ] **Step 3: Write `core/models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Track:
    id: str
    platform: str          # "spotify" | "ytmusic" | "netease"
    title: str
    artist: str
    artists: list[str]
    album: str
    album_cover_url: str
    duration_ms: int
    is_explicit: bool = False
    stream_url: str | None = None


@dataclass
class LyricWord:
    start_ms: int
    end_ms: int
    text: str


@dataclass
class LyricLine:
    start_ms: int
    end_ms: int
    text: str
    words: list[LyricWord] = field(default_factory=list)


@dataclass
class Playlist:
    id: str
    platform: str
    name: str
    cover_url: str
    track_count: int
    tracks: list[Track] = field(default_factory=list)


@dataclass
class PlayerState:
    status: str = "idle"        # "idle"|"loading"|"playing"|"paused"|"error"
    current_track: Track | None = None
    position_ms: int = 0
    duration_ms: int = 0
    volume: int = 70
    shuffle: bool = False
    repeat_mode: str = "none"   # "none"|"one"|"all"
    queue: list[Track] = field(default_factory=list)
    queue_index: int = -1
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_models.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat: add shared data model dataclasses"
```

---

## Task 3: Theme System

**Files:**
- Create: `ui/theme.py`
- Create: `tests/test_theme.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_theme.py
from ui.theme import COLORS, FONTS


def test_all_required_color_keys_present():
    required = [
        "bg_base", "bg_surface", "bg_elevated", "bg_hover",
        "accent", "accent_dim",
        "text_primary", "text_secondary", "text_muted",
        "platform_spotify", "platform_ytmusic", "platform_netease",
        "border", "divider",
        "lyrics_active", "lyrics_past", "lyrics_future",
    ]
    for key in required:
        assert key in COLORS, f"Missing COLORS['{key}']"
        assert COLORS[key].startswith("#"), f"COLORS['{key}'] must be a hex string"


def test_all_required_font_keys_present():
    required = ["family", "size_xs", "size_sm", "size_md",
                "size_lg", "size_xl", "size_lyrics"]
    for key in required:
        assert key in FONTS, f"Missing FONTS['{key}']"


def test_accent_color_is_spotify_green():
    assert COLORS["accent"] == "#1DB954"


def test_font_family_is_inter():
    assert FONTS["family"] == "Inter"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_theme.py -v
```

Expected: `ModuleNotFoundError: No module named 'ui.theme'`

- [ ] **Step 3: Write `ui/theme.py`**

```python
COLORS = {
    # Background layers
    "bg_base":       "#0D0D0D",
    "bg_surface":    "#161616",
    "bg_elevated":   "#1E1E1E",
    "bg_hover":      "#2A2A2A",

    # Accent
    "accent":        "#1DB954",
    "accent_dim":    "#158A3E",

    # Text
    "text_primary":  "#FFFFFF",
    "text_secondary": "#A0A0A0",
    "text_muted":    "#5A5A5A",

    # Platform brand colors
    "platform_spotify":  "#1DB954",
    "platform_ytmusic":  "#FF0000",
    "platform_netease":  "#E60026",

    # Structural
    "border":        "#2C2C2C",
    "divider":       "#1F1F1F",

    # Lyrics states
    "lyrics_active": "#FFFFFF",
    "lyrics_past":   "#4A4A4A",
    "lyrics_future": "#6E6E6E",
}

FONTS = {
    "family":      "Inter",
    "size_xs":     10,
    "size_sm":     12,
    "size_md":     14,
    "size_lg":     18,
    "size_xl":     24,
    "size_lyrics": 22,
}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_theme.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add ui/theme.py tests/test_theme.py
git commit -m "feat: add theme color and font constants"
```

---

## Task 4: Database Schema & Repository

**Files:**
- Create: `db/schema.sql`
- Create: `db/repository.py`
- Create: `tests/test_repository.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_repository.py
import pytest
from pathlib import Path
from db.repository import AppRepository


@pytest.fixture
def repo(tmp_path):
    return AppRepository(db_path=tmp_path / "test.db")


async def test_init_creates_default_settings(repo):
    await repo.init()
    volume = await repo.get_setting("volume")
    assert volume == "70"
    await repo.close()


async def test_set_and_get_setting(repo):
    await repo.init()
    await repo.set_setting("volume", "50")
    assert await repo.get_setting("volume") == "50"
    await repo.close()


async def test_get_missing_setting_returns_none(repo):
    await repo.init()
    assert await repo.get_setting("nonexistent") is None
    await repo.close()


async def test_all_default_settings_seeded(repo):
    await repo.init()
    for key in ("volume", "repeat_mode", "shuffle", "cover_rotation", "lyrics_font_size"):
        val = await repo.get_setting(key)
        assert val is not None, f"Default setting '{key}' not seeded"
    await repo.close()


async def test_double_init_is_idempotent(repo):
    await repo.init()
    await repo.init()  # second call must not raise or duplicate
    volume = await repo.get_setting("volume")
    assert volume == "70"
    await repo.close()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_repository.py -v
```

Expected: `ModuleNotFoundError: No module named 'db.repository'`

- [ ] **Step 3: Write `db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS credentials (
    platform    TEXT PRIMARY KEY,
    data        BLOB NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS play_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    track_id    TEXT NOT NULL,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL,
    cover_url   TEXT,
    played_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
```

- [ ] **Step 4: Write `db/repository.py`**

```python
from __future__ import annotations
import aiosqlite
from pathlib import Path

DB_PATH = Path.home() / ".somniaplayer" / "app.db"
_SCHEMA = Path(__file__).parent / "schema.sql"

_DEFAULTS = {
    "volume":          "70",
    "repeat_mode":     "none",
    "shuffle":         "false",
    "cover_rotation":  "true",
    "lyrics_font_size": "22",
}


class AppRepository:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        await self._db.executescript(_SCHEMA.read_text())
        for key, value in _DEFAULTS.items():
            await self._db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await self._db.commit()

    async def get_setting(self, key: str) -> str | None:
        async with self._db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_repository.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql db/repository.py tests/test_repository.py
git commit -m "feat: add SQLite schema and async repository"
```

---

## Task 5: Player State Machine

**Files:**
- Create: `core/player.py`
- Create: `tests/test_player.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_player.py
import pytest
from PyQt6.QtWidgets import QApplication
from core.player import UnifiedPlayer
from core.models import Track, PlayerState


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _track(**kw) -> Track:
    base = dict(id="t1", platform="netease", title="Test Song",
                artist="Artist", artists=["Artist"], album="Album",
                album_cover_url="", duration_ms=180_000)
    base.update(kw)
    return Track(**base)


def test_initial_state_is_idle(qapp):
    p = UnifiedPlayer()
    assert p.state.status == "idle"
    assert p.state.current_track is None


def test_load_transitions_to_loading(qapp):
    p = UnifiedPlayer()
    t = _track()
    p.load(t)
    assert p.state.status == "loading"
    assert p.state.current_track == t
    assert p.state.duration_ms == 180_000


def test_load_success_transitions_to_playing(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    assert p.state.status == "playing"


def test_pause_requires_playing(qapp):
    p = UnifiedPlayer()
    p.pause()  # from idle — must not crash, must stay idle
    assert p.state.status == "idle"


def test_pause_from_playing(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    p.pause()
    assert p.state.status == "paused"


def test_resume_from_paused(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    p.pause()
    p.resume()
    assert p.state.status == "playing"


def test_stop_returns_to_idle(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_success()
    p.stop()
    assert p.state.status == "idle"
    assert p.state.current_track is None
    assert p.state.position_ms == 0


def test_load_error_transitions_to_error(qapp):
    p = UnifiedPlayer()
    p.load(_track())
    p.on_load_error("network timeout")
    assert p.state.status == "error"


def test_seek_clamps_to_duration(qapp):
    p = UnifiedPlayer()
    p.load(_track(duration_ms=60_000))
    p.on_load_success()
    p.seek(999_999)
    assert p.state.position_ms == 60_000
    p.seek(-100)
    assert p.state.position_ms == 0


def test_seek_ignored_when_idle(qapp):
    p = UnifiedPlayer()
    p.seek(5000)
    assert p.state.position_ms == 0


def test_volume_clamped_to_0_100(qapp):
    p = UnifiedPlayer()
    p.set_volume(150)
    assert p.state.volume == 100
    p.set_volume(-10)
    assert p.state.volume == 0


def test_state_changed_signal_emitted_on_load(qapp, qtbot):
    p = UnifiedPlayer()
    with qtbot.waitSignal(p.state_changed, timeout=500):
        p.load(_track())


def test_track_changed_signal_emitted_on_load(qapp, qtbot):
    p = UnifiedPlayer()
    received = []
    p.track_changed.connect(received.append)
    p.load(_track())
    assert len(received) == 1
    assert received[0].title == "Test Song"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_player.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.player'`

- [ ] **Step 3: Write `core/player.py`**

```python
from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState


class UnifiedPlayer(QObject):
    state_changed = pyqtSignal(PlayerState)
    track_changed = pyqtSignal(object)   # Track
    position_changed = pyqtSignal(int)   # ms
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state = PlayerState()

    @property
    def state(self) -> PlayerState:
        return self._state

    # ── internal helpers ──────────────────────────────────────────────────────

    def _set_status(self, status: str) -> None:
        self._state.status = status
        self.state_changed.emit(self._state)

    # ── public API ────────────────────────────────────────────────────────────

    def load(self, track: Track) -> None:
        self._state.current_track = track
        self._state.position_ms = 0
        self._state.duration_ms = track.duration_ms
        self._set_status("loading")
        self.track_changed.emit(track)

    def on_load_success(self) -> None:
        if self._state.status != "loading":
            return
        self._set_status("playing")

    def on_load_error(self, message: str) -> None:
        if self._state.status != "loading":
            return
        self._set_status("error")
        self.error_occurred.emit(message)

    def pause(self) -> None:
        if self._state.status != "playing":
            return
        self._set_status("paused")

    def resume(self) -> None:
        if self._state.status != "paused":
            return
        self._set_status("playing")

    def stop(self) -> None:
        self._state.current_track = None
        self._state.position_ms = 0
        self._set_status("idle")

    def seek(self, position_ms: int) -> None:
        if self._state.status not in ("playing", "paused"):
            return
        clamped = max(0, min(position_ms, self._state.duration_ms))
        self._state.position_ms = clamped
        self.position_changed.emit(clamped)

    def set_volume(self, volume: int) -> None:
        self._state.volume = max(0, min(volume, 100))

    def set_shuffle(self, enabled: bool) -> None:
        self._state.shuffle = enabled

    def set_repeat_mode(self, mode: str) -> None:
        if mode not in ("none", "one", "all"):
            raise ValueError(f"Invalid repeat mode: {mode!r}")
        self._state.repeat_mode = mode

    def update_position(self, position_ms: int) -> None:
        self._state.position_ms = position_ms
        self.position_changed.emit(position_ms)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_player.py -v
```

Expected: 13 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add core/player.py tests/test_player.py
git commit -m "feat: add UnifiedPlayer state machine with Qt signals"
```

---

## Task 6: Queue Management

**Files:**
- Create: `core/queue.py`
- Create: `tests/test_queue.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_queue.py
from core.queue import PlayQueue
from core.models import Track


def _t(tid: str) -> Track:
    return Track(id=tid, platform="netease", title=f"Song {tid}",
                 artist="A", artists=["A"], album="Alb",
                 album_cover_url="", duration_ms=180_000)


def test_empty_queue():
    q = PlayQueue()
    assert len(q) == 0
    assert q.current_track is None
    assert q.current_index == -1


def test_set_tracks_sets_start_index():
    q = PlayQueue()
    tracks = [_t("1"), _t("2"), _t("3")]
    q.set_tracks(tracks, start_index=1)
    assert q.current_track == tracks[1]
    assert len(q) == 3


def test_next_advances():
    q = PlayQueue()
    tracks = [_t("1"), _t("2")]
    q.set_tracks(tracks, start_index=0)
    result = q.next()
    assert result == tracks[1]


def test_next_at_end_no_repeat_returns_none():
    q = PlayQueue()
    q.set_tracks([_t("1")], start_index=0)
    assert q.next(repeat_mode="none") is None


def test_next_repeat_all_wraps():
    q = PlayQueue()
    tracks = [_t("1"), _t("2")]
    q.set_tracks(tracks, start_index=1)
    result = q.next(repeat_mode="all")
    assert result == tracks[0]


def test_next_repeat_one_stays():
    q = PlayQueue()
    tracks = [_t("1"), _t("2")]
    q.set_tracks(tracks, start_index=0)
    result = q.next(repeat_mode="one")
    assert result == tracks[0]


def test_previous_goes_back():
    q = PlayQueue()
    tracks = [_t("1"), _t("2")]
    q.set_tracks(tracks, start_index=1)
    assert q.previous() == tracks[0]


def test_previous_at_start_stays():
    q = PlayQueue()
    q.set_tracks([_t("1"), _t("2")], start_index=0)
    assert q.previous() == q.tracks[0]


def test_add_to_empty_sets_index_zero():
    q = PlayQueue()
    t = _t("1")
    q.add(t)
    assert q.current_track == t
    assert len(q) == 1


def test_add_to_non_empty_appends():
    q = PlayQueue()
    q.set_tracks([_t("1")], start_index=0)
    q.add(_t("2"))
    assert len(q) == 2
    assert q.current_track == q.tracks[0]  # index unchanged


def test_clear_resets():
    q = PlayQueue()
    q.set_tracks([_t("1"), _t("2")])
    q.clear()
    assert len(q) == 0
    assert q.current_track is None


def test_shuffle_preserves_current_track():
    import random
    random.seed(42)
    q = PlayQueue()
    tracks = [_t(str(i)) for i in range(10)]
    q.set_tracks(tracks, start_index=3)
    current_before = q.current_track
    q.shuffle()
    assert q.current_track == current_before
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_queue.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.queue'`

- [ ] **Step 3: Write `core/queue.py`**

```python
from __future__ import annotations
import random
from core.models import Track


class PlayQueue:
    def __init__(self) -> None:
        self._tracks: list[Track] = []
        self._index: int = -1

    @property
    def tracks(self) -> list[Track]:
        return self._tracks

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def current_track(self) -> Track | None:
        if 0 <= self._index < len(self._tracks):
            return self._tracks[self._index]
        return None

    def set_tracks(self, tracks: list[Track], start_index: int = 0) -> None:
        self._tracks = list(tracks)
        self._index = start_index if tracks else -1

    def add(self, track: Track) -> None:
        self._tracks.append(track)
        if self._index == -1:
            self._index = 0

    def next(self, repeat_mode: str = "none") -> Track | None:
        if not self._tracks:
            return None
        if repeat_mode == "one":
            return self.current_track
        nxt = self._index + 1
        if nxt >= len(self._tracks):
            if repeat_mode == "all":
                nxt = 0
            else:
                return None
        self._index = nxt
        return self.current_track

    def previous(self) -> Track | None:
        if not self._tracks:
            return None
        self._index = max(0, self._index - 1)
        return self.current_track

    def shuffle(self) -> None:
        if not self._tracks:
            return
        current = self.current_track
        random.shuffle(self._tracks)
        if current is not None:
            self._index = self._tracks.index(current)

    def clear(self) -> None:
        self._tracks = []
        self._index = -1

    def __len__(self) -> int:
        return len(self._tracks)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_queue.py -v
```

Expected: 12 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add core/queue.py tests/test_queue.py
git commit -m "feat: add PlayQueue with next/prev/shuffle/repeat support"
```

---

## Task 7: AbstractPlatform Base

**Files:**
- Create: `platforms/base.py`
- Create: `core/lyrics_engine.py` (skeleton)

- [ ] **Step 1: Write `platforms/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from core.models import Track, Playlist, LyricLine


class AbstractPlatform(ABC):
    platform_id: str  # "spotify" | "ytmusic" | "netease"

    @abstractmethod
    async def is_authenticated(self) -> bool: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 30) -> list[Track]: ...

    @abstractmethod
    async def get_stream_url(self, track: Track) -> str: ...

    @abstractmethod
    async def get_lyrics(self, track: Track) -> list[LyricLine]: ...

    @abstractmethod
    async def get_library_playlists(self) -> list[Playlist]: ...
```

- [ ] **Step 2: Write `core/lyrics_engine.py`** (skeleton for Phase 3)

```python
# Lyrics time-axis engine — implemented in Phase 3
```

- [ ] **Step 3: Commit**

```bash
git add platforms/base.py core/lyrics_engine.py
git commit -m "feat: add AbstractPlatform interface and lyrics engine skeleton"
```

---

## Task 8: Sidebar Component

**Files:**
- Create: `ui/components/sidebar.py`

- [ ] **Step 1: Write `ui/components/sidebar.py`**

```python
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import COLORS, FONTS


class SidebarWidget(QWidget):
    nav_changed = pyqtSignal(str)  # page id: "home"|"search"|"library"|"settings"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._setup_ui()
        self._apply_styles()

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(2)

        title = QLabel("Somnia")
        title.setObjectName("appName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(16)

        for page_id, label in [
            ("search",  "🔍  搜索"),
            ("home",    "🏠  首页"),
            ("library", "📚  我的库"),
        ]:
            layout.addWidget(self._make_nav_btn(page_id, label))

        layout.addWidget(self._make_divider())
        layout.addSpacing(4)

        section = QLabel("平台账号")
        section.setObjectName("sectionLabel")
        layout.addWidget(section)

        for platform_id, name in [
            ("spotify",  "Spotify"),
            ("ytmusic",  "YouTube Music"),
            ("netease",  "网易云"),
        ]:
            layout.addWidget(self._make_platform_row(platform_id, name))

        layout.addWidget(self._make_divider())
        layout.addStretch()

        layout.addWidget(self._make_nav_btn("settings", "⚙️  设置"))
        layout.addSpacing(8)

    def _make_nav_btn(self, page_id: str, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda _checked, p=page_id: self.nav_changed.emit(p))
        self._nav_buttons[page_id] = btn
        return btn

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        return line

    def _make_platform_row(self, _platform_id: str, name: str) -> QWidget:
        row = QWidget()
        row.setObjectName("platformRow")
        vl = QVBoxLayout(row)
        vl.setContentsMargins(16, 4, 16, 4)
        lbl = QLabel(f"○  {name}")
        lbl.setObjectName("platformLabel")
        vl.addWidget(lbl)
        return row

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            SidebarWidget {{
                background-color: {c['bg_surface']};
                border-right: 1px solid {c['border']};
            }}
            #appName {{
                color: {c['text_primary']};
                font-size: {f['size_md']}px;
                font-weight: bold;
                padding: 0 12px;
            }}
            #navButton {{
                text-align: left;
                padding: 8px 16px;
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                border-radius: 0;
            }}
            #navButton:hover {{
                background-color: {c['bg_hover']};
                color: {c['text_primary']};
                border-left-color: {c['accent']};
            }}
            #navButton:checked {{
                background-color: {c['bg_hover']};
                color: {c['text_primary']};
                border-left-color: {c['accent']};
            }}
            #divider {{
                color: {c['divider']};
                margin: 4px 12px;
                max-height: 1px;
            }}
            #sectionLabel {{
                color: {c['text_muted']};
                font-size: {f['size_xs']}px;
                padding: 4px 16px;
            }}
            #platformLabel {{
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
            }}
        """)

    # ── public API ────────────────────────────────────────────────────────────

    def set_active_page(self, page_id: str) -> None:
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)
```

- [ ] **Step 2: Commit**

```bash
git add ui/components/sidebar.py
git commit -m "feat: add SidebarWidget with nav signals and platform rows"
```

---

## Task 9: NowPlayingBar Component

**Files:**
- Create: `ui/components/now_playing_bar.py`

- [ ] **Step 1: Write `ui/components/now_playing_bar.py`**

```python
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSlider,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import COLORS, FONTS
from core.models import PlayerState


class NowPlayingBar(QWidget):
    play_pause_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)   # ms
    volume_changed = pyqtSignal(int)   # 0–100
    shuffle_toggled = pyqtSignal()
    repeat_toggled = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(90)
        self._duration_ms: int = 0
        self._setup_ui()
        self._apply_styles()

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 0, 16, 0)
        root.setSpacing(0)

        root.addWidget(self._build_left(), stretch=0)
        root.addWidget(self._build_center(), stretch=1)
        root.addWidget(self._build_right(), stretch=0)

    def _build_left(self) -> QWidget:
        widget = QWidget()
        widget.setMinimumWidth(200)
        hl = QHBoxLayout(widget)
        hl.setSpacing(12)
        hl.setContentsMargins(0, 0, 0, 0)

        self._cover = QLabel()
        self._cover.setFixedSize(48, 48)
        self._cover.setObjectName("coverThumb")
        hl.addWidget(self._cover)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._title = QLabel("—")
        self._title.setObjectName("trackTitle")
        self._artist = QLabel("—")
        self._artist.setObjectName("trackArtist")
        info.addWidget(self._title)
        info.addWidget(self._artist)
        hl.addLayout(info)
        hl.addStretch()
        return widget

    def _build_center(self) -> QWidget:
        widget = QWidget()
        vl = QVBoxLayout(widget)
        vl.setContentsMargins(0, 8, 0, 8)
        vl.setSpacing(6)

        # Control buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._shuffle_btn = self._ctrl_btn("⇌")
        self._shuffle_btn.clicked.connect(self.shuffle_toggled)
        btn_row.addWidget(self._shuffle_btn)

        self._prev_btn = self._ctrl_btn("⏮")
        self._prev_btn.clicked.connect(self.prev_clicked)
        btn_row.addWidget(self._prev_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("playBtn")
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.clicked.connect(self.play_pause_clicked)
        btn_row.addWidget(self._play_btn)

        self._next_btn = self._ctrl_btn("⏭")
        self._next_btn.clicked.connect(self.next_clicked)
        btn_row.addWidget(self._next_btn)

        self._repeat_btn = self._ctrl_btn("↻")
        self._repeat_btn.clicked.connect(self.repeat_toggled)
        btn_row.addWidget(self._repeat_btn)

        vl.addLayout(btn_row)

        # Progress row
        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)

        self._pos_label = QLabel("0:00")
        self._pos_label.setObjectName("timeLabel")
        prog_row.addWidget(self._pos_label)

        self._progress = QSlider(Qt.Orientation.Horizontal)
        self._progress.setObjectName("progressSlider")
        self._progress.setRange(0, 10_000)
        self._progress.sliderMoved.connect(self._on_seek)
        prog_row.addWidget(self._progress, stretch=1)

        self._dur_label = QLabel("0:00")
        self._dur_label.setObjectName("timeLabel")
        prog_row.addWidget(self._dur_label)

        vl.addLayout(prog_row)
        return widget

    def _build_right(self) -> QWidget:
        widget = QWidget()
        widget.setMinimumWidth(150)
        hl = QHBoxLayout(widget)
        hl.setContentsMargins(8, 0, 0, 0)
        hl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hl.setSpacing(8)

        hl.addWidget(QLabel("🔊"))

        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setObjectName("volumeSlider")
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(100)
        self._volume.valueChanged.connect(self.volume_changed)
        hl.addWidget(self._volume)
        return widget

    def _ctrl_btn(self, icon: str) -> QPushButton:
        btn = QPushButton(icon)
        btn.setObjectName("controlBtn")
        return btn

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            NowPlayingBar {{
                background-color: {c['bg_surface']};
                border-top: 1px solid {c['border']};
            }}
            #coverThumb {{
                background-color: {c['bg_elevated']};
                border-radius: 6px;
            }}
            #trackTitle {{
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                font-weight: bold;
            }}
            #trackArtist {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
            }}
            #controlBtn {{
                background: transparent;
                border: none;
                color: {c['text_secondary']};
                font-size: 15px;
                padding: 4px 8px;
            }}
            #controlBtn:hover {{ color: {c['text_primary']}; }}
            #playBtn {{
                background-color: {c['accent']};
                border: none;
                color: #000000;
                font-size: 15px;
                border-radius: 18px;
            }}
            #playBtn:hover {{ background-color: {c['accent_dim']}; }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {c['bg_elevated']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {c['accent']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 0; height: 0;
            }}
            QSlider::handle:horizontal:hover {{
                width: 12px; height: 12px;
                margin: -4px 0;
                border-radius: 6px;
                background: {c['text_primary']};
            }}
            #timeLabel {{
                color: {c['text_muted']};
                font-size: {f['size_xs']}px;
                min-width: 36px;
            }}
        """)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _on_seek(self, value: int) -> None:
        if self._duration_ms > 0:
            self.seek_requested.emit(int(value / 10_000 * self._duration_ms))

    # ── public API ────────────────────────────────────────────────────────────

    def update_state(self, state: PlayerState) -> None:
        track = state.current_track
        if track:
            self._title.setText(track.title)
            self._artist.setText(track.artist)
            self._duration_ms = state.duration_ms
            self._dur_label.setText(self._fmt(state.duration_ms))
        else:
            self._title.setText("—")
            self._artist.setText("—")
            self._duration_ms = 0
            self._dur_label.setText("0:00")
        self._play_btn.setText("⏸" if state.status == "playing" else "▶")

    def update_position(self, position_ms: int) -> None:
        self._pos_label.setText(self._fmt(position_ms))
        if self._duration_ms > 0 and not self._progress.isSliderDown():
            self._progress.setValue(int(position_ms / self._duration_ms * 10_000))

    def set_volume(self, volume: int) -> None:
        self._volume.setValue(volume)
```

- [ ] **Step 2: Commit**

```bash
git add ui/components/now_playing_bar.py
git commit -m "feat: add NowPlayingBar with playback controls and progress slider"
```

---

## Task 10: Main Window

**Files:**
- Create: `ui/app_window.py`

- [ ] **Step 1: Write `ui/app_window.py`**

```python
from __future__ import annotations
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
)
from ui.theme import COLORS
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SomniaMusicPlayer")
        self.setMinimumSize(900, 600)
        self._setup_ui()
        self._apply_styles()
        self.sidebar.set_active_page("home")

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Body: sidebar + content area
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = SidebarWidget()
        self.sidebar.nav_changed.connect(self._on_nav)
        body.addWidget(self.sidebar)

        self.content = QStackedWidget()
        self.content.setObjectName("contentArea")
        body.addWidget(self.content, stretch=1)

        root.addLayout(body, stretch=1)

        # Persistent bottom bar
        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)

    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {COLORS['bg_base']};
                font-family: "Inter", "SF Pro Display", sans-serif;
            }}
            #contentArea {{
                background-color: {COLORS['bg_base']};
            }}
        """)
```

- [ ] **Step 2: Commit**

```bash
git add ui/app_window.py
git commit -m "feat: add MainWindow with sidebar, content stack, and now-playing bar"
```

---

## Task 11: UI Smoke Tests

**Files:**
- Create: `tests/test_ui_components.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_ui_components.py
import pytest
from PyQt6.QtWidgets import QApplication
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.app_window import MainWindow
from core.models import PlayerState


@pytest.fixture(scope="session")
def qapp_instance():
    return QApplication.instance() or QApplication([])


def test_sidebar_fixed_width(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    assert w.width() == 200


def test_sidebar_nav_signal(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    received: list[str] = []
    w.nav_changed.connect(received.append)
    w._nav_buttons["home"].click()
    assert received == ["home"]


def test_sidebar_set_active_checks_correct_button(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_active_page("library")
    assert w._nav_buttons["library"].isChecked()
    assert not w._nav_buttons["home"].isChecked()


def test_now_playing_bar_height(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    assert bar.height() == 90


def test_now_playing_bar_play_signal(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.play_pause_clicked, timeout=500):
        bar._play_btn.click()


def test_now_playing_bar_update_state_idle(qapp_instance, qtbot):
    bar = NowPlayingBar()
    qtbot.addWidget(bar)
    bar.update_state(PlayerState())
    assert bar._title.text() == "—"
    assert bar._play_btn.text() == "▶"


def test_main_window_title(qapp_instance, qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.windowTitle() == "SomniaMusicPlayer"


def test_main_window_has_sidebar_and_bar(qapp_instance, qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    assert w.sidebar is not None
    assert w.now_playing is not None
    assert w.content is not None
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_ui_components.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_components.py
git commit -m "test: add UI component smoke tests"
```

---

## Task 12: Entry Point with qasync

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write `main.py`**

```python
from __future__ import annotations
import asyncio
import sys
from PyQt6.QtWidgets import QApplication
import qasync
from ui.app_window import MainWindow
from db.repository import AppRepository


async def _run(app: QApplication) -> None:
    repo = AppRepository()
    await repo.init()

    window = MainWindow()

    # Pass initial volume from DB to the bar
    volume_str = await repo.get_setting("volume")
    if volume_str:
        window.now_playing.set_volume(int(volume_str))

    window.show()

    # Persist volume changes
    window.now_playing.volume_changed.connect(
        lambda v: asyncio.ensure_future(repo.set_setting("volume", str(v)))
    )

    try:
        # Keep the event loop alive until the window is closed
        closed = asyncio.get_event_loop().create_future()
        app.lastWindowClosed.connect(lambda: closed.set_result(None)
                                     if not closed.done() else None)
        await closed
    finally:
        await repo.close()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SomniaMusicPlayer")
    app.setApplicationVersion("0.1.0")

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        loop.run_until_complete(_run(app))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the app to verify it launches**

```bash
python main.py
```

Expected: Dark-themed window appears with sidebar (Somnia title, nav items, platform rows) and 90px bottom bar. Close the window to exit cleanly.

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: All tests PASSED (no failures).

- [ ] **Step 4: Final commit**

```bash
git add main.py
git commit -m "feat: wire qasync event loop and DB init into entry point"
```

---

## Self-Review Checklist

### Spec Coverage (spec.md §11 Phase 1)
- [x] 项目初始化，依赖安装 → Task 1
- [x] 主窗口布局（侧边栏 + 主区 + 底部栏） → Tasks 8–10
- [x] 主题系统（颜色、字体常量） → Task 3
- [x] 数据库初始化 → Task 4
- [x] 异步事件循环集成（qasync） → Task 12

### No Placeholders
All code blocks are complete. No TBD, TODO, or stub code beyond the intentional `core/lyrics_engine.py` skeleton.

### Type Consistency
- `PlayerState` defined in `core/models.py` Task 2, used in `core/player.py` Task 5, `NowPlayingBar.update_state()` Task 9 — all match.
- `Track` fields match across all usages.
- `AppRepository.get_setting()` returns `str | None` — callers in `main.py` guard with `if volume_str`.
