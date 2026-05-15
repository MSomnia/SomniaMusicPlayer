from __future__ import annotations
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QComboBox, QFrame, QPushButton, QLineEdit, QFileDialog,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QSignalBlocker
from ui.theme import COLORS, FONTS

_PLATFORMS = [
    ("netease", "网易云音乐"),
    ("spotify",  "Spotify"),
    ("ytmusic",  "YouTube Music"),
]


class SettingsPage(QWidget):
    _STANDBY_OPTIONS: list[tuple[str, int]] = [
        ("关闭", 0),
        ("2 分钟", 2),
        ("5 分钟", 5),
        ("10 分钟", 10),
    ]

    def __init__(self, ctrl, parent=None) -> None:
        super().__init__(parent)
        self._ctrl = ctrl
        self._loading = False
        self._platform_rows: dict[str, dict] = {}
        self._setup_ui()
        ctrl.settings_ready.connect(self._on_settings_ready)
        ctrl.netease_auth_changed.connect(
            lambda ok: self._on_auth_changed("netease", ok)
        )
        ctrl.ytmusic_auth_changed.connect(
            lambda ok: self._on_auth_changed("ytmusic", ok)
        )
        ctrl.spotify_auth_changed.connect(
            lambda ok: self._on_auth_changed("spotify", ok)
        )
        ctrl.profile_changed.connect(self._on_profile_changed)
        ctrl.background_changed.connect(self._on_background_changed)
        ctrl.volume_changed.connect(self._on_volume_synced)
        ctrl.update_status_ready.connect(self._on_update_status)

    # ── construction ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        _container = QWidget()
        _container.setObjectName("settingsContainer")
        layout = QVBoxLayout(_container)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(0)

        scroll.setWidget(_container)
        outer.addWidget(scroll)

        title = QLabel("设置")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addSpacing(24)

        # ── Profile section ──────────────────────────────────────────────────
        layout.addWidget(self._section_label("个人"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(10)
        profile_row.addWidget(self._setting_label("昵称"))
        self._display_name_input = QLineEdit()
        self._display_name_input.setObjectName("displayNameInput")
        self._display_name_input.setPlaceholderText("Somnia")
        self._display_name_input.setMaxLength(24)
        self._display_name_input.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._display_name_input.returnPressed.connect(self._save_display_name)
        profile_row.addWidget(self._display_name_input)

        self._display_name_btn = QPushButton("保存")
        self._display_name_btn.setObjectName("displayNameBtn")
        self._display_name_btn.clicked.connect(self._save_display_name)
        profile_row.addWidget(self._display_name_btn)
        layout.addLayout(profile_row)
        layout.addSpacing(24)

        # ── Accounts section ─────────────────────────────────────────────────
        layout.addWidget(self._section_label("账户"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        for pid, pname in _PLATFORMS:
            row = self._make_platform_row(pid, pname)
            layout.addLayout(row["layout"])
            self._platform_rows[pid] = row
            layout.addSpacing(8)

        layout.addSpacing(16)

        # ── Playback section ─────────────────────────────────────────────────
        layout.addWidget(self._section_label("播放"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        # Volume
        vol_row = QHBoxLayout()
        vol_row.setSpacing(10)
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
        layout.addSpacing(24)

        # ── Display section ──────────────────────────────────────────────────
        layout.addWidget(self._section_label("显示"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        # App background image
        bg_row = QHBoxLayout()
        bg_row.setSpacing(10)
        bg_row.addWidget(self._setting_label("背景图"))
        self._background_image_input = QLineEdit()
        self._background_image_input.setObjectName("backgroundImageInput")
        self._background_image_input.setPlaceholderText("未选择")
        self._background_image_input.setReadOnly(True)
        bg_row.addWidget(self._background_image_input)

        self._background_browse_btn = QPushButton("浏览")
        self._background_browse_btn.setObjectName("backgroundBrowseBtn")
        self._background_browse_btn.clicked.connect(self._choose_background_image)
        bg_row.addWidget(self._background_browse_btn)

        self._background_clear_btn = QPushButton("清除")
        self._background_clear_btn.setObjectName("backgroundClearBtn")
        self._background_clear_btn.clicked.connect(self._clear_background_image)
        bg_row.addWidget(self._background_clear_btn)

        self._background_black_check = QCheckBox("纯黑")
        self._background_black_check.setObjectName("settingCheck")
        self._background_black_check.stateChanged.connect(
            self._on_background_black_changed
        )
        bg_row.addWidget(self._background_black_check)
        layout.addLayout(bg_row)
        layout.addSpacing(12)

        # Cover rotation
        rot_row = QHBoxLayout()
        rot_row.setSpacing(10)
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
        lyr_row.setSpacing(10)
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
        layout.addSpacing(12)

        # Auto standby
        standby_row = QHBoxLayout()
        standby_row.setSpacing(10)
        standby_row.addWidget(self._setting_label("自动待机"))
        self._auto_standby_combo = QComboBox()
        self._auto_standby_combo.setObjectName("standbyCombo")
        for label, _ in self._STANDBY_OPTIONS:
            self._auto_standby_combo.addItem(label)
        self._auto_standby_combo.currentIndexChanged.connect(self._on_auto_standby_changed)
        standby_row.addWidget(self._auto_standby_combo)
        standby_row.addStretch()
        layout.addLayout(standby_row)
        layout.addSpacing(24)

        # ── Update section ───────────────────────────────────────────────────
        layout.addWidget(self._section_label("更新"))
        layout.addWidget(self._make_divider())
        layout.addSpacing(12)

        # Version row
        ver_row = QHBoxLayout()
        ver_row.setSpacing(10)
        ver_row.addWidget(self._setting_label("当前版本"))
        self._version_label = QLabel("—")
        self._version_label.setObjectName("settingValue")
        ver_row.addWidget(self._version_label)
        ver_row.addSpacing(16)
        self._check_update_btn = QPushButton("检查更新")
        self._check_update_btn.setObjectName("checkUpdateBtn")
        self._check_update_btn.clicked.connect(self._on_check_update_clicked)
        ver_row.addWidget(self._check_update_btn)
        self._update_status_label = QLabel("")
        self._update_status_label.setObjectName("updateStatusLabel")
        ver_row.addWidget(self._update_status_label)
        ver_row.addStretch()
        layout.addLayout(ver_row)
        layout.addSpacing(8)

        # Auto-update + apply row
        update_action_row = QHBoxLayout()
        update_action_row.setSpacing(10)
        update_action_row.addWidget(self._setting_label("自动更新"))
        self._auto_update_check = QCheckBox()
        self._auto_update_check.setObjectName("settingCheck")
        self._auto_update_check.setChecked(True)
        self._auto_update_check.stateChanged.connect(self._on_auto_update_changed)
        update_action_row.addWidget(self._auto_update_check)
        update_action_row.addSpacing(16)
        self._apply_update_btn = QPushButton("立即更新并重启")
        self._apply_update_btn.setObjectName("applyUpdateBtn")
        self._apply_update_btn.hide()
        self._apply_update_btn.clicked.connect(self._on_apply_update_clicked)
        update_action_row.addWidget(self._apply_update_btn)
        update_action_row.addStretch()
        layout.addLayout(update_action_row)

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

    def _make_platform_row(self, pid: str, name: str) -> dict:
        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(10)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("settingLabel")
        name_lbl.setFixedWidth(160)

        status_lbl = QLabel("未登录")
        status_lbl.setObjectName("accountStatus")

        btn = QPushButton("登录")
        btn.setObjectName("accountBtnLogin")
        btn.setFixedWidth(88)

        confirm_btn = QPushButton("确认退出")
        confirm_btn.setObjectName("accountBtnLogoutConfirm")
        confirm_btn.setFixedWidth(88)
        confirm_btn.hide()

        hbox.addWidget(name_lbl)
        hbox.addWidget(status_lbl)
        hbox.addStretch()
        hbox.addWidget(btn)
        hbox.addWidget(confirm_btn)

        btn.clicked.connect(lambda: asyncio.ensure_future(self._login(pid)))

        return {
            "layout": hbox,
            "status": status_lbl,
            "btn": btn,
            "confirm_btn": confirm_btn,
        }

    def _set_row_authed(self, pid: str, authed: bool, username: str | None = None) -> None:
        row = self._platform_rows.get(pid)
        if not row:
            return
        btn: QPushButton = row["btn"]
        confirm_btn: QPushButton = row["confirm_btn"]
        status: QLabel = row["status"]
        self._disconnect_button(btn)
        self._disconnect_button(confirm_btn)
        confirm_btn.hide()
        if authed:
            text = "已登录" + (f" · {username}" if username else "")
            status.setText(text)
            status.setProperty("class", "authed")
            btn.setText("退出登录")
            btn.setObjectName("accountBtnLogout")
            btn.clicked.connect(lambda: self._show_logout_confirm(pid))
            confirm_btn.clicked.connect(lambda: asyncio.ensure_future(self._logout(pid)))
        else:
            status.setText("未登录")
            status.setProperty("class", "")
            btn.setText("登录")
            btn.setObjectName("accountBtnLogin")
            btn.clicked.connect(lambda: asyncio.ensure_future(self._login(pid)))
        # Force style refresh after objectName change
        self._refresh_button_style(btn)
        self._refresh_button_style(confirm_btn)
        status.style().unpolish(status)
        status.style().polish(status)

    def _disconnect_button(self, btn: QPushButton) -> None:
        try:
            btn.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass

    def _refresh_button_style(self, btn: QPushButton) -> None:
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _show_logout_confirm(self, pid: str) -> None:
        row = self._platform_rows.get(pid)
        if not row:
            return
        btn: QPushButton = row["btn"]
        confirm_btn: QPushButton = row["confirm_btn"]
        self._disconnect_button(btn)
        btn.setText("取消")
        btn.setObjectName("accountBtnLogout")
        btn.clicked.connect(lambda: self._hide_logout_confirm(pid))
        confirm_btn.show()
        self._refresh_button_style(btn)
        self._refresh_button_style(confirm_btn)

    def _hide_logout_confirm(self, pid: str) -> None:
        row = self._platform_rows.get(pid)
        if not row:
            return
        btn: QPushButton = row["btn"]
        confirm_btn: QPushButton = row["confirm_btn"]
        self._disconnect_button(btn)
        btn.setText("退出登录")
        btn.setObjectName("accountBtnLogout")
        btn.clicked.connect(lambda: self._show_logout_confirm(pid))
        confirm_btn.hide()
        self._refresh_button_style(btn)
        self._refresh_button_style(confirm_btn)

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
            QCheckBox#settingCheck::indicator {{
                width: 18px; height: 18px;
                border: 2px solid {c['border']};
                border-radius: 4px;
                background: {c['bg_elevated']};
            }}
            QCheckBox#settingCheck {{
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                spacing: 8px;
            }}
            QCheckBox#settingCheck::indicator:checked {{
                background: {c['accent']};
                border-color: {c['accent']};
                image: none;
            }}
            QLabel#accountStatus {{
                color: {c['text_secondary']};
                font-size: {f['size_xs']}px;
            }}
            QLineEdit#displayNameInput,
            QLineEdit#backgroundImageInput {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                padding: 7px 12px;
            }}
            QLineEdit#displayNameInput:focus,
            QLineEdit#backgroundImageInput:focus {{
                border-color: {c['accent']};
            }}
            QPushButton#displayNameBtn,
            QPushButton#backgroundBrowseBtn {{
                background-color: {c['accent']};
                color: #000;
                border: none;
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                font-weight: bold;
                padding: 6px 16px;
            }}
            QPushButton#displayNameBtn:hover,
            QPushButton#backgroundBrowseBtn:hover {{
                background-color: {c['accent_dim']};
            }}
            QPushButton#backgroundClearBtn {{
                background-color: transparent;
                color: {c['text_secondary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                padding: 6px 14px;
            }}
            QPushButton#backgroundClearBtn:hover {{
                color: {c['text_primary']};
                border-color: {c['text_secondary']};
            }}
            QPushButton#accountBtnLogin {{
                background-color: {c['accent']};
                color: #000;
                border: none;
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                font-weight: bold;
                padding: 4px 12px;
            }}
            QPushButton#accountBtnLogin:hover {{
                background-color: {c['accent_dim']};
            }}
            QPushButton#accountBtnLogout {{
                background-color: transparent;
                color: {c['text_secondary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                padding: 4px 12px;
            }}
            QPushButton#accountBtnLogout:hover {{
                color: {c['text_primary']};
                border-color: {c['text_secondary']};
            }}
            QPushButton#accountBtnLogoutConfirm {{
                background-color: #FF4444;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                font-weight: bold;
                padding: 4px 12px;
            }}
            QPushButton#accountBtnLogoutConfirm:hover {{
                background-color: #FF6B6B;
            }}
            QComboBox#standbyCombo {{
                background-color: {c['bg_elevated']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                color: {c['text_primary']};
                font-size: {f['size_sm']}px;
                padding: 5px 10px;
                min-width: 100px;
            }}
            QComboBox#standbyCombo:hover {{
                border-color: {c['text_secondary']};
            }}
            QComboBox#standbyCombo::drop-down {{
                border: none;
                width: 20px;
            }}
            #settingsContainer {{
                background-color: transparent;
            }}
            QScrollArea#settingsScroll {{
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c['border']};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c['text_secondary']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QPushButton#checkUpdateBtn {{
                background-color: transparent;
                color: {c['text_secondary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                padding: 5px 14px;
            }}
            QPushButton#checkUpdateBtn:hover {{
                color: {c['text_primary']};
                border-color: {c['text_secondary']};
            }}
            QPushButton#checkUpdateBtn:disabled {{
                color: {c['text_secondary']};
                opacity: 0.5;
            }}
            QPushButton#applyUpdateBtn {{
                background-color: {c['accent']};
                color: #000;
                border: none;
                border-radius: 6px;
                font-size: {f['size_xs']}px;
                font-weight: bold;
                padding: 5px 16px;
            }}
            QPushButton#applyUpdateBtn:hover {{
                background-color: {c['accent_dim']};
            }}
            QPushButton#applyUpdateBtn:disabled {{
                opacity: 0.5;
            }}
            QLabel#updateStatusLabel {{
                font-size: {f['size_xs']}px;
                color: {c['text_secondary']};
            }}
            QLabel#updateStatusLabel[updateState="available"] {{
                color: {c['accent']};
            }}
            QLabel#updateStatusLabel[updateState="error"] {{
                color: #FF6B6B;
            }}
            QLabel#updateStatusLabel[updateState="ok"] {{
                color: {c['text_secondary']};
            }}
        """)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        asyncio.ensure_future(self._ctrl.load_settings())
        asyncio.ensure_future(self._refresh_accounts())

    # ── account section ───────────────────────────────────────────────────────

    async def _refresh_accounts(self) -> None:
        _auth = {
            "netease": self._ctrl.is_netease_authenticated,
            "ytmusic": self._ctrl.is_ytmusic_authenticated,
            "spotify": self._ctrl.is_spotify_authenticated,
        }
        for pid, _ in _PLATFORMS:
            if _auth[pid]:
                self._set_row_authed(pid, True)
                name = await self._ctrl.get_account_name(pid)
                self._set_row_authed(pid, True, name)
            else:
                self._set_row_authed(pid, False)

    def _on_auth_changed(self, pid: str, authed: bool) -> None:
        self._set_row_authed(pid, authed)
        if authed:
            asyncio.ensure_future(self._fetch_username(pid))

    async def _fetch_username(self, pid: str) -> None:
        name = await self._ctrl.get_account_name(pid)
        self._set_row_authed(pid, True, name)

    async def _login(self, pid: str) -> None:
        handler = {
            "netease": self._ctrl.ensure_netease_auth,
            "ytmusic": self._ctrl.ensure_ytmusic_auth,
            "spotify": self._ctrl.ensure_spotify_auth,
        }.get(pid)
        if handler:
            await handler(self)

    async def _logout(self, pid: str) -> None:
        handler = {
            "netease": self._ctrl.logout_netease,
            "ytmusic": self._ctrl.logout_ytmusic,
            "spotify": self._ctrl.logout_spotify,
        }.get(pid)
        if handler:
            await handler()

    def _on_settings_ready(self, settings: dict) -> None:
        self._loading = True
        try:
            self._display_name_input.setText(settings.get("display_name") or "Somnia")
            self._background_image_input.setText(
                settings.get("background_image_path") or ""
            )
            pure_black = (
                settings.get("background_pure_black") or "false"
            ).lower() == "true"
            self._background_black_check.setChecked(pure_black)
            self._set_background_image_controls_enabled(not pure_black)

            vol = int(settings.get("volume") or 70)
            self._volume_slider.setValue(vol)
            self._volume_value.setText(str(vol))

            rotation = (settings.get("cover_rotation") or "true").lower() == "true"
            self._rotation_check.setChecked(rotation)

            lyrics_size = int(settings.get("lyrics_font_size") or 22)
            self._lyrics_size_slider.setValue(lyrics_size)
            self._lyrics_size_value.setText(str(lyrics_size))

            minutes = int(settings.get("auto_standby_minutes") or 5)
            minutes_values = [m for _, m in self._STANDBY_OPTIONS]
            idx = minutes_values.index(minutes) if minutes in minutes_values else 2
            self._auto_standby_combo.setCurrentIndex(idx)

            auto_update = (settings.get("auto_update") or "true").lower() == "true"
            self._auto_update_check.setChecked(auto_update)
        finally:
            self._loading = False

        # Apply repeat/shuffle to player state so the bottom bar reflects
        # the saved settings. These controls live in the bottom bar now.
        repeat = settings.get("repeat_mode") or "none"
        if repeat in ("none", "all", "one"):
            self._ctrl._player.set_repeat_mode(repeat)
        shuffle = (settings.get("shuffle") or "false").lower() == "true"
        self._ctrl._player.set_shuffle(shuffle)
        self._ctrl._player.state_changed.emit(self._ctrl._player.state)

    # ── change handlers ───────────────────────────────────────────────────────

    def _on_profile_changed(self, name: str) -> None:
        if self._display_name_input.text().strip() != name:
            self._display_name_input.setText(name)

    def _save_display_name(self) -> None:
        if self._loading:
            return
        name = self._display_name_input.text().strip() or "Somnia"
        self._display_name_input.setText(name)
        asyncio.ensure_future(self._ctrl.save_setting("display_name", name))

    def _on_background_changed(self, path: str) -> None:
        if self._background_black_check.isChecked() and not path:
            return
        if self._background_image_input.text().strip() != path:
            self._background_image_input.setText(path)

    def _set_background_image_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._background_image_input,
            self._background_browse_btn,
            self._background_clear_btn,
        ):
            widget.setEnabled(enabled)

    def _on_volume_synced(self, value: int) -> None:
        with QSignalBlocker(self._volume_slider):
            self._volume_slider.setValue(value)
        self._volume_value.setText(str(value))

    def _choose_background_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "选择背景图片",
            self._background_image_input.text().strip(),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        self._background_image_input.setText(path)
        asyncio.ensure_future(self._ctrl.save_setting("background_image_path", path))

    def _clear_background_image(self) -> None:
        self._background_image_input.clear()
        asyncio.ensure_future(self._ctrl.save_setting("background_image_path", ""))

    def _on_background_black_changed(self, state: int) -> None:
        enabled = state == Qt.CheckState.Checked.value
        self._set_background_image_controls_enabled(not enabled)
        if self._loading:
            return
        asyncio.ensure_future(
            self._ctrl.save_setting("background_pure_black", str(enabled).lower())
        )

    def _on_volume_changed(self, value: int) -> None:
        self._volume_value.setText(str(value))
        if self._loading:
            return
        self._ctrl.set_volume(value)

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

    def _on_auto_standby_changed(self, index: int) -> None:
        if self._loading:
            return
        _, minutes = self._STANDBY_OPTIONS[index]
        asyncio.ensure_future(self._ctrl.save_setting("auto_standby_minutes", str(minutes)))

    # ── update handlers ───────────────────────────────────────────────────────

    def _on_check_update_clicked(self) -> None:
        self._check_update_btn.setEnabled(False)
        self._update_status_label.setText("正在检查...")
        self._apply_update_btn.hide()
        asyncio.ensure_future(self._ctrl.check_for_update())

    def _on_apply_update_clicked(self) -> None:
        self._apply_update_btn.setEnabled(False)
        self._check_update_btn.setEnabled(False)
        self._update_status_label.setText("正在更新，请稍候...")
        asyncio.ensure_future(self._ctrl.apply_update())

    def _on_auto_update_changed(self, state: int) -> None:
        if self._loading:
            return
        from PyQt6.QtCore import Qt as _Qt
        enabled = state == _Qt.CheckState.Checked.value
        asyncio.ensure_future(self._ctrl.save_setting("auto_update", str(enabled).lower()))

    def _on_update_status(self, status) -> None:
        from PyQt6.QtCore import QTimer
        self._check_update_btn.setEnabled(True)
        self._version_label.setText(status.local_short)
        if status.error and not status.available:
            self._update_status_label.setProperty("updateState", "error")
            self._update_status_label.setText(status.error)
            self._apply_update_btn.hide()
        elif status.available:
            self._update_status_label.setProperty("updateState", "available")
            msgs = "、".join(status.commit_messages[:3]) if status.commit_messages else ""
            self._update_status_label.setText(f"发现新版本 {status.remote_short}" + (f"：{msgs}" if msgs else ""))
            self._apply_update_btn.show()
            self._apply_update_btn.setEnabled(True)
        else:
            self._update_status_label.setProperty("updateState", "ok")
            self._update_status_label.setText("已是最新版本")
            self._apply_update_btn.hide()
        # Force style refresh after property change
        self._update_status_label.style().unpolish(self._update_status_label)
        self._update_status_label.style().polish(self._update_status_label)

    def init_version_label(self) -> None:
        """Called once on startup to show local commit without a full check."""
        import asyncio as _asyncio
        async def _set():
            from core import updater
            commit = await updater.get_local_commit()
            self._version_label.setText(commit[:7] if commit else "unknown")
        _asyncio.ensure_future(_set())
