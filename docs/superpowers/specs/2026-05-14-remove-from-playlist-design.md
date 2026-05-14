# 从歌单移出功能设计

**日期:** 2026-05-14  
**范围:** 三个平台（网易云、Spotify、YouTube Music）"我的库"歌单详情页单曲"移出歌单"功能

---

## 目标

在库页面歌单曲目列表的每首歌曲悬停时，新增第三个按钮"移出"，允许用户将该曲目从当前歌单中移除。

## 交互方式

鼠标悬停在歌曲行上，显示三个按钮：`[加队列] [加歌单] [移出]`。"移出"按钮仅在库页面（歌单详情视图）启用，其他页面（搜索、主页）的 TrackRow 不显示此按钮。

移除成功后：立即从 UI 列表中删除该行，显示 toast "已从歌单移出"。失败时显示错误 toast。

---

## 各层改动

### Layer 1: core/models.py

`Track` 新增可选字段：
```python
playlist_item_id: str | None = None
```
用途：存储 YTMusic 的 `setVideoId`（歌单内唯一标识，移除时必需）。其他平台忽略此字段。

### Layer 2: platforms/base.py

新增非抽象方法（默认返回 False，不破坏未实现的平台）：
```python
async def remove_track_from_playlist(self, playlist_id: str, track: Track) -> bool:
    return False
```

### Layer 3: 各平台实现

**网易云** (`platforms/netease/client.py`)  
复用 `/weapi/playlist/manipulate/tracks`，`op: "del"`，其余参数与 add 一致。

**Spotify** (`platforms/spotify/client.py`)  
REST API：`DELETE https://api.spotify.com/v1/playlists/{id}/tracks`  
Body: `{"tracks": [{"uri": "spotify:track:{track_id}"}]}`  
使用 `_auth.get_access_token()` 获取 token。

**YouTube Music** (`platforms/ytmusic/client.py`)  
- `get_playlist_tracks` 加载时从原始数据提取 `setVideoId` → `track.playlist_item_id`
- 普通歌单：`ytm.remove_playlist_items(playlist_id, [{"videoId": ..., "setVideoId": ...}])`
- 喜欢的歌曲（`LM`）：`ytm.rate_song(track.id, "INDIFFERENT")`

### Layer 4: core/app_controller.py

```python
async def remove_track_from_playlist(self, track: Track, playlist: Playlist) -> bool
```
模式与 `add_track_to_playlist` 相同：平台匹配校验 → 调用客户端 → 成功时清除该歌单的 tracks cache。

### Layer 5: ui/components/track_row.py

- 新增 `remove_clicked = pyqtSignal(object)` 信号
- 新增 `_remove_btn` (文字"移出")，默认隐藏
- 新增 `set_removable(show: bool)` 方法控制显示
- `_reposition_btn` 支持 2 按钮（默认）或 3 按钮（可移除模式）布局

### Layer 6: ui/pages/library_page.py

- 新增 `status_message = pyqtSignal(str, bool)` 信号（提供给 app_window 显示 toast）
- 维护 `_current_playlist: Playlist | None = None`
- `_display_tracks(tracks, playlist)` 增加 `playlist` 参数，为 TrackRow 调用 `set_removable(True)` 并连接 `remove_clicked`
- 新增 `_on_remove_track(track)` 异步处理器：调用 ctrl → 成功移除列表行 + 发 toast；失败发错误 toast
- 新增 `_remove_track_from_view(track)` 从 QListWidget 移除对应行

### Layer 7: ui/app_window.py

单行改动：
```python
self._library_page.status_message.connect(self._status_toast.popup)
```

---

## 边界情况

- 移除正在播放的歌曲：只从列表移除，不影响播放
- YTMusic `playlist_item_id` 为 None（例如从缓存加载的旧数据）：remove 返回 False，显示错误 toast
- YTMusic 喜欢的歌曲（LM）：调用 rate_song INDIFFERENT 实现取消喜欢
- 网络失败：捕获异常，显示错误 toast，不移除 UI 行
