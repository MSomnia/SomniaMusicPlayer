from __future__ import annotations
import asyncio
import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Track

logger = logging.getLogger(__name__)

_AVAILABLE = False
if sys.platform == "darwin":
    try:
        import MediaPlayer  # noqa: F401
        _AVAILABLE = True
    except ImportError:
        logger.debug("PyObjC MediaPlayer framework not available — lock screen info disabled")


class MacOSMediaHandler:
    """Updates MPNowPlayingInfoCenter and registers MPRemoteCommandCenter handlers.

    Gracefully degrades when PyObjC is not installed.
    """

    def __init__(self, ctrl) -> None:
        self._ctrl = ctrl
        self._cover_data: bytes | None = None
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

    def update(self, track: "Track | None", position_ms: int, is_playing: bool) -> None:
        if not _AVAILABLE:
            return
        if track is None:
            self._clear()
            return
        try:
            self._update_now_playing(track, position_ms, is_playing)
        except Exception as exc:
            logger.debug("NowPlayingInfo update failed: %s", exc)

    def _clear(self) -> None:
        try:
            from MediaPlayer import MPNowPlayingInfoCenter
            MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
        except Exception:
            pass

    def _update_now_playing(self, track: "Track", position_ms: int, is_playing: bool) -> None:
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
