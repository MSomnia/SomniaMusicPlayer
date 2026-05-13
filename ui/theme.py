COLORS = {
    # Background layers
    "bg_base":       "#0D0D0D",
    "bg_panel":      "#1A1A1A",   # sidebar + content area (lighter gray)
    "bg_surface":    "#161616",
    "bg_elevated":   "#242424",
    "bg_hover":      "#2E2E2E",

    # Accent
    "accent":        "#1DB954",
    "accent_dim":    "#158A3E",

    # Text
    "text_primary":  "#FFFFFF",
    "text_secondary": "#A0A0A0",
    "text_muted":    "#5A5A5A",

    # Platform brand colors
    "platform_spotify":  "#1DB954",
    "platform_ytmusic":  "#FF0000",
    "platform_netease":  "#F97316",

    # Structural
    "border":        "#2C2C2C",
    "divider":       "#1F1F1F",

    # Lyrics states
    "lyrics_active": "#FFFFFF",
    "lyrics_past":   "#4A4A4A",
    "lyrics_future": "#6E6E6E",
}

FONTS = {
    "family":      "Inter",
    "size_xs":     10,
    "size_sm":     12,
    "size_md":     14,
    "size_lg":     18,
    "size_xl":     24,
    "size_lyrics": 22,
}


def scrollbar_qss() -> str:
    return f"""
        QScrollBar:horizontal {{
            background: transparent;
            height: 0px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: transparent;
            height: 0px;
        }}
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0px;
            height: 0px;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 6px 2px 6px 2px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 70);
            border-radius: 3px;
            min-height: 36px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(255, 255, 255, 110);
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            width: 0px;
            height: 0px;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """
