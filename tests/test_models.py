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
