# SomniaMusicPlayer — 开发 Spec

> 版本：v1.0  
> 平台：macOS 13+  
> 技术栈：Python 3.12 + PyQt6  
> 风格：深色现代（Spotify 桌面端风格）

---

## 1. 项目概览

SomniaMusicPlayer 是一款 macOS 原生风格的第三方音乐播放器，聚合 Spotify、YouTube Music 和网易云音乐三个平台，不使用任何官方公开 API，通过逆向平台内部请求协议实现完整功能（搜索、播放、歌词、收藏等）。

### 核心原则
- **无官方 API**：所有平台通信均通过逆向内部 HTTP 请求实现
- **无离线缓存**：所有内容实时流式获取
- **自定义 UI**：完全自绘界面，非内嵌 WebView 展示
- **登录安全**：通过隐藏 WebView 自动捕获 Cookie/Token，用户无需手动操作

---

## 2. 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| UI 框架 | PyQt6 | 主界面渲染 |
| Web 引擎 | PyQt6 WebEngineWidgets | 登录 Cookie 捕获 |
| Spotify 音频 | `librespot-python` | Spotify 流媒体解密播放 |
| YouTube Music | `ytmusicapi` | 搜索/元数据/流地址 |
| 网易云 | 自实现（weapi/eapi 加密） | 全功能逆向 |
| 音频播放引擎 | `python-vlc` (VLC bindings) | YTMusic / 网易云音频 |
| 歌词解析 | 自实现 LRC/TTML 解析器 | 逐字歌词渲染 |
| HTTP 客户端 | `httpx` (async) | 所有网络请求 |
| 异步运行时 | `asyncio` + `qasync` | 非阻塞 UI |
| 数据持久化 | `SQLite` via `aiosqlite` | 播放历史、设置、登录态 |
| 打包 | `PyInstaller` | 生成 .app |

---

## 3. 项目目录结构

```
SomniaMusicPlayer/
├── main.py                        # 入口，启动 QApplication
├── spec.md                        # 本文件
├── requirements.txt
├── assets/
│   ├── icons/                     # SVG 图标集
│   ├── fonts/                     # 自定义字体（如 Inter）
│   └── default_cover.png          # 默认封面占位图
│
├── core/
│   ├── __init__.py
│   ├── player.py                  # 统一播放器状态机
│   ├── queue.py                   # 播放队列管理
│   └── lyrics_engine.py           # 歌词时间轴引擎
│
├── platforms/
│   ├── __init__.py
│   ├── base.py                    # AbstractPlatform 基类
│   ├── spotify/
│   │   ├── __init__.py
│   │   ├── auth.py                # sp_dc Cookie → access_token
│   │   ├── client.py              # 内部 API 请求封装
│   │   ├── librespot_bridge.py    # librespot 进程管理 + 音频桥接
│   │   └── lyrics.py             # Spotify 内部歌词 API
│   ├── ytmusic/
│   │   ├── __init__.py
│   │   ├── auth.py                # WebView 捕获 headers
│   │   ├── client.py              # ytmusicapi 封装
│   │   └── lyrics.py             # LRCLIB / 外部歌词源
│   └── netease/
│       ├── __init__.py
│       ├── auth.py                # WebView 捕获 MUSIC_U Cookie
│       ├── crypto.py              # weapi / eapi / linux_api 加密实现
│       ├── client.py              # 逆向 API 封装
│       └── lyrics.py             # 网易云歌词 API（含逐字 TTML）
│
├── ui/
│   ├── __init__.py
│   ├── app_window.py              # 主窗口（QMainWindow）
│   ├── theme.py                   # 全局颜色/字体/尺寸常量
│   ├── components/
│   │   ├── sidebar.py             # 左侧导航栏
│   │   ├── now_playing_bar.py     # 底部播放控制栏
│   │   ├── lyrics_view.py         # 歌词逐字动画视图
│   │   ├── cover_art.py           # 封面图（圆角+阴影+旋转动画）
│   │   ├── search_bar.py          # 搜索框 + 平台切换 Tab
│   │   ├── track_list.py          # 歌曲列表（虚拟列表）
│   │   ├── platform_badge.py      # 平台标识徽章组件
│   │   ├── volume_slider.py       # 自定义音量滑块
│   │   ├── progress_bar.py        # 播放进度条（可拖拽）
│   │   └── login_dialog.py        # 登录弹窗（内嵌 WebView）
│   └── pages/
│       ├── home_page.py           # 首页（推荐 + 最近播放）
│       ├── search_page.py         # 搜索结果页
│       ├── library_page.py        # 我的库（收藏/歌单）
│       └── settings_page.py       # 设置页
│
├── db/
│   ├── __init__.py
│   ├── schema.sql                 # 数据库建表语句
│   └── repository.py             # 数据访问层
│
└── utils/
    ├── __init__.py
    ├── image_loader.py            # 异步封面图加载
    ├── lrc_parser.py              # LRC 格式解析
    └── ttml_parser.py             # TTML/逐字歌词解析
```

