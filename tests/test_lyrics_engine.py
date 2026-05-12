import pytest
from core.lyrics_engine import LyricsEngine
from core.models import LyricLine, LyricWord


def _make_line(start: int, end: int, text: str, words=None) -> LyricLine:
    return LyricLine(start_ms=start, end_ms=end, text=text, words=words or [])


def _make_word(start: int, end: int, text: str) -> LyricWord:
    return LyricWord(start_ms=start, end_ms=end, text=text)


@pytest.fixture
def engine():
    return LyricsEngine()


@pytest.fixture
def simple_lines():
    return [
        _make_line(1000, 3000, "Line one"),
        _make_line(3000, 5000, "Line two"),
        _make_line(6000, 8000, "Line three"),  # gap before this line
    ]


# ── load / clear ─────────────────────────────────────────────────────────────


def test_initial_state(engine):
    assert engine.current_line == -1
    assert engine.current_word == -1
    assert engine.lines == []


def test_load_sets_lines(engine, simple_lines):
    engine.load(simple_lines)
    assert len(engine.lines) == 3


def test_clear_resets_state(engine, simple_lines):
    engine.load(simple_lines)
    engine.update(2000)
    engine.clear()
    assert engine.lines == []
    assert engine.current_line == -1


# ── line-level lookup ─────────────────────────────────────────────────────────


def test_before_first_line_returns_minus_one(engine, simple_lines):
    engine.load(simple_lines)
    assert engine.update(0) == (-1, -1)


def test_position_on_first_line(engine, simple_lines):
    engine.load(simple_lines)
    line_idx, word_idx = engine.update(1500)
    assert line_idx == 0
    assert word_idx == -1  # no words defined


def test_position_on_second_line(engine, simple_lines):
    engine.load(simple_lines)
    line_idx, _ = engine.update(4000)
    assert line_idx == 1


def test_position_in_gap_between_lines(engine, simple_lines):
    engine.load(simple_lines)
    # Gap is 5000–6000
    line_idx, _ = engine.update(5500)
    assert line_idx == -1


def test_position_exactly_at_line_start(engine, simple_lines):
    engine.load(simple_lines)
    line_idx, _ = engine.update(3000)
    assert line_idx == 1


def test_position_at_line_end_excluded(engine, simple_lines):
    engine.load(simple_lines)
    # end_ms == 3000 is exclusive; 3000 belongs to line 1
    line_idx, _ = engine.update(2999)
    assert line_idx == 0


def test_after_last_line_returns_minus_one(engine, simple_lines):
    engine.load(simple_lines)
    line_idx, _ = engine.update(9000)
    assert line_idx == -1


def test_empty_lines_always_returns_minus_one(engine):
    engine.load([])
    assert engine.update(0) == (-1, -1)
    assert engine.update(99999) == (-1, -1)


# ── word-level lookup ─────────────────────────────────────────────────────────


def test_word_level_highlight(engine):
    words = [
        _make_word(1000, 1500, "Hello"),
        _make_word(1500, 2000, " "),
        _make_word(2000, 2500, "world"),
    ]
    lines = [_make_line(1000, 3000, "Hello world", words=words)]
    engine.load(lines)

    line_idx, word_idx = engine.update(1200)
    assert line_idx == 0
    assert word_idx == 0

    _, word_idx = engine.update(1800)
    assert word_idx == 1

    _, word_idx = engine.update(2300)
    assert word_idx == 2


def test_word_gap_returns_minus_one(engine):
    words = [
        _make_word(1000, 1200, "A"),
        _make_word(1500, 1700, "B"),  # gap 1200–1500
    ]
    lines = [_make_line(1000, 3000, "A B", words=words)]
    engine.load(lines)

    _, word_idx = engine.update(1300)
    assert word_idx == -1


def test_no_words_gives_minus_one_word_idx(engine, simple_lines):
    engine.load(simple_lines)
    _, word_idx = engine.update(2000)
    assert word_idx == -1


# ── repeated update calls ─────────────────────────────────────────────────────


def test_update_is_idempotent(engine, simple_lines):
    engine.load(simple_lines)
    result_a = engine.update(1500)
    result_b = engine.update(1500)
    assert result_a == result_b


def test_update_advances_correctly(engine, simple_lines):
    engine.load(simple_lines)
    assert engine.update(1500)[0] == 0
    assert engine.update(3500)[0] == 1
    assert engine.update(7000)[0] == 2
