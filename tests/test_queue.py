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
    assert q.current_track == q.tracks[0]


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


def test_peek_next_returns_next_without_advancing():
    q = PlayQueue()
    tracks = [_t("1"), _t("2"), _t("3")]
    q.set_tracks(tracks, start_index=0)
    peeked = q.peek_next()
    assert peeked == tracks[1]
    assert q.current_track == tracks[0]   # index 未推进
    assert q.current_index == 0


def test_peek_next_at_end_no_repeat_returns_none():
    q = PlayQueue()
    q.set_tracks([_t("1")], start_index=0)
    assert q.peek_next(repeat_mode="none") is None


def test_peek_next_repeat_all_returns_first():
    q = PlayQueue()
    tracks = [_t("1"), _t("2")]
    q.set_tracks(tracks, start_index=1)
    assert q.peek_next(repeat_mode="all") == tracks[0]


def test_peek_next_repeat_one_returns_current():
    q = PlayQueue()
    tracks = [_t("1"), _t("2")]
    q.set_tracks(tracks, start_index=0)
    assert q.peek_next(repeat_mode="one") == tracks[0]


def test_peek_next_empty_queue_returns_none():
    q = PlayQueue()
    assert q.peek_next() is None