---

## 4. 功能列表

### 4.1 账号与登录

| 功能 | 说明 |
|------|------|
| Spotify 登录 | 弹出隐藏 WebView 加载 `accounts.spotify.com`，捕获 `sp_dc` Cookie 后关闭 |
| YouTube Music 登录 | 弹出隐藏 WebView 加载 `music.youtube.com`，登录完成后捕获完整请求头集合（Cookie、`X-Goog-AuthUser` 等） |
| 网易云登录 | 弹出隐藏 WebView 加载 `music.163.com`，捕获 `MUSIC_U` + `__csrf` Cookie |
| 登录态持久化 | 加密存储到 SQLite，下次启动自动复用 |
| Token 自动刷新 | 检测到 401 时静默触发重新鉴权流程 |
| 多平台同时登录 | 三个平台独立管理，可同时保持登录态 |

### 4.2 搜索

| 功能 | 说明 |
|------|------|
| 全局搜索 | 一个搜索框同时查询三个平台 |
| 平台筛选 | 搜索结果支持按平台 Tab 切换 |
| 结果类型 | 歌曲、专辑、艺术家、歌单 |
| 搜索防抖 | 输入停止 400ms 后触发，避免频繁请求 |

### 4.3 播放

| 功能 | 说明 |
|------|------|
| Spotify 播放 | `librespot-python` 处理 OGG Vorbis 加密流，本地解码输出 PCM |
| YouTube Music 播放 | 获取 YouTube 音频流 URL，交由 VLC 播放 |
| 网易云播放 | 获取带签名的 CDN 音频 URL，交由 VLC 播放 |
| 播放/暂停/停止 | 统一播放器状态机控制 |
| 上一首/下一首 | 队列管理 |
| 进度拖拽 | 支持毫秒级 Seek |
| 音量控制 | 0–100，记忆上次音量 |
| 循环模式 | 顺序 / 单曲循环 / 随机 |
| 媒体键支持 | 响应键盘媒体键（播放/暂停/切歌） |
| macOS 锁屏信息 | 通过 `NSNowPlayingInfoCenter` 显示封面和进度（需 PyObjC） |

### 4.4 歌词

| 功能 | 说明 |
|------|------|
| 歌词来源 - Spotify | 调用 `spclient.wg.spotify.com/color-lyrics/v2` 内部接口获取 TTML 逐字歌词 |
| 歌词来源 - 网易云 | 调用逆向歌词 API，获取 `klyric`（逐字）或 `lrc`（逐行）格式 |
| 歌词来源 - YouTube Music | ① YouTube Music 内部接口 → ② Musixmatch（开发者内置 key，逐字）→ ③ LRCLIB.net 兜底 |
| 逐字高亮 | 每个字按时间轴独立着色，当前字高亮，已过字渐暗 |
| 滚动动画 | 当前行自动居中，平滑滚动（`QPropertyAnimation`） |
| 歌词/封面切换 | 播放区可在大封面和全屏歌词视图之间切换 |
| 无歌词降级 | 无逐字时自动降级为逐行，无歌词时显示"暂无歌词" |

