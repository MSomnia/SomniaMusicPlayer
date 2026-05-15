from __future__ import annotations
import io
import logging
import threading
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
        self._lock = threading.Lock()

    def has_session(self) -> bool:
        with self._lock:
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
            session = builder.stored_file().create()
        elif username and password:
            logger.info("Librespot: authenticating with username/password")
            session = builder.user_pass(username, password).create()
        else:
            raise RuntimeError(
                "No librespot credentials found. Login with username and password first."
            )
        with self._lock:
            self._session = session

    def create_session_with_token(self, access_token: str) -> None:
        """Create a librespot Session using an existing Spotify Web API access token.

        Spotify Connect's AUTHENTICATION_SPOTIFY_TOKEN type was designed for
        tokens obtained from open.spotify.com/get_access_token (i.e. sp_dc tokens),
        making this more compatible with current Spotify AP servers than the
        keymaster OAuth flow used by librespot's built-in oauth().
        """
        if not _LIBRESPOT_AVAILABLE:
            raise RuntimeError("librespot-python is not installed")

        from librespot.proto.Authentication_pb2 import (
            LoginCredentials,
            AuthenticationType,
        )

        conf = (
            Session.Configuration.Builder()
            .set_stored_credential_file(self._creds_path)
            .build()
        )
        builder = Session.Builder(conf=conf)
        builder.login_credentials = LoginCredentials(
            typ=AuthenticationType.AUTHENTICATION_SPOTIFY_TOKEN,
            auth_data=access_token.encode("utf-8"),
        )
        logger.info("Librespot: authenticating with sp_dc access token")
        session = builder.create()
        with self._lock:
            self._session = session

    def load_track(self, track_id_str: str) -> tuple[np.ndarray, int]:
        """Decrypt and decode a Spotify track → (float32 array, samplerate).

        Downloads the full track before returning (download-then-play model).
        Raises RuntimeError if no session or decode fails.
        Auto-reconnects once if the session has been dropped by the AP server.
        """
        if not _LIBRESPOT_AVAILABLE:
            raise RuntimeError("librespot-python not installed")
        if sf is None:
            raise RuntimeError("soundfile not installed — cannot decode Ogg Vorbis")

        for attempt in range(2):
            with self._lock:
                session = self._session
            if session is None:
                raise RuntimeError("No session — call create_session() first")
            try:
                return self._do_load_track(session, track_id_str)
            except Exception as exc:
                if attempt == 0 and self._is_connection_error(exc):
                    logger.warning(
                        "Librespot session disconnected (attempt %d): %s — reconnecting",
                        attempt + 1, exc,
                    )
                    self._invalidate_and_reconnect()
                    continue
                raise

        raise RuntimeError("load_track: unreachable")  # pragma: no cover

    def _do_load_track(self, session: "Session", track_id_str: str) -> tuple[np.ndarray, int]:
        tid = TrackId.from_uri(f"spotify:track:{track_id_str}")
        loaded = session.content_feeder().load(
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

        if audio_data.ndim == 1:
            audio_data = audio_data.reshape(-1, 1)

        logger.debug(
            "Loaded track %s: %d frames @ %dHz, %d ch",
            track_id_str, len(audio_data), samplerate, audio_data.shape[1],
        )
        return audio_data, samplerate

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        if isinstance(exc, (ConnectionResetError, ConnectionRefusedError, ConnectionAbortedError, OSError)):
            return True
        msg = str(exc).lower()
        return any(k in msg for k in ("failed to receive packet", "connection reset", "connection refused", "broken pipe", "socket"))

    def _invalidate_and_reconnect(self) -> None:
        """Close the broken session and recreate it from stored credentials."""
        with self._lock:
            old_session = self._session
            self._session = None
        if old_session is not None:
            try:
                old_session.close()
            except Exception:
                pass
        if not Path(self._creds_path).exists():
            raise RuntimeError("Librespot session dropped and no stored credentials to reconnect with")
        logger.info("Librespot: reconnecting from stored credentials")
        self.create_session()

    @staticmethod
    def _patch_oauth_server_reuse_port() -> None:
        """Set SO_REUSEPORT on librespot's OAuth callback server.

        librespot's OAuth.CallbackServer never calls server_close(), so the
        socket on port 5588 stays bound after an exception (e.g. TravelRestriction).
        Setting allow_reuse_port=True lets the next attempt rebind immediately.
        """
        try:
            import socket as _socket
            if not hasattr(_socket, "SO_REUSEPORT"):
                return
            from librespot.oauth import OAuth
            OAuth.CallbackServer.allow_reuse_port = True
        except Exception:
            pass

    def create_session_oauth(self, url_callback=None) -> None:
        """Create a librespot Session via Spotify OAuth browser flow.

        url_callback(url: str) is called once the OAuth URL is ready.
        Blocks until the user completes login in the browser; librespot's
        local HTTP server at 127.0.0.1:5588 captures the redirect.
        On success, credentials are persisted to creds_path automatically.
        """
        if not _LIBRESPOT_AVAILABLE:
            raise RuntimeError("librespot-python is not installed")

        self._patch_oauth_server_reuse_port()

        conf = (
            Session.Configuration.Builder()
            .set_stored_credential_file(self._creds_path)
            .build()
        )
        session = Session.Builder(conf=conf).oauth(url_callback).create()
        with self._lock:
            self._session = session

    def close(self) -> None:
        with self._lock:
            session = self._session
            self._session = None
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
