from __future__ import annotations
import asyncio
import ctypes
import ctypes.util
import logging
import sys
import time
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QLabel,
    QLineEdit, QTextEdit, QPlainTextEdit, QApplication, QMenuBar, QMessageBox,
)
from ui.components.playlist_picker_popup import PlaylistPickerPopup
from PyQt6.QtCore import Qt, QRectF, QTimer, QEvent, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QKeySequence, QPainter, QPainterPath, QPixmap
from ui.theme import COLORS, FONTS
from ui.frosted import paint_frosted_panel
from ui.components.sidebar import SidebarWidget
from ui.components.now_playing_bar import NowPlayingBar
from ui.components.lyrics_view import LyricsView
from ui.components.queue_panel import QueuePanel
from ui.pages.search_page import SearchPage
from ui.pages.home_page import HomePage
from ui.pages.library_page import LibraryPage
from ui.pages.settings_page import SettingsPage
from ui.pages.standby_page import StandbyPage
from ui.pages.artist_page import ArtistPage

logger = logging.getLogger(__name__)

_PLATFORM_LABELS = {
    "netease": "网易云音乐",
    "spotify": "Spotify",
    "ytmusic": "YouTube Music",
}


_INPUT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)


class _GlobalKeyFilter(QObject):
    """App-level event filter: intercepts Space and tracks user activity."""

    activity = pyqtSignal()

    _ACTIVITY_EVENTS = frozenset({
        QEvent.Type.MouseMove,
        QEvent.Type.MouseButtonPress,
        QEvent.Type.KeyPress,
        QEvent.Type.Wheel,
    })

    def __init__(self, ctrl) -> None:
        super().__init__()
        self._ctrl = ctrl

    def eventFilter(self, obj, event) -> bool:
        if event.type() in self._ACTIVITY_EVENTS:
            self.activity.emit()
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space:
                focus = QApplication.focusWidget()
                if not isinstance(focus, _INPUT_TYPES):
                    self._ctrl.toggle_play_pause()
                    return True  # consume — don't deliver to focused widget
        return False