### 4.5 我的库

| 功能 | 说明 |
|------|------|
| 读取各平台收藏歌单 | 调用各平台内部"我的音乐库"接口 |
| 读取已收藏歌曲 | 展示各平台"喜欢的歌曲" |
| 播放歌单 | 一键加入队列 |
| 平台标识 | 每首歌显示来源平台徽章 |

### 4.6 首页推荐

| 功能 | 说明 |
|------|------|
| Spotify | 调用内部 `home` 接口获取每日推荐/最近播放 |
| YouTube Music | `ytmusicapi.get_home()` |
| 网易云 | 每日推荐歌曲 + 推荐歌单接口 |

---

## 5. UI 设计规范

### 5.1 整体布局

```
┌─────────────────────────────────────────────────────────┐
│  [侧边栏 200px]  │        [主内容区 flex]                 │
│                  │                                        │
│  🔍 搜索          │   ┌──── 当前页面内容 ────┐             │
│  🏠 首页          │   │                      │             │
│  📚 我的库        │   │                      │             │
│  ─────────        │   │                      │             │
│  平台账号         │   └──────────────────────┘             │
│  ○ Spotify        │                                        │
│  ○ YouTube Music  │  [歌词/封面区 可展开至全屏]            │
│  ○ 网易云         │                                        │
│  ─────────        │                                        │
│  ⚙️ 设置          │                                        │
│                  │                                        │
├──────────────────┴────────────────────────────────────  │
│  [底部播放栏 90px 常驻]                                    │
│  封面缩略图  歌名/歌手  ←  ⏸  →  进度条  🔀 🔁  🔊       │
└─────────────────────────────────────────────────────────┘
```

### 5.2 颜色系统

```python
# theme.py
COLORS = {
    # 背景层级
    "bg_base":       "#0D0D0D",   # 最底层背景
    "bg_surface":    "#161616",   # 卡片/面板
    "bg_elevated":   "#1E1E1E",   # 悬浮元素
    "bg_hover":      "#2A2A2A",   # 悬停态

    # 强调色
    "accent":        "#1DB954",   # Spotify 绿（主强调）
    "accent_dim":    "#158A3E",   # 暗化强调

    # 文字
    "text_primary":  "#FFFFFF",
    "text_secondary":"#A0A0A0",
    "text_muted":    "#5A5A5A",

    # 平台标识色
    "platform_spotify":  "#1DB954",
    "platform_ytmusic":  "#FF0000",
    "platform_netease":  "#E60026",

    # 功能色
    "border":        "#2C2C2C",
    "divider":       "#1F1F1F",
    "lyrics_active": "#FFFFFF",
    "lyrics_past":   "#4A4A4A",
    "lyrics_future": "#6E6E6E",
}
```

### 5.3 字体

```python
FONTS = {
    "family":        "Inter",     # 首选，降级到 SF Pro Display
    "size_xs":       10,
    "size_sm":       12,
    "size_md":       14,
    "size_lg":       18,
    "size_xl":       24,
    "size_lyrics":   22,          # 歌词字号
}
```

### 5.4 关键组件视觉规范

**底部播放栏 (`now_playing_bar.py`)**
- 高度：90px，背景 `bg_surface` + 顶部 1px `border` 线
- 封面缩略图：48×48px，圆角 6px
- 进度条：自定义绘制，高度 4px，悬停时扩展到 6px，滑块圆点仅悬停时显示
- 音量滑块：宽度 100px，样式同进度条

**歌词视图 (`lyrics_view.py`)**
- 背景：`bg_base`，可选封面颜色取样的渐变背景（使用 `colorthief` 提取主色）
- 当前行：字号 22px，`text_primary`，加粗
- 当前行逐字高亮：已过的字 `lyrics_past`，当前字 `accent`，未到的字 `lyrics_future`
- 非当前行：字号 18px，`lyrics_future`，缩小+透明度降低
- 滚动：`QScrollArea` + 自定义 `QPropertyAnimation`，缓动函数 `OutCubic`

