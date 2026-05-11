# 网易云播放流程接线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 NeteaseClient、UnifiedPlayer、VLCBackend 通过 AppController 接入 UI，实现从侧边栏登录、搜索、点击曲目到 VLC 播放的完整流程。

**Architecture:** 新建 `AppController(QObject)` 作为唯一服务协调层，持有全部后端服务并通过 Qt 信号向上层 UI 广播状态变化；`MainWindow` 接收 `AppController` 注入，各页面只持有 controller 引用。

**Tech Stack:** PyQt6 6.10, qasync 0.27+, python-vlc 3.0+, httpx, pycryptodome, aiosqlite

---

## File Map

| 文件 | 操作 |
|------|------|
| `core/app_controller.py` | 新建 |
| `tests/test_app_controller.py` | 新建 |
| `ui/components/track_list.py` | 新建 |
| `tests/test_track_list.py` | 新建 |
| `ui/components/sidebar.py` | 修改：平台行 → 按钮 + 状态指示 |
| `tests/test_ui_components.py` | 修改：更新 MainWindow 测试 + 新增侧边栏平台按钮测试 |
| `ui/pages/search_page.py` | 新建 |
| `tests/test_search_page.py` | 新建 |
| `ui/app_window.py` | 修改：接收 AppController，创建页面，连线信号 |
| `main.py` | 修改：构建 AppController，注入 MainWindow |

---

## Task 1: AppController

**Files:**
- Create: `core/app_controller.py`
- Create: `tests/test_app_controller.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_app_controller.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from core.models import Track, PlayerState


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _track(**kw) -> Track:
    base = dict(id="t1", platform="netease", title="Song", artist="A",
                artists=["A"], album="Alb", album_cover_url="", duration_ms=180_000)
    base.update(kw)
    return Track(**base)


class _FakeVLC(QObject):
    """Test double for VLCBackend — real Qt signals, no libvlc needed."""
    position_changed = pyqtSignal(int)
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def play(self, url): self._last_url = url
    def pause(self): pass
    def stop(self): pass
    def seek(self, ms): pass
    def set_volume(self, v): pass
    def get_position_ms(self): return 0


@pytest.fixture
def fake_vlc(qapp):
    return _FakeVLC()


@pytest.fixture
def ctrl(qapp, fake_vlc):
    with patch("core.app_controller.VLCBackend", return_value=fake_vlc), \
         patch("core.app_controller.AppRepository") as MockRepo:
        mock_repo = AsyncMock()
        mock_repo.get_setting = AsyncMock(return_value="70")
        mock_repo.load_credential = AsyncMock(return_value=None)
        mock_repo.save_credential = AsyncMock()
        mock_repo.init = AsyncMock()
        mock_repo.close = AsyncMock()
        MockRepo.return_value = mock_repo

        from core.app_controller import AppController
        c = AppController()
        c._vlc = fake_vlc
        return c


async def test_init_without_saved_cookies_stays_unauthenticated(ctrl):
    ctrl._repo.load_credential = AsyncMock(return_value=None)
    received = []
    ctrl.netease_auth_changed.connect(received.append)
    await ctrl.init()
    assert ctrl._client is None
    assert received == []


async def test_init_with_saved_cookies_builds_client(ctrl):
    ctrl._repo.load_credential = AsyncMock(
        return_value={"MUSIC_U": "abc", "__csrf": "xyz"}
    )
    received = []
    ctrl.netease_auth_changed.connect(received.append)
    await ctrl.init()
    assert ctrl._client is not None
    assert received == [True]


async def test_play_track_calls_vlc_play(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client

    t = _track()
    await ctrl.play_track(t)

    mock_client.get_stream_url.assert_awaited_once_with(t)
    assert hasattr(fake_vlc, "_last_url")
    assert fake_vlc._last_url == "https://cdn.example.com/a.mp3"
    assert ctrl._player.state.status == "playing"


async def test_play_track_error_sets_error_state(ctrl):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(side_effect=RuntimeError("timeout"))
    ctrl._client = mock_client

    await ctrl.play_track(_track())
    assert ctrl._player.state.status == "error"


async def test_toggle_play_pause_from_playing(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client
    await ctrl.play_track(_track())

    assert ctrl._player.state.status == "playing"
    ctrl.toggle_play_pause()
    assert ctrl._player.state.status == "paused"


async def test_toggle_play_pause_from_paused_resumes(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client
    await ctrl.play_track(_track())
    ctrl.toggle_play_pause()   # → paused
    ctrl.toggle_play_pause()   # → playing
    assert ctrl._player.state.status == "playing"


async def test_play_next_stops_when_queue_exhausted(ctrl, fake_vlc):
    mock_client = MagicMock()
    mock_client.get_stream_url = AsyncMock(return_value="https://cdn.example.com/a.mp3")
    ctrl._client = mock_client
    await ctrl.play_track(_track())   # queue=[t], index=0

    # next() with repeat_mode="none" returns None → stop
    await ctrl.play_next()
    assert ctrl._player.state.status == "idle"


async def test_search_emits_results(ctrl):
    mock_client = MagicMock()
    tracks = [_track(id="1"), _track(id="2")]
    mock_client.search = AsyncMock(return_value=tracks)
    ctrl._client = mock_client

    received = []
    ctrl.search_results_ready.connect(received.append)
    result = await ctrl.search("test")

    assert result == tracks
    assert len(received) == 1
    assert received[0] == tracks


async def test_search_returns_empty_when_not_authenticated(ctrl):
    ctrl._client = None
    result = await ctrl.search("test")
    assert result == []


async def test_is_netease_authenticated_property(ctrl):
    assert ctrl.is_netease_authenticated is False
    ctrl._client = MagicMock()
    assert ctrl.is_netease_authenticated is True
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/msomnia/Library/CloudStorage/OneDrive-Personal/1MSomnia/code/SomniaPlayer
python3 -m pytest tests/test_app_controller.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'core.app_controller'`