class _ErrorToast(QLabel):
    """Transient overlay that shows '歌曲无法播放' and auto-hides after 3 s."""

    _DURATION_MS = 3000

    def __init__(self, parent: QWidget) -> None:
        super().__init__("  ✕  歌曲无法播放  ", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(40)
        self.hide()
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            _ErrorToast, QLabel {{
                background-color: {c['bg_elevated']};
                border: 1px solid #FF4444;
                border-radius: 8px;
                color: #FF6B6B;
                font-size: {f['size_sm']}px;
                font-weight: bold;
            }}
        """)

    def popup(self) -> None:
        p = self.parent()
        w = 220
        self.setGeometry((p.width() - w) // 2, 20, w, 40)
        self.show()
        self.raise_()
        QTimer.singleShot(self._DURATION_MS, self.hide)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.isVisible():
            p = self.parent()
            self.move((p.width() - self.width()) // 2, 20)


class _StatusToast(QLabel):
    _DURATION_MS = 2200

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(36)
        self.hide()

    def popup(self, message: str, success: bool = True) -> None:
        c, f = COLORS, FONTS
        border = COLORS["accent"] if success else "#FF4444"
        text = COLORS["text_primary"] if success else "#FF6B6B"
        self.setText(f"  {message}  ")
        self.setStyleSheet(f"""
            _StatusToast, QLabel {{
                background-color: {c['bg_elevated']};
                border: 1px solid {border};
                border-radius: 8px;
                color: {text};
                font-size: {f['size_sm']}px;
                font-weight: bold;
            }}
        """)
        p = self.parent()
        w = min(max(180, self.fontMetrics().horizontalAdvance(message) + 48), 360)
        self.setGeometry((p.width() - w) // 2, 68, w, 36)
        self.show()
        self.raise_()
        QTimer.singleShot(self._DURATION_MS, self.hide)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self.isVisible():
            p = self.parent()
            self.move((p.width() - self.width()) // 2, 68)


class _TrafficLightButton(QWidget):
    """Single circular traffic-light button drawn via QPainter."""

    clicked = pyqtSignal()

    _COLORS: dict[str, tuple[str, str]] = {
        "close":    ("#FF5F57", "#C0403C"),
        "minimize": ("#FEBC2E", "#C09020"),
        "zoom":     ("#28C840", "#1A9A2D"),
    }

    def __init__(self, kind: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        normal, dark = self._COLORS[kind]
        self._normal = QColor(normal)
        self._dark   = QColor(dark)
        self._pressed = False

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            was, self._pressed = self._pressed, False
            self.update()
            if was and self.rect().contains(event.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._dark if self._pressed else self._normal)
        p.drawEllipse(self.rect())


class _TrafficLightsBar(QWidget):
    """Custom title-bar strip: traffic-light buttons + drag area."""

    def __init__(self, main_window: "MainWindow", parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setAutoFillBackground(False)
        self._main = main_window
        self._drag_offset = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 0, 8)
        layout.setSpacing(8)
        for kind in ("close", "minimize", "zoom"):
            btn = _TrafficLightButton(kind, self)
            if kind == "close":
                btn.clicked.connect(self._main.close)
            elif kind == "minimize":
                btn.clicked.connect(self._main.showMinimized)
            else:
                btn.clicked.connect(self._toggle_zoom)
            layout.addWidget(btn)
        layout.addStretch()

    def _toggle_zoom(self) -> None:
        if self._main.isMaximized():
            self._main.showNormal()
        else:
            self._main.showMaximized()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._main.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if (self._drag_offset is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            self._main.move(
                event.globalPosition().toPoint() - self._drag_offset
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_zoom()
        super().mouseDoubleClickEvent(event)


class _AppRoot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("appRoot")
        self.setAutoFillBackground(False)
        self._background_path = ""
        self._background_pixmap = QPixmap()

    def set_background_image(self, path: str) -> None:
        path = path.strip()
        self._background_path = path
        self._background_pixmap = QPixmap(path) if path else QPixmap()
        self.update()
        for child in self.findChildren(QWidget):
            child.update()

    def background_pixmap(self) -> QPixmap:
        return self._background_pixmap

    _CORNER_RADIUS = 10.0  # matches macOS standard window corner radius

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        win = self.window()
        rounded = (
            sys.platform == "darwin"
            and win is not None
            and not win.isFullScreen()
        )
        if rounded:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self._CORNER_RADIUS, self._CORNER_RADIUS)
            painter.setClipPath(path)

        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._background_pixmap.isNull():
            return

        source = self._background_pixmap
        scaled = source.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)


class _FrostedStackedWidget(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("contentArea")
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        paint_frosted_panel(self, painter)
        super().paintEvent(event)


def _apply_macos_window_style(win_id: int) -> None:
    """Apply dark appearance, shadow and resize capability to a frameless macOS window.

    FramelessWindowHint sets NSWindowStyleMaskBorderless (=0) which removes
    the shadow and resize handles.  This restores both without adding a
    native titlebar.

    Uses ctypes to call the Objective-C runtime directly; no PyObjC required.
    """
    if sys.platform != "darwin":
        return
    try:
        objc_lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))

        objc_lib.objc_getClass.restype = ctypes.c_void_p
        objc_lib.objc_getClass.argtypes = [ctypes.c_char_p]
        objc_lib.sel_registerName.restype = ctypes.c_void_p
        objc_lib.sel_registerName.argtypes = [ctypes.c_char_p]

        def _sel(name: bytes) -> ctypes.c_void_p:
            return objc_lib.sel_registerName(name)

        def _send(receiver, selector: bytes, *args,
                  restype=ctypes.c_void_p, argtypes: list | None = None):
            objc_lib.objc_msgSend.restype = restype
            objc_lib.objc_msgSend.argtypes = (
                [ctypes.c_void_p, ctypes.c_void_p] + (argtypes or [])
            )
            return objc_lib.objc_msgSend(receiver, _sel(selector), *args)

        ns_view = ctypes.c_void_p(win_id)
        ns_window = _send(ns_view, b"window")

        # Dark appearance
        NSString = objc_lib.objc_getClass(b"NSString")
        name_str = _send(NSString, b"stringWithUTF8String:",
                         b"NSAppearanceNameDarkAqua", argtypes=[ctypes.c_char_p])
        NSAppearance = objc_lib.objc_getClass(b"NSAppearance")
        dark_appearance = _send(NSAppearance, b"appearanceNamed:", name_str,
                                argtypes=[ctypes.c_void_p])
        _send(ns_window, b"setAppearance:", dark_appearance,
              restype=None, argtypes=[ctypes.c_void_p])

        # Restore shadow (removed by FramelessWindowHint / NSWindowStyleMaskBorderless)
        _send(ns_window, b"setHasShadow:", ctypes.c_bool(True),
              restype=None, argtypes=[ctypes.c_bool])

        # Add NSWindowStyleMaskResizable (1<<3) so edges can still be dragged
        objc_lib.objc_msgSend.restype = ctypes.c_ulong
        objc_lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        current_mask = objc_lib.objc_msgSend(ns_window, _sel(b"styleMask"))
        _send(ns_window, b"setStyleMask:",
              ctypes.c_ulong(current_mask | 8),
              restype=None, argtypes=[ctypes.c_ulong])

        # Rounded corners via CALayer — clips ALL child widgets at the compositor
        # level so both top and bottom corners are rounded uniformly.
        _send(ns_view, b"setWantsLayer:", ctypes.c_bool(True),
              restype=None, argtypes=[ctypes.c_bool])
        layer = _send(ns_view, b"layer")
        objc_lib.objc_msgSend.restype = None
        objc_lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double]
        objc_lib.objc_msgSend(layer, _sel(b"setCornerRadius:"),
                              ctypes.c_double(_AppRoot._CORNER_RADIUS))
        _send(layer, b"setMasksToBounds:", ctypes.c_bool(True),
              restype=None, argtypes=[ctypes.c_bool])

    except Exception as exc:
        logger.debug("macOS window style unavailable: %s", exc)


def _macos_set_corner_radius(win_id: int, radius: float) -> None:
    """Update the CALayer corner radius on the Qt NSView (macOS only)."""
    if sys.platform != "darwin":
        return
    try:
        objc_lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc_lib.sel_registerName.restype = ctypes.c_void_p
        objc_lib.sel_registerName.argtypes = [ctypes.c_char_p]

        def _sel(name: bytes) -> ctypes.c_void_p:
            return objc_lib.sel_registerName(name)

        def _send(receiver, selector: bytes, *args,
                  restype=ctypes.c_void_p, argtypes: list | None = None):
            objc_lib.objc_msgSend.restype = restype
            objc_lib.objc_msgSend.argtypes = (
                [ctypes.c_void_p, ctypes.c_void_p] + (argtypes or [])
            )
            return objc_lib.objc_msgSend(receiver, _sel(selector), *args)

        ns_view = ctypes.c_void_p(win_id)
        layer = _send(ns_view, b"layer")
        objc_lib.objc_msgSend.restype = None
        objc_lib.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double]
        objc_lib.objc_msgSend(layer, _sel(b"setCornerRadius:"), ctypes.c_double(radius))
        _send(layer, b"setMasksToBounds:", ctypes.c_bool(radius > 0),
              restype=None, argtypes=[ctypes.c_bool])
    except Exception as exc:
        logger.debug("Corner radius update failed: %s", exc)


class MainWindow(QMainWindow):
    def __init__(self, ctrl) -> None:
        super().__init__()
        if sys.platform == "darwin":
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._ctrl = ctrl
        self.setWindowTitle("Omnia")
        self.setMinimumSize(900, 600)
        self._setup_menu_bar()
        self._setup_ui()
        self._apply_styles()
        self._wire_signals()
        self.sidebar.set_active_page("home")
        self._dark_titlebar_done = False
        self._preload_scheduled = False
        self._auto_update_enabled = True
        self._key_filter = _GlobalKeyFilter(ctrl)
        QApplication.instance().installEventFilter(self._key_filter)

        self._idle_timeout_ms: int = 5 * 60 * 1000  # default 5 min
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._key_filter.activity.connect(self._reset_idle_timer)
        self._idle_timer.start(self._idle_timeout_ms)

    def changeEvent(self, event) -> None:  # type: ignore[override]
        super().changeEvent(event)
        if (sys.platform == "darwin"
                and event.type() == QEvent.Type.WindowStateChange
                and self._dark_titlebar_done):
            is_fs = bool(self.windowState() & Qt.WindowState.WindowFullScreen)
            radius = 0.0 if is_fs else _AppRoot._CORNER_RADIUS
            _macos_set_corner_radius(int(self.winId()), radius)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._dark_titlebar_done:
            self._dark_titlebar_done = True
            _apply_macos_window_style(int(self.winId()))
            if hasattr(self._ctrl, "enable_macos_status_item"):
                self._ctrl.enable_macos_status_item()
        if not self._preload_scheduled:
            self._preload_scheduled = True
            QTimer.singleShot(800, self._preload_authenticated_platforms)
            # Show local version immediately, then auto-check after 15 s
            self._settings_page.init_version_label()
            QTimer.singleShot(15_000, self._schedule_auto_update_check)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "_standby_page") and hasattr(self, "_app_root"):
            central = self._app_root
            np_h = self.now_playing.height()
            self._standby_page.setGeometry(0, 0, central.width(), central.height() - np_h)

    def _setup_menu_bar(self) -> None:
        if sys.platform == "darwin":
            menu_bar = QMenuBar()
            menu_bar.setNativeMenuBar(True)
            self._menu_bar = menu_bar
        else:
            menu_bar = self.menuBar()

        app_name = self.windowTitle()

        app_menu = menu_bar.addMenu(app_name)
        about_action = QAction(f"About {app_name}", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self._show_about_dialog)
        app_menu.addAction(about_action)

        settings_action = QAction("Settings...", self)
        settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.triggered.connect(
            lambda checked=False: self._on_nav("settings")
        )
        app_menu.addAction(settings_action)

        app_menu.addSeparator()

        quit_action = QAction(f"Quit {app_name}", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(QApplication.instance().quit)
        app_menu.addAction(quit_action)

        view_menu = menu_bar.addMenu("View")
        for label, page_id in [
            ("Home", "home"),
            ("Search", "search"),
            ("Library", "library"),
            ("Lyrics", "lyrics"),
            ("Settings", "settings"),
        ]:
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked=False, target=page_id: self._on_nav(target)
            )
            view_menu.addAction(action)
        view_menu.addSeparator()
        standby_action = QAction("Toggle Standby", self)
        standby_action.triggered.connect(self._toggle_standby)
        view_menu.addAction(standby_action)

        playback_menu = menu_bar.addMenu("Playback")
        play_pause_action = QAction("Play/Pause", self)
        play_pause_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        play_pause_action.triggered.connect(self._ctrl.toggle_play_pause)
        playback_menu.addAction(play_pause_action)

        previous_action = QAction("Previous Track", self)
        previous_action.triggered.connect(
            lambda: asyncio.ensure_future(self._ctrl.play_prev())
        )
        playback_menu.addAction(previous_action)

        next_action = QAction("Next Track", self)
        next_action.triggered.connect(
            lambda: asyncio.ensure_future(self._ctrl.play_next())
        )
        playback_menu.addAction(next_action)
        playback_menu.addSeparator()

        queue_action = QAction("Show Queue", self)
        queue_action.triggered.connect(self._show_queue)
        playback_menu.addAction(queue_action)

        window_menu = menu_bar.addMenu("Window")
        minimize_action = QAction("Minimize", self)
        minimize_action.setShortcut(QKeySequence("Ctrl+M"))
        minimize_action.triggered.connect(self.showMinimized)
        window_menu.addAction(minimize_action)

        zoom_action = QAction("Zoom", self)
        zoom_action.triggered.connect(self._toggle_zoom)
        window_menu.addAction(zoom_action)

        window_menu.addSeparator()
        bring_front_action = QAction("Bring All to Front", self)
        bring_front_action.triggered.connect(self._bring_to_front)
        window_menu.addAction(bring_front_action)

        help_menu = menu_bar.addMenu("Help")
        help_action = QAction(f"{app_name} Help", self)
        help_action.triggered.connect(self._show_help_dialog)
        help_menu.addAction(help_action)

    def _toggle_zoom(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _bring_to_front(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _show_about_dialog(self) -> None:
        app = QApplication.instance()
        name = self.windowTitle()
        version = app.applicationVersion() if app else "0.1.0"
        QMessageBox.about(
            self,
            f"About {name}",
            f"{name}\nVersion {version}",
        )

    def _show_help_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Omnia Help",
            "Use the sidebar and bottom playback bar as usual. The menu mirrors "
            "the same navigation and playback controls.",
        )

    def _setup_ui(self) -> None:
        central = _AppRoot()
        self._app_root = central
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if sys.platform == "darwin":
            self._titlebar = _TrafficLightsBar(self, central)
            root.addWidget(self._titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(12, 8, 12, 12)
        body.setSpacing(12)

        self.sidebar = SidebarWidget()
        self.sidebar.nav_changed.connect(self._on_nav)
        self.sidebar.platform_login_requested.connect(self._on_platform_login)
        body.addWidget(self.sidebar)

        self.content = _FrostedStackedWidget()

        self._home_page = HomePage(self._ctrl)
        self._search_page = SearchPage(self._ctrl)
        self._library_page = LibraryPage(self._ctrl)
        self._settings_page = SettingsPage(self._ctrl)
        self._lyrics_view = LyricsView()
        self._artist_page = ArtistPage(self._ctrl)

        self._page_map: dict[str, int] = {
            "home":     self.content.addWidget(self._home_page),
            "search":   self.content.addWidget(self._search_page),
            "library":  self.content.addWidget(self._library_page),
            "settings": self.content.addWidget(self._settings_page),
            "lyrics":   self.content.addWidget(self._lyrics_view),
            "artist":   self.content.addWidget(self._artist_page),
        }
        self._prev_page: str = "home"
        self._page_before_artist: str = "home"

        body.addWidget(self.content, stretch=1)
        root.addLayout(body, stretch=1)

        self.now_playing = NowPlayingBar()
        root.addWidget(self.now_playing)

        # Queue panel (lazy-created popup)
        self._queue_panel: QueuePanel | None = None

        # Error toast — child of central so it overlays the content area
        self._error_toast = _ErrorToast(central)
        self._status_toast = _StatusToast(central)
        self._last_error_skip: float = 0.0  # guard against rapid cascades

        # Standby page — full-body overlay, hidden by default
        self._standby_page = StandbyPage(self._ctrl, central)
        central_h = central.height()
        np_h = self.now_playing.height() if self.now_playing.height() > 0 else 90
        self._standby_page.setGeometry(0, 0, central.width() or 900, central_h - np_h or 510)

    def _wire_signals(self) -> None:
        ctrl = self._ctrl

        # Player state → UI
        ctrl.state_changed.connect(self.now_playing.update_state)
        ctrl.state_changed.connect(self._on_state_changed)
        ctrl.position_changed.connect(self.now_playing.update_position)
        ctrl.position_changed.connect(self._lyrics_view.update_position)
        ctrl.volume_changed.connect(self.now_playing.set_volume)

        # Auth status → sidebar + preload on login
        ctrl.netease_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("netease", ok)
        )
        ctrl.netease_auth_changed.connect(
            lambda ok: ok and self._preload_platform("netease")
        )
        ctrl.ytmusic_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("ytmusic", ok)
        )
        ctrl.ytmusic_auth_changed.connect(
            lambda ok: ok and self._preload_platform("ytmusic")
        )
        ctrl.spotify_auth_changed.connect(
            lambda ok: self.sidebar.set_platform_status("spotify", ok)
        )
        ctrl.spotify_auth_changed.connect(
            lambda ok: ok and self._preload_platform("spotify")
        )
        ctrl.profile_changed.connect(self.sidebar.set_display_name)
        ctrl.background_changed.connect(self._app_root.set_background_image)
        ctrl.settings_ready.connect(self._apply_standby_timeout_setting)
        ctrl.settings_ready.connect(self._apply_auto_update_setting)
        ctrl.update_status_ready.connect(self._on_update_status_for_auto)

        # Sidebar standby toggle
        self.sidebar.standby_requested.connect(self._toggle_standby)

        # Standby page data feeds
        ctrl.state_changed.connect(self._standby_page.on_state_changed)
        ctrl.cover_art_bytes.connect(self._standby_page.set_cover_art_bytes)
        ctrl.cover_color_ready.connect(self._standby_page.set_cover_color)
        ctrl.lyrics_ready.connect(self._standby_page.set_lyrics)
        ctrl.position_changed.connect(self._standby_page.update_position)

        # Lyrics & cover
        ctrl.lyrics_ready.connect(self._lyrics_view.set_lyrics)
        ctrl.cover_color_ready.connect(self._lyrics_view.set_cover_color)
        ctrl.cover_art_bytes.connect(self._lyrics_view.set_cover_art_bytes)
        ctrl.cover_art_bytes.connect(self.now_playing.set_cover_pixmap_from_bytes)

        # Sync initial auth state (ctrl.init() runs before MainWindow is built)
        self.sidebar.set_platform_status("netease", ctrl.is_netease_authenticated)
        self.sidebar.set_platform_status("ytmusic", ctrl.is_ytmusic_authenticated)
        self.sidebar.set_platform_status("spotify", ctrl.is_spotify_authenticated)
        self.sidebar.set_display_name(getattr(ctrl, "display_name", "Omnia"))
        self._app_root.set_background_image(
            getattr(ctrl, "background_image_path", "")
        )

        # Playback controls
        self.now_playing.play_pause_clicked.connect(ctrl.toggle_play_pause)
        self.now_playing.seek_requested.connect(ctrl.seek)
        self.now_playing.next_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_next())
        )
        self.now_playing.prev_clicked.connect(
            lambda: asyncio.ensure_future(ctrl.play_prev())
        )
        self.now_playing.volume_changed.connect(ctrl.set_volume)
        self.now_playing.shuffle_toggled.connect(ctrl.toggle_shuffle)
        self.now_playing.repeat_toggled.connect(ctrl.cycle_repeat_mode)

        # Lyrics & queue toggle
        self.now_playing.lyrics_toggled.connect(self._toggle_lyrics)
        self.now_playing.track_info_clicked.connect(self._show_lyrics)
        self.now_playing.queue_requested.connect(self._show_queue)
        self.now_playing.playlist_requested.connect(
            self._on_now_playing_playlist_requested
        )
        self._lyrics_view.back_requested.connect(self._toggle_lyrics)

        # Artist page
        self.now_playing.artist_clicked.connect(self._on_nowplaying_artist_clicked)
        ctrl.artist_ready.connect(self._artist_page.load_artist)
        ctrl.artist_tracks_ready.connect(self._artist_page.load_tracks)
        self._artist_page.back_requested.connect(self._on_artist_back)
        self._artist_page.play_track.connect(
            lambda t: asyncio.ensure_future(ctrl.play_track(t))
        )
        self._artist_page.queue_track.connect(ctrl.add_to_queue)
        self._artist_page.artist_clicked.connect(
            lambda t: self._navigate_to_artist(t.artist, t.platform)
        )
        self._home_page.artist_clicked.connect(
            lambda t: self._navigate_to_artist(t.artist, t.platform)
        )
        self._search_page.artist_clicked.connect(
            lambda t: self._navigate_to_artist(t.artist, t.platform)
        )
        self._library_page.artist_clicked.connect(
            lambda t: self._navigate_to_artist(t.artist, t.platform)
        )
        self._library_page.status_message.connect(self._status_toast.popup)
        self._home_page.playlist_requested.connect(self._request_add_to_playlist)
        self._search_page.playlist_requested.connect(self._request_add_to_playlist)

    # ── state handlers ────────────────────────────────────────────────────────

    def _on_state_changed(self, state) -> None:
        if state.current_track is None:
            self._lyrics_view.clear()
        elif state.status == "loading":
            self._lyrics_view.clear_cover_art()
        if state.status == "error":
            now = time.monotonic()
            if now - self._last_error_skip >= 2.0:
                self._last_error_skip = now
                self._error_toast.popup()
                QTimer.singleShot(
                    800,
                    lambda: asyncio.ensure_future(self._ctrl.play_next()),
                )

    # ── navigation ────────────────────────────────────────────────────────────

    def _on_nav(self, page_id: str) -> None:
        self.sidebar.set_active_page(page_id)
        if page_id == "lyrics":
            self._toggle_lyrics()
            return
        if page_id in self._page_map:
            self.content.setCurrentIndex(self._page_map[page_id])
            self.now_playing.set_lyrics_active(False)

    def _show_lyrics(self) -> None:
        if self.content.currentIndex() == self._page_map["lyrics"]:
            return
        self._save_prev_page()
        self.content.setCurrentIndex(self._page_map["lyrics"])
        self.now_playing.set_lyrics_active(True)

    def _toggle_lyrics(self) -> None:
        if self.content.currentIndex() == self._page_map["lyrics"]:
            idx = self._page_map.get(self._prev_page, self._page_map["home"])
            self.content.setCurrentIndex(idx)
            self.now_playing.set_lyrics_active(False)
        else:
            self._save_prev_page()
            self.content.setCurrentIndex(self._page_map["lyrics"])
            self.now_playing.set_lyrics_active(True)

    def _save_prev_page(self) -> None:
        current_idx = self.content.currentIndex()
        self._prev_page = next(
            (k for k, v in self._page_map.items()
             if v == current_idx and k != "lyrics"),
            "home",
        )

    def _on_nowplaying_artist_clicked(self) -> None:
        track = self._ctrl.current_state.current_track
        if track is None:
            return
        self._navigate_to_artist(track.artist, track.platform)

    def _navigate_to_artist(self, artist_name: str, platform: str) -> None:
        if not artist_name:
            return
        current_idx = self.content.currentIndex()
        self._page_before_artist = next(
            (k for k, v in self._page_map.items()
             if v == current_idx and k not in ("lyrics", "artist")),
            "home",
        )
        self.content.setCurrentIndex(self._page_map["artist"])
        self.now_playing.set_lyrics_active(False)
        asyncio.ensure_future(self._ctrl.load_artist(artist_name, platform))

    def _on_artist_back(self) -> None:
        idx = self._page_map.get(self._page_before_artist, self._page_map["home"])
        self.content.setCurrentIndex(idx)

    # ── queue panel ───────────────────────────────────────────────────────────

    def _show_queue(self) -> None:
        import time
        if self._queue_panel is None:
            self._queue_panel = QueuePanel(self._ctrl, self)
        # If the popup was just auto-closed because the user clicked this
        # button (Popup closes on press, clicked fires on release), skip
        # re-opening so the button acts as a proper toggle.
        if time.monotonic() - self._queue_panel.last_hide_time < 0.15:
            return
        self._queue_panel.refresh()
        btn = self.now_playing.queue_btn_global_rect()
        x = btn.right() - self._queue_panel.width()
        y = btn.top() - self._queue_panel.height() - 8
        self._queue_panel.move(x, y)
        self._queue_panel.show()

    # ── add to playlist ──────────────────────────────────────────────────────

    def _on_now_playing_playlist_requested(self) -> None:
        track = self._ctrl.current_state.current_track
        if track is None:
            return
        btn = self.now_playing.playlist_btn_global_rect()
        self._request_add_to_playlist(track, btn.bottomLeft())

    def _request_add_to_playlist(self, track, pos=None) -> None:
        asyncio.ensure_future(
            self._open_add_to_playlist_menu(track, pos or QCursor.pos())
        )

    async def _open_add_to_playlist_menu(self, track, pos) -> None:
        if not track:
            return
        if not self._is_platform_authenticated(track.platform):
            ok = await self._ensure_platform_auth(track.platform)
            if not ok:
                self._status_toast.popup("需要先登录对应平台", success=False)
                return

        popup = PlaylistPickerPopup(track.platform, parent=self)

        async def _on_selected(playlist) -> None:
            ok = await self._ctrl.add_track_to_playlist(track, playlist)
            if ok:
                self._status_toast.popup(f"已加入 {playlist.name}")
            else:
                msg = getattr(self._ctrl, "last_playlist_error", "") or "加入歌单失败"
                self._status_toast.popup(msg, success=False)

        popup.playlist_selected.connect(lambda p: asyncio.ensure_future(_on_selected(p)))
        popup.show_at(pos)

        try:
            playlists = await self._ctrl.get_addable_playlists(track.platform)
            popup.set_playlists(playlists)
        except Exception:
            popup.set_error("获取歌单失败")

    # ── platform login ────────────────────────────────────────────────────────

    # ── preload ───────────────────────────────────────────────────────────────

    def _preload_platform(self, platform: str) -> None:
        asyncio.ensure_future(self._ctrl.load_home(platform))
        asyncio.ensure_future(self._ctrl.load_library(platform))

    def _preload_authenticated_platforms(self) -> None:
        for platform, authenticated in [
            ("netease", self._ctrl.is_netease_authenticated),
            ("ytmusic", self._ctrl.is_ytmusic_authenticated),
            ("spotify", self._ctrl.is_spotify_authenticated),
        ]:
            if authenticated:
                self._preload_platform(platform)

    def _on_platform_login(self, platform_id: str) -> None:
        asyncio.ensure_future(self._open_platform_library(platform_id))

    async def _open_platform_library(self, platform_id: str) -> None:
        if not self._is_platform_authenticated(platform_id):
            ok = await self._ensure_platform_auth(platform_id)
            if not ok:
                self.sidebar.set_active_platform(None)
                return
        self._show_platform_library(platform_id)

    def _is_platform_authenticated(self, platform_id: str) -> bool:
        if platform_id == "netease":
            return self._ctrl.is_netease_authenticated
        if platform_id == "ytmusic":
            return self._ctrl.is_ytmusic_authenticated
        if platform_id == "spotify":
            return self._ctrl.is_spotify_authenticated
        return False

    async def _ensure_platform_auth(self, platform_id: str) -> bool:
        if platform_id == "netease":
            return await self._ctrl.ensure_netease_auth(self)
        if platform_id == "ytmusic":
            return await self._ctrl.ensure_ytmusic_auth(self)
        if platform_id == "spotify":
            return await self._ctrl.ensure_spotify_auth(self)
        return False

    def _show_platform_library(self, platform_id: str) -> None:
        self.sidebar.set_active_page("library")
        self.sidebar.set_active_platform(platform_id)
        self.content.setCurrentIndex(self._page_map["library"])
        self._library_page.set_platform(platform_id)
        self.now_playing.set_lyrics_active(False)

    def _toggle_standby(self) -> None:
        if self._standby_page.isVisible():
            self._standby_page.leave()
            self._reset_idle_timer()
        else:
            self._standby_page.enter()
            self._idle_timer.stop()

    def _reset_idle_timer(self) -> None:
        if self._idle_timeout_ms > 0 and not self._standby_page.isVisible():
            self._idle_timer.start(self._idle_timeout_ms)

    def _on_idle_timeout(self) -> None:
        if not self._standby_page.isVisible():
            self._standby_page.enter()

    def _apply_standby_timeout_setting(self, settings: dict) -> None:
        minutes = int(settings.get("auto_standby_minutes") or 5)
        self._idle_timeout_ms = minutes * 60 * 1000
        if self._idle_timeout_ms > 0:
            self._idle_timer.start(self._idle_timeout_ms)
        else:
            self._idle_timer.stop()

    def _apply_auto_update_setting(self, settings: dict) -> None:
        self._auto_update_enabled = (
            settings.get("auto_update") or "true"
        ).lower() == "true"

    def _schedule_auto_update_check(self) -> None:
        asyncio.ensure_future(self._ctrl.check_for_update())

    def _on_update_status_for_auto(self, status) -> None:
        if not status.available or not getattr(self, "_auto_update_enabled", True):
            return
        msgs = "\n".join(f"• {m}" for m in status.commit_messages) if status.commit_messages else ""
        body = f"发现新版本（{status.remote_short}），是否立即更新并重启？"
        if msgs:
            body += f"\n\n{msgs}"
        dlg = QMessageBox(self)
        dlg.setWindowTitle("发现新版本")
        dlg.setText(body)
        dlg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        dlg.setDefaultButton(QMessageBox.StandardButton.Yes)
        dlg.button(QMessageBox.StandardButton.Yes).setText("立即更新")
        dlg.button(QMessageBox.StandardButton.No).setText("稍后再说")
        if dlg.exec() == QMessageBox.StandardButton.Yes:
            asyncio.ensure_future(self._ctrl.apply_update())

    # ── styling ───────────────────────────────────────────────────────────────

    def _apply_styles(self) -> None:
        c = COLORS
        self.setStyleSheet(f"""
            QMainWindow, #appRoot {{
                background-color: #000000;
            }}
            QWidget {{
                font-family: "Inter", "SF Pro Display", sans-serif;
            }}
            #contentArea {{
                background-color: transparent;
                border-radius: 8px;
                border: none;
            }}
        """)
        QApplication.instance().setStyleSheet(f"""
            QAbstractItemView {{
                background-color: {c['bg_elevated']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                outline: 0;
                padding: 2px;
            }}
            QAbstractItemView::item:selected {{
                background-color: {c['accent']};
                color: #000000;
            }}
            QAbstractItemView::item:hover {{
                background-color: {c['bg_surface']};
            }}
        """)