**封面图 (`cover_art.py`)**
- 圆角：12px
- 阴影：`QGraphicsDropShadowEffect`，模糊半径 40px，颜色取自封面主色，透明度 80%
- 播放时旋转动画（可在设置中关闭）

**侧边栏 (`sidebar.py`)**
- 宽度：200px，不可调整
- 平台账号区显示头像（圆形）+ 用户名 + 在线状态指示点
- 导航项悬停：`bg_hover` 背景，左侧 3px `accent` 竖线

---

## 6. 数据模型

```python
# 统一的跨平台数据结构

@dataclass
class Track:
    id: str                          # 平台内部 ID
    platform: str                    # "spotify" | "ytmusic" | "netease"
    title: str
    artist: str
    artists: list[str]
    album: str
    album_cover_url: str
    duration_ms: int
    is_explicit: bool = False
    stream_url: str | None = None    # 播放时填充

@dataclass
class LyricLine:
    start_ms: int
    end_ms: int
    text: str
    words: list[LyricWord]           # 逐字时间轴

@dataclass
class LyricWord:
    start_ms: int
    end_ms: int
    text: str

@dataclass
class Playlist:
    id: str
    platform: str
    name: str
    cover_url: str
    track_count: int
    tracks: list[Track] = field(default_factory=list)

@dataclass
class PlayerState:
    status: str                      # "idle" | "loading" | "playing" | "paused" | "error"
    current_track: Track | None
    position_ms: int
    duration_ms: int
    volume: int                      # 0–100
    shuffle: bool
    repeat_mode: str                 # "none" | "one" | "all"
    queue: list[Track]
    queue_index: int
```

---

## 7. 平台逆向实现规范

### 7.1 Spotify

**鉴权流程**
```
1. WebView 加载 accounts.spotify.com/login
2. 监听 WebView CookieStore，检测到 sp_dc cookie 写入
3. 关闭 WebView，保存 sp_dc 到 SQLite（AES-256 加密）
4. 使用 sp_dc 请求 open.spotify.com/get_access_token 获取 Bearer Token
5. Token 有效期约 1 小时，过期前静默刷新
```

**音频播放（librespot 桥接）**
```
1. 启动 librespot 子进程（以 pipe 模式输出 PCM）
2. Python 端通过 subprocess.PIPE 读取 PCM 数据流
3. 使用 PyAudio 或 sounddevice 输出到系统音频设备
4. Seek 操作通过向 librespot stdin 发送命令实现
```

**关键内部 API**
```
# 搜索
GET https://api-partner.spotify.com/pathfinder/v1/query
  ?operationName=searchDesktop
  Authorization: Bearer {token}

# 歌曲元数据
GET https://spclient.wg.spotify.com/metadata/4/track/{track_id}

# 逐字歌词
GET https://spclient.wg.spotify.com/color-lyrics/v2/track/{track_id}
  Authorization: Bearer {token}
  App-Platform: WebPlayer

# 推荐首页
GET https://api-partner.spotify.com/pathfinder/v1/query
  ?operationName=home
```

### 7.2 YouTube Music

**鉴权流程**
```
1. WebView 加载 music.youtube.com
2. 用户完成 Google 登录
3. 监听 WebView 网络请求，捕获成功请求的完整 Headers：
   - Cookie
   - X-Goog-AuthUser
   - X-Goog-Visitor-Id
   - Authorization (如有)
4. 将 headers dict 保存为 ytmusicapi browser.json 格式
5. 初始化 YTMusic(headers) 实例
```

**关键功能调用**
```python
ytmusic = YTMusic("headers_auth.json")

# 搜索
results = ytmusic.search("query", filter="songs")

# 获取播放流地址（通过 yt-dlp 或内部 player endpoint）
# POST https://music.youtube.com/youtubei/v1/player
# 返回 streamingData.adaptiveFormats，选择最高质量音频流

# 首页推荐
home = ytmusic.get_home()

# 我的收藏
library = ytmusic.get_library_songs()
```

