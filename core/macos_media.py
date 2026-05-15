from __future__ import annotations
import asyncio
import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Track

logger = logging.getLogger(__name__)

_STATUS_VISIBLE_TEXT_CHARS = 12
_STATUS_SCROLL_INTERVAL_MS = 500
_STATUS_SCROLL_GAP = "   "
# Fixed pixel width for the status item — prevents resizing during marquee scroll.
# Sized to fit prefix (♪/Ⅱ) + space + 15 chars at the menu-bar system font (~8 px/char).
_STATUS_ITEM_WIDTH = 155.0

_AVAILABLE = False
if sys.platform == "darwin":
    try:
        import MediaPlayer  # noqa: F401
        _AVAILABLE = True
    except ImportError:
        logger.debug("PyObjC MediaPlayer framework not available — lock screen info disabled")

_STATUS_AVAILABLE = False
if sys.platform == "darwin":
    try:
        import AppKit  # noqa: F401
        _STATUS_AVAILABLE = True
    except ImportError:
        logger.debug("PyObjC AppKit framework not available — menu bar status disabled")

# NSEventMask for right mouse down (type=3 → mask=1<<3=8)
_NSEventMaskRightMouseDown = 8

if _STATUS_AVAILABLE:
    from AppKit import NSObject  # type: ignore[import]

    # Module-level dict avoids storing Python refs directly on NSObject instances,
    # which is unreliable across PyObjC versions.
    _menu_handlers: dict = {}

    class _StatusMenuTarget(NSObject):  # type: ignore[misc]
        """ObjC target for status-bar button clicks and menu item actions."""

        def handleButtonClick_(self, sender):
            h = _menu_handlers.get(id(self))
            if h is not None:
                h._show_status_context_menu()

        def prevTrack_(self, sender):
            h = _menu_handlers.get(id(self))
            if h is not None:
                asyncio.ensure_future(h._ctrl.play_prev())

        def playPause_(self, sender):
            h = _menu_handlers.get(id(self))
            if h is not None:
                h._ctrl.toggle_play_pause()

        def nextTrack_(self, sender):
            h = _menu_handlers.get(id(self))
            if h is not None:
                asyncio.ensure_future(h._ctrl.play_next())

        def quitApp_(self, sender):
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.quit()


def _qt_application_ready() -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return False
    try:
        from PyQt6.QtWidgets import QApplication
        return QApplication.instance() is not None
    except Exception:
        return False


