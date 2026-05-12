from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QComboBox, QFrame,
)
from PyQt6.QtCore import Qt
from ui.theme import COLORS, FONTS


class SettingsPage(QWidget):
    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._loading = False
        self._setup_ui()
        ctrl.settings_ready.connect(self._on_settings_ready)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(0)

        title = QLabel("设置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addSpacing(24)

        # ── Playback section ─────────────────────────────────────────────────
        layout.addWidget(self._section_label("播放"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        # Volume
        vol_row = QHBoxLayout()
        vol_row.addWidget(self._setting_label("音量"))
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setObjectName("settingSlider")
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setFixedWidth(200)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)
        vol_row.addWidget(self._volume_slider)
        self._volume_value = QLabel("70")
        self._volume_value.setObjectName("settingValue")
        self._volume_value.setFixedWidth(36)
        vol_row.addWidget(self._volume_value)
        vol_row.addStretch()
        layout.addLayout(vol_row)
        layout.addSpacing(12)

        # Repeat mode
        rep_row = QHBoxLayout()
        rep_row.addWidget(self._setting_label("循环模式"))
        self._repeat_combo = QComboBox()
        self._repeat_combo.setObjectName("settingCombo")
        self._repeat_combo.addItems(["不循环", "循环全部", "单曲循环"])
        self._repeat_combo.currentIndexChanged.connect(self._on_repeat_changed)
        rep_row.addWidget(self._repeat_combo)
        rep_row.addStretch()
        layout.addLayout(rep_row)
        layout.addSpacing(12)

        # Shuffle
        shuf_row = QHBoxLayout()
        shuf_row.addWidget(self._setting_label("随机播放"))
        self._shuffle_check = QCheckBox()
        self._shuffle_check.setObjectName("settingCheck")
        self._shuffle_check.stateChanged.connect(self._on_shuffle_changed)
        shuf_row.addWidget(self._shuffle_check)
        shuf_row.addStretch()
        layout.addLayout(shuf_row)
        layout.addSpacing(24)

        # ── Display section ──────────────────────────────────────────────────
        layout.addWidget(self._section_label("显示"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        # Cover rotation
        rot_row = QHBoxLayout()
        rot_row.addWidget(self._setting_label("封面旋转动画"))
        self._rotation_check = QCheckBox()
        self._rotation_check.setObjectName("settingCheck")
        self._rotation_check.stateChanged.connect(self._on_rotation_changed)
        rot_row.addWidget(self._rotation_check)
        rot_row.addStretch()
        layout.addLayout(rot_row)
        layout.addSpacing(12)

        # Lyrics font size
        lyr_row = QHBoxLayout()
        lyr_row.addWidget(self._setting_label("歌词字号"))
        self._lyrics_size_slider = QSlider(Qt.Orientation.Horizontal)
        self._lyrics_size_slider.setObjectName("settingSlider")
        self._lyrics_size_slider.setRange(14, 36)
        self._lyrics_size_slider.setFixedWidth(200)
        self._lyrics_size_slider.valueChanged.connect(self._on_lyrics_size_changed)
        lyr_row.addWidget(self._lyrics_size_slider)
        self._lyrics_size_value = QLabel("22")
        self._lyrics_size_value.setObjectName("settingValue")
        self._lyrics_size_value.setFixedWidth(36)
        lyr_row.addWidget(self._lyrics_size_value)
        lyr_row.addStretch()
        layout.addLayout(lyr_row)

        layout.addStretch()
        self._apply_styles()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _setting_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingLabel")
        label.setFixedWidth(120)
        return label

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        return line

    def _apply_styles(self) -> None:
        c, f = COLORS, FONTS
        self.setStyleSheet(f"""
            #pageTitle {{
                color: {c['text_primary']};
                font-size: {f['size_xl']}px;
                font-weight: bold;
            }}
            #sectionTitle {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
                font-weight: bold;
                letter-spacing: 1px;
                text-transform: uppercase;
                padding: 0;
            }}
            #settingLabel {{
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
            }}
            #settingValue {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
            }}
            #divider {{
                color: {c['divider']};
                margin: 4px 0;
                max-height: 1px;
            }}
            QSlider#settingSlider::groove:horizontal {{
                height: 4px;
                background: {c['bg_elevated']};
                border-radius: 2px;
            }}
            QSlider#settingSlider::sub-page:horizontal {{
                background: {c['accent']};
                border-radius: 2px;
            }}
            QSlider#settingSlider::handle:horizontal {{
                width: 14px; height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                background: {c['text_primary']};
            }}
            QComboBox#settingCombo {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                padding: 4px 12px;
                min-width: 140px;
            }}
            QComboBox#settingCombo::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox#settingCombo QAbstractItemView {{
                background-color: {c['bg_elevated']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                selection-background-color: {c['bg_hover']};
            }}
            QCheckBox#settingCheck::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {c['border']};
                border-radius: 4px;
                background: {c['bg_elevated']};
            }}
            QCheckBox#settingCheck::indicator:checked {{
                background: {c['accent']};
                border-color: {c['accent']};
                image: none;
            }}
        """)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        asyncio.ensure_future(self._ctrl.load_settings())

    def _on_settings_ready(self, settings: dict) -> None:
        self._loading = True
        try:
            vol = int(settings.get("volume") or 70)
            self._volume_slider.setValue(vol)
            self._volume_value.setText(str(vol))

            repeat = settings.get("repeat_mode") or "none"
            idx = {"none": 0, "all": 1, "one": 2}.get(repeat, 0)
            self._repeat_combo.setCurrentIndex(idx)

            shuffle = (settings.get("shuffle") or "false").lower() == "true"
            self._shuffle_check.setChecked(shuffle)

            rotation = (settings.get("cover_rotation") or "true").lower() == "true"
            self._rotation_check.setChecked(rotation)

            lyrics_size = int(settings.get("lyrics_font_size") or 22)
            self._lyrics_size_slider.setValue(lyrics_size)
            self._lyrics_size_value.setText(str(lyrics_size))
        finally:
            self._loading = False

    # ── change handlers ───────────────────────────────────────────────────────

    def _on_volume_changed(self, value: int) -> None:
        self._volume_value.setText(str(value))
        if self._loading:
            return
        self._ctrl.set_volume(value)

    def _on_repeat_changed(self, index: int) -> None:
        if self._loading:
            return
        mode = ["none", "all", "one"][index]
        self._ctrl._player.set_repeat_mode(mode)
        asyncio.ensure_future(self._ctrl.save_setting("repeat_mode", mode))

    def _on_shuffle_changed(self, state: int) -> None:
        if self._loading:
            return
        enabled = state == Qt.CheckState.Checked.value
        self._ctrl._player.set_shuffle(enabled)
        asyncio.ensure_future(self._ctrl.save_setting("shuffle", str(enabled).lower()))

    def _on_rotation_changed(self, state: int) -> None:
        if self._loading:
            return
        enabled = state == Qt.CheckState.Checked.value
        asyncio.ensure_future(self._ctrl.save_setting("cover_rotation", str(enabled).lower()))

    def _on_lyrics_size_changed(self, value: int) -> None:
        self._lyrics_size_value.setText(str(value))
        if self._loading:
            return
        asyncio.ensure_future(self._ctrl.save_setting("lyrics_font_size", str(value)))