**歌词获取**
```
优先级：
1. ytmusicapi.get_watch_playlist() 中的 lyrics browseId
   → ytmusicapi.get_lyrics(browseId)
2. Musixmatch API（开发者内置 key，逐字歌词质量最佳）
   GET https://api.musixmatch.com/ws/1.1/matcher.lyrics.get
     ?q_track=xxx&q_artist=xxx&apikey={BUNDLED_KEY}
   GET https://api.musixmatch.com/ws/1.1/track.subtitle.get
     ?track_id=xxx&subtitle_format=lrc&apikey={BUNDLED_KEY}
   注：BUNDLED_KEY 由开发者申请后硬编码在 app 内，用户无需任何操作
3. 最终降级：LRCLIB.net API（无 key 公共接口，匹配率较低）
   GET https://lrclib.net/api/search?track_name=xxx&artist_name=xxx
```

### 7.3 网易云音乐

**鉴权流程**
```
1. WebView 加载 music.163.com
2. 用户完成登录（支持手机号/微信/QQ）
3. 监听 CookieStore，捕获 MUSIC_U + __csrf
4. 后续所有请求携带这两个 Cookie
```

**加密算法实现（crypto.py）**
```python
# weapi 加密（主要使用）
def weapi_encrypt(params: dict) -> dict:
    # 1. JSON 序列化 params
    # 2. 生成随机 16 字节密钥
    # 3. AES-128-CBC 加密（pad 到 key: "0CoJUm6Qyw8W8jud"）
    # 4. 再用随机密钥 AES 加密
    # 5. RSA 加密随机密钥
    # 返回 {"params": ..., "encSecKey": ...}

# eapi 加密（移动端接口使用）
def eapi_encrypt(url: str, params: dict) -> dict:
    # 使用固定 key: "e82ckenh8dichen8"
    # MD5 签名 + AES-128-ECB
```

**关键内部 API**
```
# 搜索
POST https://music.163.com/weapi/cloudsearch/pc
body: weapi_encrypt({"s": keyword, "type": 1, "limit": 30})

# 获取音乐流地址（需 MUSIC_U）
POST https://music.163.com/weapi/song/enhance/player/url/v1
body: weapi_encrypt({"ids": [song_id], "level": "exhigh", "encodeType": "flac"})

# 歌词（含逐字 klyric）
POST https://music.163.com/weapi/song/lyric/v1
body: weapi_encrypt({"id": song_id, "kv": 1, "lv": 1})
返回字段: lrc（逐行）、klyric（逐字 JSON）

# 每日推荐（需登录）
POST https://music.163.com/weapi/v3/discovery/recommend/songs

# 我的歌单
POST https://music.163.com/weapi/user/playlist
```

---

## 8. 播放器状态机

```
              ┌──────────────────────────────────┐
              │                                  │
    IDLE ──load()──► LOADING ──success()──► PLAYING
      ▲                  │                    │  │
      │              error()               pause() │
      │                  │                    │  │
      └──stop()────── ERROR          PAUSED ◄─┘  │
                                      │           │
                                   resume()    seek()
                                      │           │
                                      └──────►────┘
```

- 所有状态变更通过 Qt Signal 通知 UI 层
- 跨平台切换时，先 stop() 当前平台播放器，再 load() 新平台

---

## 9. 异步架构

```python
# 使用 qasync 桥接 asyncio 和 Qt 事件循环
# 所有网络请求必须在协程中执行，禁止阻塞主线程

# 示例模式
class SearchPage(QWidget):
    def on_search(self, query: str):
        asyncio.ensure_future(self._do_search(query))

    async def _do_search(self, query: str):
        results = await platform_client.search(query)
        self.track_list.set_tracks(results)  # 在主线程更新 UI
```

---

## 10. 数据库 Schema