class MacOSMediaHandler:
    """Updates MPNowPlayingInfoCenter and registers MPRemoteCommandCenter handlers.

    Gracefully degrades when PyObjC is not installed.
    Two update paths:
      update_full()     — on track/state change: full info dict + explicit playbackState
      update_position() — on 250ms tick: only elapsed time + rate + playbackState
    """

    def __init__(self, ctrl) -> None:
        self._ctrl = ctrl
        self._cover_data: bytes | None = None
        self._current_track: "Track | None" = None
        self._status_item = None
        self._status_track: "Track | None" = None
        self._status_is_playing = False
        self._status_scroll_key = ""
        self._status_scroll_offset = 0
        self._status_scroll_timer = None
        self._menu_target = None
        if _AVAILABLE:
            self._register_commands()

    # ── remote command registration ───────────────────────────────────────────

    def _register_commands(self) -> None:
        try:
            from MediaPlayer import (
                MPRemoteCommandCenter,
                MPRemoteCommandHandlerStatusSuccess,
            )
            cc = MPRemoteCommandCenter.sharedCommandCenter()

            def _play(event):
                self._ctrl.toggle_play_pause()
                return MPRemoteCommandHandlerStatusSuccess

            def _pause(event):
                self._ctrl.toggle_play_pause()
                return MPRemoteCommandHandlerStatusSuccess

            def _toggle(event):
                self._ctrl.toggle_play_pause()
                return MPRemoteCommandHandlerStatusSuccess

            def _next(event):
                asyncio.ensure_future(self._ctrl.play_next())
                return MPRemoteCommandHandlerStatusSuccess

            def _prev(event):
                asyncio.ensure_future(self._ctrl.play_prev())
                return MPRemoteCommandHandlerStatusSuccess

            def _seek(event):
                pos_s = event.positionTime()
                self._ctrl.seek(int(pos_s * 1000))
                return MPRemoteCommandHandlerStatusSuccess

            cc.playCommand().addTargetWithHandler_(_play)
            cc.pauseCommand().addTargetWithHandler_(_pause)
            cc.togglePlayPauseCommand().addTargetWithHandler_(_toggle)
            cc.nextTrackCommand().addTargetWithHandler_(_next)
            cc.previousTrackCommand().addTargetWithHandler_(_prev)
            cc.changePlaybackPositionCommand().addTargetWithHandler_(_seek)
            logger.debug("macOS remote command handlers registered")
        except Exception as exc:
            logger.warning("macOS media key registration failed: %s", exc)

    # ── public API ────────────────────────────────────────────────────────────

    def set_cover_data(self, data: bytes) -> None:
        self._cover_data = data

    def __del__(self) -> None:
        if _STATUS_AVAILABLE and self._menu_target is not None:
            _menu_handlers.pop(id(self._menu_target), None)

    def ensure_status_item(self) -> None:
        if self._status_item is not None:
            return
        if not (_STATUS_AVAILABLE and _qt_application_ready()):
            return
        self._setup_status_item()
        self._update_status_item(self._status_track, self._status_is_playing)

    def update_full(self, track: "Track | None", position_ms: int, is_playing: bool) -> None:
        """Full update: call on track change, play/pause, or seek."""
        scroll_key = self._status_scroll_key_for(track)
        if scroll_key != self._status_scroll_key:
            self._status_scroll_key = scroll_key
            self._status_scroll_offset = 0
        self._status_track = track
        self._status_is_playing = is_playing
        self._update_status_item(track, is_playing)
        if not _AVAILABLE:
            return
        self._current_track = track
        if track is None:
            self._clear()
            return
        try:
            self._update_now_playing(track, position_ms, is_playing)
            self._set_playback_state(is_playing)
        except Exception as exc:
            logger.debug("NowPlayingInfo full update failed: %s", exc)

    def update_position(self, position_ms: int, is_playing: bool) -> None:
        """Lightweight update: call on every position tick (250ms)."""
        if not _AVAILABLE or self._current_track is None:
            return
        try:
            from MediaPlayer import (
                MPNowPlayingInfoCenter,
                MPNowPlayingInfoPropertyElapsedPlaybackTime,
                MPNowPlayingInfoPropertyPlaybackRate,
            )
            center = MPNowPlayingInfoCenter.defaultCenter()
            info = dict(center.nowPlayingInfo() or {})
            info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = position_ms / 1000.0
            info[MPNowPlayingInfoPropertyPlaybackRate] = 1.0 if is_playing else 0.0
            center.setNowPlayingInfo_(info)
            self._set_playback_state(is_playing)
        except Exception as exc:
            logger.debug("NowPlayingInfo position update failed: %s", exc)

    # ── internal ─────────────────────────────────────────────────────────────

    def _set_playback_state(self, is_playing: bool) -> None:
        try:
            from MediaPlayer import (
                MPNowPlayingInfoCenter,
                MPNowPlayingPlaybackStatePlaying,
                MPNowPlayingPlaybackStatePaused,
            )
            state = (
                MPNowPlayingPlaybackStatePlaying if is_playing
                else MPNowPlayingPlaybackStatePaused
            )
            MPNowPlayingInfoCenter.defaultCenter().setPlaybackState_(state)
        except Exception as exc:
            logger.debug("playbackState update failed: %s", exc)

    def _setup_status_item(self) -> None:
        try:
            from AppKit import NSStatusBar
            from PyQt6.QtCore import QTimer
            bar = NSStatusBar.systemStatusBar()
            self._status_item = bar.statusItemWithLength_(_STATUS_ITEM_WIDTH)

            # Wire right-click → context menu
            self._menu_target = _StatusMenuTarget.new()
            _menu_handlers[id(self._menu_target)] = self
            btn = self._status_item.button()
            btn.setTarget_(self._menu_target)
            btn.setAction_("handleButtonClick:")
            btn.sendActionOn_(_NSEventMaskRightMouseDown)

            self._status_scroll_timer = QTimer()
            self._status_scroll_timer.setInterval(_STATUS_SCROLL_INTERVAL_MS)
            self._status_scroll_timer.timeout.connect(self._advance_status_scroll)
            self._set_status_visible(False)
        except Exception as exc:
            self._status_item = None
            self._status_scroll_timer = None
            self._menu_target = None
            logger.warning("macOS status item setup failed: %s", exc, exc_info=True)

    def _update_status_item(self, track: "Track | None", is_playing: bool) -> None:
        if self._status_item is None:
            return
        if track is None:
            self._stop_status_scroll()
            self._set_status_visible(False)
            return
        try:
            button = self._status_item.button()
            if button is None:
                return
            title = self._format_status_title(
                track, is_playing, self._status_scroll_offset
            )
            button.setTitle_(title)
            tooltip = self._format_status_tooltip(track)
            button.setToolTip_(tooltip)
            self._set_status_visible(True)
            self._sync_status_scroll_timer(track)
        except Exception as exc:
            logger.debug("macOS status item update failed: %s", exc)

    def _set_status_visible(self, visible: bool) -> None:
        if self._status_item is None:
            return
        try:
            if hasattr(self._status_item, "setLength_"):
                self._status_item.setLength_(_STATUS_ITEM_WIDTH if visible else 0.0)
            button = self._status_item.button()
            if button is not None:
                button.setHidden_(not visible)
        except Exception as exc:
            logger.debug("macOS status item visibility update failed: %s", exc)

    @staticmethod
    def _status_scroll_key_for(track: "Track | None") -> str:
        if track is None:
            return ""
        return f"{track.platform}:{track.id}:{track.title}:{track.artist}"

    def _advance_status_scroll(self) -> None:
        track = self._status_track
        if track is None or not self._status_text_should_scroll(track):
            self._stop_status_scroll()
            return
        text = self._status_base_text(track)
        self._status_scroll_offset = (
            self._status_scroll_offset + 1
        ) % len(text + _STATUS_SCROLL_GAP)
        self._update_status_item(track, self._status_is_playing)

    def _sync_status_scroll_timer(self, track: "Track") -> None:
        timer = self._status_scroll_timer
        if timer is None:
            return
        if self._status_text_should_scroll(track):
            if not timer.isActive():
                timer.start()
        else:
            self._stop_status_scroll()

    def _stop_status_scroll(self) -> None:
        timer = self._status_scroll_timer
        if timer is not None and timer.isActive():
            timer.stop()

    def _show_status_context_menu(self) -> None:
        try:
            from AppKit import NSMenu, NSMenuItem
            menu = NSMenu.alloc().initWithTitle_("Omnia")
            menu.setAutoenablesItems_(False)

            def _item(title: str, action: str, enabled: bool = True) -> NSMenuItem:
                it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    title, action, ""
                )
                it.setTarget_(self._menu_target)
                it.setEnabled_(enabled)
                return it

            has_track = self._status_track is not None
            menu.addItem_(_item("上一首", "prevTrack:", has_track))
            play_title = "暂停" if self._status_is_playing else "播放"
            menu.addItem_(_item(play_title, "playPause:", has_track))
            menu.addItem_(_item("下一首", "nextTrack:", has_track))
            menu.addItem_(NSMenuItem.separatorItem())
            menu.addItem_(_item("退出 Omnia", "quitApp:"))

            self._status_item.popUpStatusItemMenu_(menu)
        except Exception as exc:
            logger.debug("Status context menu failed: %s", exc)

    @staticmethod
    def _status_base_text(track: "Track") -> str:
        title = track.title.strip() or "Unknown Track"
        artist = track.artist.strip()
        return f"{title} - {artist}" if artist else title

    @staticmethod
    def _status_text_should_scroll(track: "Track") -> bool:
        return len(MacOSMediaHandler._status_base_text(track)) > _STATUS_VISIBLE_TEXT_CHARS

    @staticmethod
    def _format_status_title(track: "Track", is_playing: bool, offset: int = 0) -> str:
        prefix = "♪" if is_playing else "Ⅱ"
        text = MacOSMediaHandler._status_base_text(track)
        if len(text) > _STATUS_VISIBLE_TEXT_CHARS:
            marquee = text + _STATUS_SCROLL_GAP
            offset %= len(marquee)
            text = (marquee + marquee)[offset:offset + _STATUS_VISIBLE_TEXT_CHARS]
        return f"{prefix} {text}"

    @staticmethod
    def _format_status_tooltip(track: "Track") -> str:
        parts = [track.title.strip() or "Unknown Track"]
        if track.artist.strip():
            parts.append(track.artist.strip())
        if track.album.strip():
            parts.append(track.album.strip())
        return "\n".join(parts)

    def _clear(self) -> None:
        try:
            from MediaPlayer import MPNowPlayingInfoCenter
            MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
        except Exception:
            pass

    def _update_now_playing(
        self, track: "Track", position_ms: int, is_playing: bool
    ) -> None:
        from MediaPlayer import (
            MPNowPlayingInfoCenter,
            MPMediaItemPropertyTitle,
            MPMediaItemPropertyArtist,
            MPMediaItemPropertyAlbumTitle,
            MPMediaItemPropertyPlaybackDuration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime,
            MPNowPlayingInfoPropertyPlaybackRate,
        )

        info: dict = {
            MPMediaItemPropertyTitle: track.title,
            MPMediaItemPropertyArtist: track.artist,
            MPMediaItemPropertyAlbumTitle: track.album,
            MPMediaItemPropertyPlaybackDuration: track.duration_ms / 1000.0,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: position_ms / 1000.0,
            MPNowPlayingInfoPropertyPlaybackRate: 1.0 if is_playing else 0.0,
        }

        if self._cover_data:
            artwork = self._make_artwork(self._cover_data)
            if artwork is not None:
                from MediaPlayer import MPMediaItemPropertyArtwork
                info[MPMediaItemPropertyArtwork] = artwork

        MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(info)

    @staticmethod
    def _make_artwork(data: bytes):
        try:
            from AppKit import NSImage
            from MediaPlayer import MPMediaItemArtwork

            ns_image = NSImage.alloc().initWithData_(data)
            if ns_image is None:
                return None

            def _handler(size):
                return ns_image

            artwork = MPMediaItemArtwork.alloc().initWithBoundsSize_requestHandler_(
                (300.0, 300.0), _handler
            )
            return artwork
        except Exception as exc:
            logger.debug("MPMediaItemArtwork creation failed: %s", exc)
            return None
