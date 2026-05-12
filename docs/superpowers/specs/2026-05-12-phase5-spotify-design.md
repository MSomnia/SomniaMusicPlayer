# Phase 5 — Spotify 集成设计

> 日期：2026-05-12  
> 基于：spec.md §7.1、§11 Phase 5  
> 音频后端：librespot-python 库 + sounddevice（方案 A）

---

## 1. 总体架构

Phase 5 在现有 Phase 1–4 基础上叠加，新增四个文件，修改两个现有文件。

```
platforms/spotify/
├── auth.py              # sp_dc 捕获 + access_token 管理
├── client.py            # AbstractPlatform 实现（搜索/歌词/库）
├── librespot_bridge.py  # librespot-python Session 封装，供 LibrespotBackend 调用
└── lyrics.py            # color-lyrics v2 API 解析 → list[LyricLine]

core/
└── librespot_backend.py # LibrespotBackend QObject，与 VLCBackend 对称

（修改）
core/app_controller.py   # 添加 Spotify auth/client/backend 字段及方法
ui/app_window.py         # _on_platform_login 添加 spotify 分支 + 信号连接
requirements.txt         # 添加 librespot-python、sounddevice、pyobjc-framework-MediaPlayer
```

---

## 2. auth.py — Spotify 鉴权

**职责**：WebView 捕获 `sp_dc` Cookie，换取 Bearer token，管理 token 刷新。

### 流程

```
LoginDialog(accounts.spotify.com/login)
  → 监听 CookieStore，检测到 sp_dc 写入
  → 关闭 WebView
  → 保存 sp_dc 到 SQLite（AES-256，与其他平台一致）
  → 调用 open.spotify.com/get_access_token 换取 Bearer token
  → 缓存 token + 过期时间（约 1 小时）
```

### 接口

```python
class SpotifyAuth:
    async def load_sp_dc(self) -> str | None
    async def login(self, parent=None) -> str | None       # 返回 sp_dc
    async def get_access_token(self) -> str                # 自动刷新
    async def ensure_authenticated(self, parent=None) -> str | None
```

`get_access_token()` 检查缓存 token 是否过期（提前 60 秒刷新），过期则用 sp_dc 重新换取，无需再弹 WebView。

---

## 3. client.py — AbstractPlatform 实现

**职责**：实现 `AbstractPlatform` 的四个方法，对接 Spotify 内部 API。

| 方法 | 接口 | 说明 |
|------|------|------|
| `is_authenticated()` | `SpotifyAuth.load_sp_dc()` | 检查 sp_dc 是否存在 |
| `search(query, limit)` | `api-partner.spotify.com/pathfinder/v1/query?operationName=searchDesktop` | GraphQL，返回 `list[Track]` |
| `get_stream_url(track)` | 不适用——Spotify 流需 librespot 解密 | 返回 `f"spotify:track:{track.id}"` 作为伪 URL，由 LibrespotBackend 解析 |
| `get_lyrics(track)` | `spclient.wg.spotify.com/color-lyrics/v2/track/{id}` | 调 `SpotifyLyrics.fetch()` |
| `get_library_playlists()` | `api-partner.spotify.com/pathfinder/v1/query?operationName=libraryV3` | 返回用户收藏歌单 |

**`get_stream_url()` 特殊处理**：Spotify 曲目无法像 YouTube/网易云那样返回可直接播放的 HTTP URL。`get_stream_url()` 返回 `spotify:track:{id}` 协议字符串。`AppController.play_track()` 检测到此格式后，不调用 VLC，改调 `LibrespotBackend.play(track_id)`。

### HTTP 请求规范

```python
# 所有 Spotify API 请求共用一个 httpx.AsyncClient，携带：
headers = {
    "Authorization": f"Bearer {token}",
    "App-Platform": "WebPlayer",
    "Spotify-App-Version": "1.2.50.248",
}
```

---

## 4. librespot_bridge.py — librespot-python 封装

**职责**：管理 librespot-python `Session` 对象，提供同步的流解密接口供 `LibrespotBackend` 在后台线程调用。

```python
class LibrespotBridge:
    def create_session(self, username: str, token: str) -> None
        # 用 Spotify access_token 初始化 librespot Session
    
    def load_track(self, track_id: str) -> AudioStream
        # 返回可迭代的解密 PCM 块（bytes 迭代器）
    
    def seek(self, position_ms: int) -> None
        # 重新打开 stream 到目标偏移量
    
    def close(self) -> None
```

**认证方式**：librespot-python `Session.Builder` 支持以下方式初始化：
- `stored_credential(username, blob)` — 首次用 `user_pass()` 或 OAuth 认证后，librespot 返回可持久化的凭证 blob，后续复用。
- `oauth(access_token)` — 若 librespot-python 版本支持，直接用 Web API access_token（需验证）。

**实际策略**：首次登录时，`librespot_bridge.py` 尝试以 `oauth(access_token)` 方式创建 Session；若不支持，则向用户提示需要输入 Spotify 账号/密码一次，成功后保存 credential blob 到 SQLite（加密），后续复用 `stored_credential`，无需再次输入。