- [ ] **Step 3: 写 `core/app_controller.py`**

```python
from __future__ import annotations
import asyncio
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import Track, PlayerState
from core.player import UnifiedPlayer
from core.queue import PlayQueue
from core.vlc_backend import VLCBackend
from db.repository import AppRepository
from platforms.netease.auth import NeteaseAuth
from platforms.netease.client import NeteaseClient


class AppController(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._repo = AppRepository()
        self._auth = NeteaseAuth(self._repo)
        self._client: NeteaseClient | None = None
        self._player = UnifiedPlayer()
        self._vlc = VLCBackend()
        self._queue = PlayQueue()
        self._wire_internal()

    @property
    def is_netease_authenticated(self) -> bool:
        return self._client is not None

    def _wire_internal(self) -> None:
        self._vlc.position_changed.connect(self._player.update_position)
        self._vlc.end_reached.connect(
            lambda: asyncio.ensure_future(self.play_next())
        )
        self._vlc.error_occurred.connect(self._player.on_load_error)
        self._player.state_changed.connect(self.state_changed)
        self._player.position_changed.connect(self.position_changed)

    async def init(self) -> None:
        await self._repo.init()
        cookies = await self._auth.load_cookies()
        if cookies:
            self._client = NeteaseClient(cookies)
            self.netease_auth_changed.emit(True)

    async def ensure_netease_auth(self, parent=None) -> bool:
        if self._client is not None:
            return True
        cookies = await self._auth.login(parent)
        if cookies:
            self._client = NeteaseClient(cookies)
            self.netease_auth_changed.emit(True)
            return True
        return False

    async def search(self, query: str) -> list[Track]:
        if not self._client:
            return []
        tracks = await self._client.search(query)
        self.search_results_ready.emit(tracks)
        return tracks

    async def play_track(self, track: Track) -> None:
        self._queue.set_tracks([track], 0)
        self._player.load(track)
        try:
            url = await self._client.get_stream_url(track)
            self._vlc.play(url)
            self._player.on_load_success()
        except Exception as exc:
            self._player.on_load_error(str(exc))

    def toggle_play_pause(self) -> None:
        status = self._player.state.status
        if status == "playing":
            self._vlc.pause()
            self._player.pause()
        elif status == "paused":
            self._vlc.pause()
            self._player.resume()

    def seek(self, ms: int) -> None:
        self._vlc.seek(ms)
        self._player.seek(ms)

    async def play_next(self) -> None:
        repeat_mode = self._player.state.repeat_mode
        next_track = self._queue.next(repeat_mode)
        if next_track is None:
            self._vlc.stop()
            self._player.stop()
        else:
            await self.play_track(next_track)

    async def play_prev(self) -> None:
        prev_track = self._queue.previous()
        if prev_track is not None:
            await self.play_track(prev_track)

    async def get_initial_volume(self) -> int:
        val = await self._repo.get_setting("volume")
        return int(val) if val else 70

    async def close(self) -> None:
        await self._repo.close()
```