```sql
-- 登录凭证（字段值 AES-256 加密存储）
CREATE TABLE credentials (
    platform    TEXT PRIMARY KEY,   -- 'spotify'|'ytmusic'|'netease'
    data        BLOB NOT NULL,      -- 加密的 JSON（cookie/token 等）
    updated_at  INTEGER NOT NULL
);

-- 播放历史
CREATE TABLE play_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    track_id    TEXT NOT NULL,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL,
    cover_url   TEXT,
    played_at   INTEGER NOT NULL
);

-- 应用设置
CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
-- 默认设置项：
-- volume: 70
-- repeat_mode: none
-- shuffle: false
-- cover_rotation: true
-- lyrics_font_size: 22
```

---

## 11. 开发阶段规划

### Phase 1 — 基础骨架
- [ ] 项目初始化，依赖安装
- [ ] 主窗口布局（侧边栏 + 主区 + 底部栏）
- [ ] 主题系统（颜色、字体常量）
- [ ] 数据库初始化
- [ ] 异步事件循环集成（qasync）

### Phase 2 — 网易云（最先验证）
- [ ] WebView 登录弹窗 + Cookie 捕获
- [ ] weapi/eapi 加密算法实现
- [ ] 搜索功能（返回结果列表）
- [ ] 获取音频流 URL + VLC 播放
- [ ] 歌词获取 + LRC/逐字解析

### Phase 3 — 歌词视图
- [ ] 逐行滚动歌词渲染
- [ ] 逐字高亮动画
- [ ] 封面颜色提取 + 渐变背景

### Phase 4 — YouTube Music
- [ ] WebView 登录 + Headers 捕获
- [ ] ytmusicapi 集成
- [ ] 音频流获取（yt-dlp 辅助）
- [ ] 歌词源接入（LRCLIB）

### Phase 5 — Spotify
- [ ] sp_dc Cookie 捕获 + Token 刷新
- [ ] librespot 子进程管理
- [ ] PCM 输出 + 音量/Seek 控制
- [ ] Spotify 内部 API（搜索/歌词/推荐）

### Phase 6 — 完善
- [ ] 首页推荐（三平台）
- [ ] 我的库（收藏/歌单读取）
- [ ] macOS 媒体键 + 锁屏信息（PyObjC）
- [ ] 播放队列 UI
- [ ] 设置页
- [ ] PyInstaller 打包为 .app

---

## 12. 依赖清单（requirements.txt）

```
PyQt6>=6.7.0
PyQt6-WebEngine>=6.7.0
qasync>=0.27.0
httpx[http2]>=0.27.0
ytmusicapi>=1.7.0
librespot-python>=0.0.5      # Spotify 音频
python-vlc>=3.0.20122        # YTMusic / 网易云音频播放
yt-dlp>=2024.5.0             # YouTube 流地址提取
colorthief>=0.2.1            # 封面主色提取
musixmatch-python>=0.0.7     # Musixmatch 歌词（开发者内置 key）
aiosqlite>=0.20.0
pycryptodome>=3.20.0         # 网易云 AES/RSA 加密
pyobjc-framework-MediaPlayer>=10.0  # macOS 锁屏信息
sounddevice>=0.4.7           # 备选音频输出（Spotify PCM）
Pillow>=10.3.0               # 图片处理
```

---

## 13. 注意事项 & 风险点

| 风险 | 说明 | 缓解策略 |
|------|------|---------|
| Spotify 逆向失效 | spclient API 结构可能更新 | 模块化隔离，单独维护 spotify/client.py |
| librespot 授权 | 需要 Premium 账号 | 文档中明确说明前提条件 |
| 网易云海外限制 | 部分音频在海外无法获取 URL | 提示用户使用代理，或切换备用音质参数 |
| YouTube 反爬 | 频繁请求可能触发验证 | 加入请求间隔，复用 session |
| WebView 登录兼容性 | 平台更新登录页可能导致捕获失败 | 提供手动输入 Cookie 的备用入口 |
| PyQt6 WebEngine 打包 | 体积大，约 300MB | 使用 --exclude 剔除不需要的 Qt 模块 |

---

*最后更新：2026-05-11*