---

## 5. core/librespot_backend.py — LibrespotBackend QObject

**职责**：与 `VLCBackend` 对称的 QObject，在后台线程泵 PCM 数据到 sounddevice，发射相同格式的 Qt 信号。

### 接口（与 VLCBackend 对称）

```python
class LibrespotBackend(QObject):
    position_changed = pyqtSignal(int)   # ms
    end_reached = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def play(self, track_id: str) -> None
    def pause(self) -> None
    def stop(self) -> None
    def seek(self, position_ms: int) -> None
    def set_volume(self, volume: int) -> None
    def get_position_ms(self) -> int
```

### 线程模型

```
主线程（Qt）               后台线程（daemon）
    │                           │
    │── play(track_id) ────────►│ bridge.load_track()
    │                           │ sounddevice.OutputStream.write(pcm_chunk)
    │                           │ [loop...]
    │◄─ position_changed(ms) ───│ QMetaObject.invokeMethod（每 250ms）
    │◄─ end_reached() ──────────│ stream 耗尽时
    │
    │── pause() ──────────────► _pause_event.set()
    │── seek(ms) ─────────────► _seek_queue.put(ms)（后台线程检查并重启 stream）
    │── stop() ───────────────► _stop_event.set()
```

**seek 实现**：后台线程在每个 PCM chunk 循环中检查 `_seek_queue`。收到 seek 请求时，调用 `bridge.seek(ms)` 重新获取 stream，刷新位置计数器，继续泵数据。

**音量**：通过对 PCM 样本乘以音量因子（0.0–1.0）实现软件音量控制。

**位置轮询**：后台线程维护 `_position_ms`（根据写入的样本数累加），每 250ms 通过 `QMetaObject.invokeMethod` 发射 `position_changed`，与 VLCBackend 的轮询定时器对称。

---

## 6. lyrics.py — Spotify 歌词

**职责**：调用 `color-lyrics/v2` 接口，解析 TTML/line 格式歌词为 `list[LyricLine]`。

```python
class SpotifyLyrics:
    async def fetch(self, track_id: str, token: str) -> list[LyricLine]
```

Spotify 歌词 API 返回 JSON 中的 `lyrics.lines` 数组。每行有 `startTimeMs`、`endTimeMs`、`words` 字段（逐字时为数组，非逐字时为单个字符串）。解析后统一为 `LyricLine(start_ms, end_ms, text, words=[LyricWord(...)])` 格式。

无歌词时返回空列表，触发 UI 层"暂无歌词"降级。

---

## 7. app_controller.py 修改

新增字段：
```python
self._spotify_auth: SpotifyAuth
self._spotify_client: SpotifyClient | None
self._librespot: LibrespotBackend
self.spotify_auth_changed = pyqtSignal(bool)
```

`init()` 中恢复 Spotify session：读取 sp_dc → 若存在则初始化 `SpotifyClient`，发射 `spotify_auth_changed(True)`。

`_get_platform_client()` 添加 `"spotify"` 分支。

`play_track()` 修改：检测 `track.platform == "spotify"` 时，停止 VLC，改用 `self._librespot.play(track.id)`，并连接 librespot 的 signals 到 player 状态机。

`_wire_internal()` 添加 librespot 信号连接（与 VLC 信号连接对称）。

新增方法：
```python
async def ensure_spotify_auth(self, parent=None) -> bool
```

---

## 8. app_window.py 修改

`_on_platform_login()` 添加：
```python
elif platform_id == "spotify":
    asyncio.ensure_future(self._ctrl.ensure_spotify_auth(self))
```

`_wire_signals()` 添加：
```python
ctrl.spotify_auth_changed.connect(
    lambda ok: self.sidebar.set_platform_status("spotify", ok)
)
self.sidebar.set_platform_status("spotify", ctrl.is_spotify_authenticated)
```

---

## 9. requirements.txt 新增依赖

```
librespot-python>=0.0.5
sounddevice>=0.4.7
pyobjc-framework-MediaPlayer>=10.0
```

---

## 10. 边界条件与错误处理

| 场景 | 处理方式 |
|------|----------|
| librespot-python 未安装 | 与 VLC 相同：启动时 warn，`play()` 时 emit `error_occurred` |
| sp_dc 过期（API 返回 401） | `SpotifyAuth.get_access_token()` 检测到 401 → 用 sp_dc 重新换 token；sp_dc 本身失效则提示重新登录 |
| Premium 账号限制 | librespot 初始化失败时 emit error，UI 层显示"需要 Spotify Premium" |
| 搜索 API 结构变更 | `client.py` 捕获解析异常，返回空列表 + warn 日志 |
| seek 精度 | sounddevice 输出为 16bit/44100Hz PCM，seek 精度约 ±20ms（一个 chunk） |

---

## 11. 不在范围内

- macOS 锁屏信息（`NSNowPlayingInfoCenter`）—— Phase 6 任务
- 播放历史写入 SQLite —— 已在 `play_track()` 中有位置预留，Phase 6 补充
- Spotify 首页推荐（`home` GraphQL）—— Phase 6 任务