- [ ] **Step 4: 运行测试**

```bash
python3 -m pytest tests/test_app_controller.py -v
```

Expected: 9 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add core/app_controller.py tests/test_app_controller.py
git commit -m "feat: add AppController service coordinator"
```

---

## Task 2: TrackListWidget

**Files:**
- Create: `ui/components/track_list.py`
- Create: `tests/test_track_list.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_track_list.py
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from core.models import Track
from ui.components.track_list import TrackListWidget


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _t(tid: str) -> Track:
    return Track(id=tid, platform="netease", title=f"Song {tid}",
                 artist="Artist", artists=["Artist"], album="Alb",
                 album_cover_url="", duration_ms=180_000)


def test_track_list_creates_without_error(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)


def test_set_tracks_populates_list(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.set_tracks([_t("1"), _t("2"), _t("3")])
    assert w._list.count() == 3


def test_set_tracks_text_contains_title(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.set_tracks([_t("abc")])
    assert "Song abc" in w._list.item(0).text()


def test_set_tracks_stores_track_in_item(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    track = _t("x")
    w.set_tracks([track])
    stored = w._list.item(0).data(Qt.ItemDataRole.UserRole)
    assert stored == track


def test_clear_removes_all_items(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.set_tracks([_t("1"), _t("2")])
    w.clear()
    assert w._list.count() == 0


def test_show_loading_displays_placeholder(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.show_loading()
    assert w._list.count() == 0
    assert "搜索" in w._status_label.text() or "加载" in w._status_label.text()


def test_show_empty_displays_message(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    w.show_empty("无结果")
    assert "无结果" in w._status_label.text()


def test_track_selected_signal_on_double_click(qapp, qtbot):
    w = TrackListWidget()
    qtbot.addWidget(w)
    track = _t("1")
    w.set_tracks([track])
    received = []
    w.track_selected.connect(received.append)
    qtbot.mouseDClick(w._list.viewport(),
                      Qt.MouseButton.LeftButton,
                      pos=w._list.visualItemRect(w._list.item(0)).center())
    assert len(received) == 1
    assert received[0] == track
```

- [ ] **Step 2: 运行确认失败**

```bash
python3 -m pytest tests/test_track_list.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'ui.components.track_list'`

- [ ] **Step 3: 写 `ui/components/track_list.py`**

```python
from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from core.models import Track
from ui.theme import COLORS, FONTS


class TrackListWidget(QWidget):
    track_selected = pyqtSignal(object)  # Track

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status_label = QLabel()
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setObjectName("statusLabel")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        self._list = QListWidget()
        self._list.setObjectName("trackList")
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        self._apply_styles()

    def _on_double_click(self, item: QListWidgetItem) -> None:
        track: Track = item.data(Qt.ItemDataRole.UserRole)
        if track:
            self.track_selected.emit(track)

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def set_tracks(self, tracks: list[Track]) -> None:
        self._list.clear()
        self._status_label.hide()
        self._list.show()
        for track in tracks:
            text = f"{track.title}  —  {track.artist}  [{self._fmt(track.duration_ms)}]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, track)
            self._list.addItem(item)

    def clear(self) -> None:
        self._list.clear()
        self._status_label.hide()

    def show_loading(self) -> None:
        self._list.clear()
        self._list.hide()
        self._status_label.setText("搜索中…")
        self._status_label.show()

    def show_empty(self, msg: str = "无结果") -> None:
        self._list.clear()
        self._list.hide()
        self._status_label.setText(msg)
        self._status_label.show()

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #trackList {{
                background-color: {c['bg_base']};
                border: none;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #trackList::item {{
                padding: 10px 16px;
                border-bottom: 1px solid {c['divider']};
            }}
            #trackList::item:hover {{
                background-color: {c['bg_hover']};
            }}
            #trackList::item:selected {{
                background-color: {c['bg_elevated']};
            }}
            #statusLabel {{
                color: {c['text_muted']};
                font-size: {f['size_sm']}px;
                padding: 32px;
            }}
        """)
```

- [ ] **Step 4: 运行测试**

```bash
python3 -m pytest tests/test_track_list.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add ui/components/track_list.py tests/test_track_list.py
git commit -m "feat: add TrackListWidget with track_selected signal"
```

---

## Task 3: 更新 SidebarWidget

**Files:**
- Modify: `ui/components/sidebar.py`
- Modify: `tests/test_ui_components.py` (新增平台按钮测试)

- [ ] **Step 1: 在 `tests/test_ui_components.py` 末尾追加新测试**

```python
# 追加到 tests/test_ui_components.py 文件末尾
def test_sidebar_has_platform_login_requested_signal(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    received = []
    w.platform_login_requested.connect(received.append)
    w._platform_buttons["netease"].click()
    assert received == ["netease"]


def test_sidebar_set_platform_status_logged_in(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_platform_status("netease", True)
    assert "●" in w._platform_buttons["netease"].text()


def test_sidebar_set_platform_status_logged_out(qapp_instance, qtbot):
    w = SidebarWidget()
    qtbot.addWidget(w)
    w.set_platform_status("netease", True)
    w.set_platform_status("netease", False)
    assert "○" in w._platform_buttons["netease"].text()
```

- [ ] **Step 2: 运行确认新测试失败**

```bash
python3 -m pytest tests/test_ui_components.py -v -k "platform" 2>&1 | tail -10
```

Expected: `AttributeError: 'SidebarWidget' object has no attribute 'platform_login_requested'`

- [ ] **Step 3: 修改 `ui/components/sidebar.py`**

用以下完整内容替换该文件：

```python
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.theme import COLORS, FONTS


class SidebarWidget(QWidget):
    nav_changed = pyqtSignal(str)               # "home"|"search"|"library"|"settings"
    platform_login_requested = pyqtSignal(str)  # "netease"|"spotify"|"ytmusic"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(200)
        self._nav_buttons: dict[str, QPushButton] = {}
        self._platform_buttons: dict[str, QPushButton] = {}
        self._platform_names: dict[str, str] = {}
        self._setup_ui()
        self._apply_styles()

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
            layout.addWidget(self._make_platform_btn(platform_id, name))

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

    def _make_platform_btn(self, platform_id: str, name: str) -> QPushButton:
        btn = QPushButton(f"○  {name}")
        btn.setObjectName("platformButton")
        btn.clicked.connect(
            lambda: self.platform_login_requested.emit(platform_id)
        )
        self._platform_buttons[platform_id] = btn
        self._platform_names[platform_id] = name
        return btn

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        return line

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
            #platformButton {{
                text-align: left;
                padding: 6px 16px;
                background: transparent;
                border: none;
                color: {c['text_secondary']};
                font-size: {f['size_sm']}px;
                border-radius: 0;
            }}
            #platformButton:hover {{
                background-color: {c['bg_hover']};
                color: {c['text_primary']};
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
        """)

    def set_active_page(self, page_id: str) -> None:
        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)

    def set_platform_status(self, platform_id: str, logged_in: bool) -> None:
        btn = self._platform_buttons.get(platform_id)
        if not btn:
            return
        name = self._platform_names[platform_id]
        if logged_in:
            btn.setText(f"●  {name}")
            btn.setStyleSheet(f"color: {COLORS['accent']};")
        else:
            btn.setText(f"○  {name}")
            btn.setStyleSheet("")
