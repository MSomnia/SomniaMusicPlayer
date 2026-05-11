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
    await repo.init()
    volume = await repo.get_setting("volume")
    assert volume == "70"
    await repo.close()
