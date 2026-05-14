# Design: Next Track Prefetch — 提前预取下一首消除切歌黑屏

**Date**: 2026-05-13
**Branch**: feat/phase4-youtube-music
**Scope**: 在当前曲目播放结束前预取下一首流 URL（及 autoplay 推荐），消除 8-15s 切歌延迟

---

## Problem

切歌时各平台延迟：
- **网易云**：`get_stream_url()` 每次发 HTTP 请求，200-800ms
- **YouTube Music**：yt-dlp 解析，8-15 秒
- **Spotify**：librespot 下载整首曲目，5-15 秒（本次范围外，见下）

当前无任何预取机制，`play_next()` 触发后才开始网络请求，导致切歌时有明显空白。

## Solution Overview

监听 `position_changed` 信号，当当前曲目剩余时间低于平台阈值时，后台预取：
1. 队列有下一首 → 预取其流 URL，缓存到 `track.stream_url`
2. 队列将空 → 预取推荐列表 + 第一首推荐的流 URL

`play_next()` / `play_track()` 命中缓存时直接使用，跳过网络请求。

---

## Architecture

### 触发机制

在 `AppController._on_position_changed(position_ms)` 中（新增，连接现有 `position_changed` 信号）：

```
条件：
  remaining_ms = state.duration_ms - position_ms
  threshold_ms = _PREFETCH_THRESHOLD[current_platform]

  remaining_ms <= threshold_ms
  AND duration_ms > 0        ← 已知时长
  AND not _prefetch_done     ← 本曲只触发一次
  AND _prefetch_task is None ← 未已在进行

退化条件（duration_ms == 0）：
  position_ms >= 30_000   ← 播放满 30s 后触发
  （仅 netease 极少数情况遇到，ytmusic/spotify 均有时长）
```

### 平台阈值

```python
_PREFETCH_THRESHOLD: dict[str, int] = {
    "netease": 5_000,   # 5s  — get_stream_url ≈ 200-800ms
    "ytmusic": 25_000,  # 25s — yt-dlp 解析 ≈ 8-15s
    "spotify": 20_000,  # 20s — 提前准备 autoplay 推荐；stream_url fetch 本身即时
}
```

### 新增状态（AppController）

```python
self._prefetch_task: asyncio.Task | None = None
self._prefetch_done: bool = False
self._prefetched_next_track: Track | None = None
self._prefetched_autoplay: list[Track] | None = None
```

调用 `play_track()` 时全部重置，保证新曲目重新计算。

---

## Component Changes

### 1. `core/queue.py` — 新增 `peek_next()`

```python
def peek_next(self, repeat_mode: str = "none") -> Track | None:
    """Return next track without advancing index."""
    if repeat_mode == "one":
        return self.current_track
    nxt = self._index + 1
    if nxt >= len(self._tracks):
        if repeat_mode == "all":
            return self._tracks[0] if self._tracks else None
        return None
    return self._tracks[nxt]
```

### 2. `core/app_controller.py` — 主要改动

#### 新增常量

```python
_PREFETCH_THRESHOLD: dict[str, int] = {
    "netease": 5_000,
    "ytmusic": 25_000,
    "spotify": 20_000,
}
```

#### 连接 position_changed 信号

在 `__init__` 的信号连接区：
```python
self.position_changed.connect(self._on_position_changed)
```

#### `_on_position_changed(position_ms)`（新增）

```python
def _on_position_changed(self, position_ms: int) -> None:
    state = self.current_state
    if state.status != "playing" or self._prefetch_done:
        return
    platform = state.current_track.platform if state.current_track else None
    if platform is None:
        return
    duration_ms = state.duration_ms
    threshold = _PREFETCH_THRESHOLD.get(platform, 5_000)
    if duration_ms > 0:
        should_prefetch = (duration_ms - position_ms) <= threshold
    else:
        should_prefetch = position_ms > 0  # fallback: any progress (rare)
    if should_prefetch and self._prefetch_task is None:
        self._prefetch_done = True
        self._prefetch_task = asyncio.ensure_future(self._prefetch_next())
```

#### `_prefetch_next()`（新增）

```python
async def _prefetch_next(self) -> None:
    try:
        state = self.current_state
        if state.current_track is None:
            return
        repeat_mode = state.repeat_mode
        next_track = self._queue.peek_next(repeat_mode)

        if next_track is not None:
            await self._prefetch_stream_url(next_track)
        else:
            # 队列将空 → 预取推荐
            client = self._get_platform_client(state.current_track.platform)
            if client is None:
                return
            recs = await client.get_recommendations(state.current_track)
            if recs:
                self._prefetched_autoplay = recs
                await self._prefetch_stream_url(recs[0])
    except Exception:
        pass  # 预取失败不影响主流程
    finally:
        self._prefetch_task = None

async def _prefetch_stream_url(self, track: Track) -> None:
    if track.stream_url:
        return  # 已有缓存
    if track.platform == "spotify":
        return  # get_stream_url 即时；librespot 下载超出本次范围
    client = self._get_platform_client(track.platform)
    if client is None:
        return
    url = await client.get_stream_url(track)
    if url:
        track.stream_url = url
    self._prefetched_next_track = track
```

#### `play_track()` 修改（1 处）

```python
# 修改前
url = await client.get_stream_url(track)

# 修改后
url = track.stream_url or await client.get_stream_url(track)
```

同时在函数开头重置预取状态：
```python
self._prefetch_done = False
self._prefetched_next_track = None
self._prefetched_autoplay = None   # 用户手动切歌时，旧推荐作废
if self._prefetch_task:
    self._prefetch_task.cancel()
    self._prefetch_task = None
```

#### `play_next()` 修改

```python
async def play_next(self) -> None:
    next_track = self._queue.next(self.current_state.repeat_mode)
    if next_track is not None:
        await self.play_track(next_track)
        return
    # 队列空：优先使用预取的推荐
    if self._prefetched_autoplay:
        recs = self._prefetched_autoplay
        self._prefetched_autoplay = None
        self._queue.set_tracks(recs, 0)
        self._emit_queue_changed()
        await self.play_track(recs[0])
    else:
        await self._autoplay(self.current_state.current_track)
```

---

## Error Handling

| 情况 | 处理 |
|------|------|
| 预取中途用户跳歌 | `play_track()` cancel 旧 task，重置状态，新曲正常 fetch |
| 预取异常（网络、API 限流）| `except Exception: pass`，`play_next()` 走原有路径 |
| 单曲循环 | `peek_next("one")` 返回当前曲，stream_url 已有，跳过 |
| 全部循环 | `peek_next("all")` 返回队列首曲，正常预取 |
| 队列空且推荐失败 | `_prefetched_autoplay = None`，`_autoplay()` 重试 |
| URL 过期 | 暂不处理（URL 有效期通常数分钟，足够切歌使用） |

## Out of Scope

- **Spotify 音频预下载**：需要重构 `LibrespotBridge`，另立任务
- **Spotify 阈值**：触发预取但仅对 autoplay 推荐有效，音频延迟无改善
- **并发预取多首**：只预取下一首，避免浪费带宽

---

## Files Changed

| 文件 | 变更 |
|------|------|
| `core/queue.py` | 新增 `peek_next()` |
| `core/app_controller.py` | 新增常量、状态、`_on_position_changed`、`_prefetch_next`、`_prefetch_stream_url`；修改 `play_track`、`play_next` |
| `tests/test_queue.py` | 新增 `peek_next` 测试 |
| `tests/test_app_controller.py` | 新增预取逻辑测试 |