```

- [ ] **Step 4: 运行所有 sidebar 相关测试**

```bash
python3 -m pytest tests/test_ui_components.py -v
```

Expected: 全部 PASSED（包含 3 个新测试）。

- [ ] **Step 5: Commit**

```bash
git add ui/components/sidebar.py tests/test_ui_components.py
git commit -m "feat: make sidebar platform rows clickable with login signal"
```

---

## Task 4: SearchPage

**Files:**
- Create: `ui/pages/search_page.py`
- Create: `tests/test_search_page.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_search_page.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication
from core.models import Track, PlayerState


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class _MockCtrl(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.is_netease_authenticated = True
        self.search = AsyncMock(return_value=[])
        self.play_track = AsyncMock()
        self.ensure_netease_auth = AsyncMock(return_value=True)


def _track(tid="1") -> Track:
    return Track(id=tid, platform="netease", title=f"Song {tid}",
                 artist="A", artists=["A"], album="Alb",
                 album_cover_url="", duration_ms=180_000)


def test_search_page_creates(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    w = SearchPage(ctrl)
    qtbot.addWidget(w)


def test_search_page_has_search_input(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    w = SearchPage(ctrl)
    qtbot.addWidget(w)
    assert w._search_input is not None


def test_search_results_signal_populates_list(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    w = SearchPage(ctrl)
    qtbot.addWidget(w)
    tracks = [_track("1"), _track("2")]
    ctrl.search_results_ready.emit(tracks)
    assert w._track_list._list.count() == 2


async def test_track_selected_calls_play_track(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    w = SearchPage(ctrl)
    qtbot.addWidget(w)
    t = _track("42")
    w._track_list.track_selected.emit(t)
    # Give event loop a tick
    await asyncio.sleep(0)
    ctrl.play_track.assert_awaited_once_with(t)


async def test_do_search_calls_ctrl_search(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    w = SearchPage(ctrl)
    qtbot.addWidget(w)
    await w._do_search("hello")
    ctrl.search.assert_awaited_once_with("hello")


async def test_do_search_skips_empty_query(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    w = SearchPage(ctrl)
    qtbot.addWidget(w)
    await w._do_search("  ")
    ctrl.search.assert_not_awaited()


async def test_do_search_triggers_login_when_not_authenticated(qapp, qtbot):
    from ui.pages.search_page import SearchPage
    ctrl = _MockCtrl()
    ctrl.is_netease_authenticated = False
    w = SearchPage(ctrl)
    qtbot.addWidget(w)
    await w._do_search("hello")
    ctrl.ensure_netease_auth.assert_awaited_once()
```

- [ ] **Step 2: 运行确认失败**

```bash
python3 -m pytest tests/test_search_page.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'ui.pages.search_page'`

- [ ] **Step 3: 写 `ui/pages/search_page.py`**

```python
from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit
from PyQt6.QtCore import QTimer
from ui.components.track_list import TrackListWidget
from ui.theme import COLORS, FONTS


class SearchPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._on_timer_fired)
        self._setup_ui()
        ctrl.search_results_ready.connect(self._track_list.set_tracks)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 0)
        layout.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索网易云音乐…")
        self._search_input.setObjectName("searchInput")
        self._search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._search_input)

        self._track_list = TrackListWidget()
        self._track_list.track_selected.connect(
            lambda t: asyncio.ensure_future(self._ctrl.play_track(t))
        )
        layout.addWidget(self._track_list, stretch=1)

        self._apply_styles()

    def _on_text_changed(self, text: str) -> None:
        self._debounce.start()

    def _on_timer_fired(self) -> None:
        asyncio.ensure_future(self._do_search(self._search_input.text()))

    async def _do_search(self, query: str) -> None:
        query = query.strip()
        if not query:
            return
        if not self._ctrl.is_netease_authenticated:
            ok = await self._ctrl.ensure_netease_auth(self)
            if not ok:
                return
        self._track_list.show_loading()
        await self._ctrl.search(query)

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #searchInput {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                padding: 8px 14px;
            }}
            #searchInput:focus {{
                border-color: {c['accent']};
            }}
        """)
```

- [ ] **Step 4: 运行测试**

```bash
python3 -m pytest tests/test_search_page.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add ui/pages/search_page.py tests/test_search_page.py
git commit -m "feat: add SearchPage with debounced search and track list"
```

---

## Task 5: 接线 MainWindow + 更新 main.py

**Files:**
- Modify: `ui/app_window.py`
- Modify: `tests/test_ui_components.py` (MainWindow 测试需传入 mock ctrl)
- Modify: `main.py`

- [ ] **Step 1: 在 `tests/test_ui_components.py` 顶部添加 import 并更新 MainWindow fixture**

在文件顶部现有 import 后添加：

```python
from unittest.mock import MagicMock
from PyQt6.QtCore import QObject, pyqtSignal
from core.models import PlayerState


class _MockCtrl(QObject):
    state_changed = pyqtSignal(PlayerState)
    position_changed = pyqtSignal(int)
    search_results_ready = pyqtSignal(list)
    netease_auth_changed = pyqtSignal(bool)
    is_netease_authenticated = False

    def toggle_play_pause(self): pass
    def seek(self, ms): pass
```

然后将所有 `MainWindow()` 调用改为 `MainWindow(_MockCtrl())`：

```python
# test_main_window_title 中
def test_main_window_title(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    assert w.windowTitle() == "SomniaMusicPlayer"


def test_main_window_has_sidebar_and_bar(qapp_instance, qtbot):
    w = MainWindow(_MockCtrl())
    qtbot.addWidget(w)
    assert w.sidebar is not None
    assert w.now_playing is not None
    assert w.content is not None
```

- [ ] **Step 2: 运行确认这两个测试现在失败（MainWindow 还不接收 ctrl 参数）**

```bash
python3 -m pytest tests/test_ui_components.py::test_main_window_title tests/test_ui_components.py::test_main_window_has_sidebar_and_bar -v 2>&1 | tail -10
```

Expected: `TypeError: MainWindow.__init__() takes 1 positional argument but 2 were given`

- [ ] **Step 3: 用以下内容完整替换 `ui/app_window.py`**

```python
from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
)
from ui.theme import COLORS
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.pages.search_page import SearchPage


class MainWindow(QMainWindow):
    def __init__(self, ctrl) -> None:
        super().__init__()
        self._ctrl = ctrl
        self.setWindowTitle("SomniaMusicPlayer")
        self.setMinimumSize(900, 600)
        self._setup_ui()
        self._apply_styles()
        self._wire_signals()
        self.sidebar.set_active_page("home")

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = SidebarWidget()
        self.sidebar.nav_changed.connect(self._on_nav)
        self.sidebar.platform_login_requested.connect(self._on_platform_login)
        body.addWidget(self.sidebar)

        self.content = QStackedWidget()
        self.content.setObjectName("contentArea")

        self._search_page = SearchPage(self._ctrl)
        self._page_map: dict[str, int] = {
            "search": self.content.addWidget(self._search_page),
        }

        body.addWidget(self.content, stretch=1)
        root.addLayout(body, stretch=1)

        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

    def _wire_signals(self) -> None:
        ctrl = self._ctrl
        ctrl.state_changed.connect(self.now_playing.update_state)
        ctrl.position_changed.connect(self.now_playing.update_position)
        ctrl.netease_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("netease", ok)
        )
        self.now_playing.play_pause_clicked.connect(ctrl.toggle_play_pause)
        self.now_playing.seek_requested.connect(ctrl.seek)
        self.now_playing.next_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_next())
        )
        self.now_playing.prev_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_prev())
        )
        self.now_playing.volume_changed.connect(
            lambda v: asyncio.ensure_future(
                self._ctrl._repo.set_setting("volume", str(v))
            )
        )

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)
        if page_id in self._page_map:
            self.content.setCurrentIndex(self._page_map[page_id])

    def _on_platform_login(self, platform_id: str) -> None:
        if platform_id == "netease":
            asyncio.ensure_future(self._ctrl.ensure_netease_auth(self))

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

- [ ] **Step 4: 用以下内容完整替换 `main.py`**

```python
from __future__ import annotations
import asyncio
import sys
from PyQt6.QtWidgets import QApplication
import qasync
from core.app_controller import AppController
from ui.app_window import MainWindow


async def _run(app: QApplication) -> None:
    ctrl = AppController()
    await ctrl.init()

    window = MainWindow(ctrl)
    volume = await ctrl.get_initial_volume()
    window.now_playing.set_volume(volume)
    ctrl._vlc.set_volume(volume)

    window.show()

    closed: asyncio.Future = asyncio.get_event_loop().create_future()
    app.lastWindowClosed.connect(
        lambda: closed.set_result(None) if not closed.done() else None
    )
    try:
        await closed
    finally:
        await ctrl.close()


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

- [ ] **Step 5: 运行全量测试**

```bash
python3 -m pytest -v
```

Expected: 全部 PASSED（77 原有 + 新增约 27 = 约 104 tests）。

- [ ] **Step 6: Commit**

```bash
git add ui/app_window.py main.py tests/test_ui_components.py
git commit -m "feat: wire MainWindow with AppController, SearchPage, and playback signals"
```

---

## Task 6: 安装 python-vlc 并烟雾测试

- [ ] **Step 1: 确认 VLC 应用已安装**

```bash
ls /Applications/VLC.app 2>/dev/null && echo "VLC installed" || echo "Need to install VLC"
```

若未安装，从 https://www.videolan.org/vlc/ 下载安装 macOS 版 VLC。

- [ ] **Step 2: 安装 python-vlc**

```bash
pip3 install python-vlc
python3 -c "import vlc; print(vlc.Instance())"
```

Expected: 输出类似 `<vlc.Instance object at 0x...>` 而不是报错。

- [ ] **Step 3: 启动应用验证 UI**

```bash
python3 main.py
```

Expected:
- 深色主窗口出现，左侧边栏、底部播放栏正常显示
- 侧边栏"网易云"为按钮（可点击）
- 点击"网易云"弹出登录 WebView 窗口
- 导航到"搜索"后，搜索框出现
- 搜索框输入关键词后，列表显示结果（需已登录）

- [ ] **Step 4: 最终 commit**

```bash
git add requirements.txt  # 若有更新
git commit -m "chore: confirm python-vlc dependency for playback"
```

---

## Self-Review

**Spec 覆盖检查：**
- ✅ 侧边栏登录入口 → Task 3
- ✅ AppController 协调层 → Task 1
- ✅ TrackListWidget → Task 2
- ✅ SearchPage + 400ms 防抖 → Task 4
- ✅ MainWindow 接线（state_changed, position_changed, play_pause, seek, next, prev）→ Task 5
- ✅ play_next 队列末尾 → stop → Task 1 (`play_next_stops_when_queue_exhausted`)

**类型一致性检查：**
- `AppController.get_initial_volume()` → `int` ✅ (main.py 直接用)
- `VLCBackend.set_volume(int)` ✅ (main.py 初始化音量时调用)
- `TrackListWidget._list` → `QListWidget` ✅ (test_track_list.py 直接访问)
- `SearchPage._search_input` → `QLineEdit` ✅ (test_search_page.py 访问)
- `SearchPage._track_list` → `TrackListWidget` ✅
- `SidebarWidget._platform_buttons` → `dict[str, QPushButton]` ✅ (test_ui_components.py 访问)
