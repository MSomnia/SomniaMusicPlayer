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
