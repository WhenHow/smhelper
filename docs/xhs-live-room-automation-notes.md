# 小红书直播间自动化观察记录

本文档记录 2026-05-28 使用 CloakBrowser 对小红书 Web 直播间页面的实测结论，用于后续实现直播助手 CLI 的进入直播间、留言、静音处理和拉流地址提取能力。

## 1. 观察样本

正在直播的直播间：

```text
https://www.xiaohongshu.com/livestream/570294708029245530?track_id=live_total_chat%406a1807af346a760015a7c681&source=web_feed
```

已结束的直播间：

```text
https://www.xiaohongshu.com/livestream/570291385754642634
```

观察方式：

- 使用 CloakBrowser 可见窗口。
- 使用持久账号 profile：`.smhelper/browser-profiles/xhs/account-1`。
- 通过 Playwright 直接读取 DOM、`video` 元素和网络请求，不使用 OCR。
- 未实际发送直播间留言，只填入草稿验证输入框和发送按钮行为。

## 2. 进入直播间

打开直播间 URL 后，在线直播间页面标题类似：

```text
九方智投证券投资咨询的小红书直播间
```

已结束直播间页面标题类似：

```text
和时玉润的小红书直播间
```

建议 CLI 使用账号对应的持久 profile 打开直播间：

```text
.smhelper/browser-profiles/xhs/{account_id}
```

进入页面后不要立刻判断状态，应等待以下任一条件出现：

- `.live-finish .live-status`
- `.player-ref-container.xgplayer-is-live`
- `.main-player video`
- 拉流请求中出现 `.flv` 或 `.m3u8`

## 3. 判断是否正在直播

### 3.1 已结束状态

已结束直播间存在明确 DOM：

```css
.live-finish
.live-finish .live-status
```

其中 `.live-finish .live-status` 文本为：

```text
直播已结束
```

已结束直播间的实测特征：

- `video` 数量为 `0`。
- 没有 `.flv` / `.m3u8` 拉流请求。
- 页面主体包含 `直播已结束`、`累计...赞`、主播名和关注按钮。
- `.live-chat` 可能仍存在，但内容为空，不能用它判断正在直播。

### 3.2 正在直播状态

在线直播间的实测特征：

- 存在可见视频元素：

```css
.main-player video
```

- 播放器根节点包含直播 class：

```css
.player-ref-container.xgplayer-is-live
```

- `video.duration` 为 `Infinity`。
- `video.readyState` 达到可播放状态，实测为 `4`。
- 网络请求中出现真实拉流地址。
- 页面包含在线观众、聊天消息和留言输入区。

建议判断优先级：

1. 如果 `.live-finish .live-status` 可见，且文本包含 `直播已结束`，判定为 `not_live`。
2. 否则如果存在可见 `.main-player video`，且 `.player-ref-container` 包含 `xgplayer-is-live`，判定为 `live`。
3. 否则如果已捕获 `.flv` / `.m3u8` 拉流地址，判定为 `live`。
4. 否则继续短时间轮询；超时后返回 `unknown`。

不要只用单一信号判断：

- 只看 `video` 会受页面加载时机影响。
- 只看网络请求会受捕获时机影响。
- 只看聊天区不可靠，已结束页面仍可能保留 `.live-chat` 外壳。

## 4. 留言输入与发送

留言输入框 selector：

```css
#input-area
```

实测 DOM：

```html
<div id="input-area" contenteditable="true" class="input-editable" data-placeholder="说点什么..."></div>
```

输入框特征：

- 使用 `contenteditable="true"`，不是普通 `input` 或 `textarea`。
- 空状态时 `data-placeholder="说点什么..."`。
- 填入内容后，`data-placeholder` 变为空，class 变为 `input-editable with-button`。

填入内容后会出现发送按钮：

```css
button.send
```

实测 DOM：

```html
<button class="send"> 发送 </button>
```

建议发送流程：

1. 等待 `#input-area` 可见。
2. 使用 Playwright `locator("#input-area").fill(comment)` 填入留言。
3. 等待 `button.send` 可见。
4. 点击 `button.send`。
5. 记录发送动作和结果。

注意事项：

- 本次只验证了填草稿后发送按钮出现，未点击真实发送，避免污染直播间。
- 后续实现真实发送时，应由 CLI 明确传入 `--comment` 后才发送。
- 发送后需要根据 UI 状态、错误提示或消息列表变化补充结果判断。

## 5. 静音判断与取消静音

小红书直播页使用 xgplayer。不能只看 `video.muted` 判断静音。

实测初始静音状态：

```text
video.muted = false
video.volume = 0
```

同时播放器根节点包含：

```css
.player-ref-container.xgplayer-volume-muted
```

静音图标 selector：

```css
.xgplayer-icon-muted
```

音量按钮 selector：

```css
.xgplayer-volume
```

取消静音流程：

1. 如果 `.player-ref-container` 包含 `xgplayer-volume-muted`，或者 `.xgplayer-icon-muted` 可见，判定为静音。
2. 点击 `.xgplayer-volume`。
3. 再次读取 `video.volume` 和播放器 class。

实测点击 `.xgplayer-volume` 后：

```text
video.volume = 0.6
```

播放器 class 变为：

```text
xgplayer-volume-active xgplayer-volume-large
```

建议判断：

- 首选 `.player-ref-container.xgplayer-volume-muted`。
- 兜底检查 `.xgplayer-icon-muted`。
- 不以 `video.muted` 作为唯一依据。

## 6. 拉流地址提取

直播页 `video.src` 不是原始拉流地址，而是 blob：

```text
blob:https://www.xiaohongshu.com/...
```

因此不能从 `video.src` 或 `video.currentSrc` 直接拿直播流。

应从网络请求或 Performance Resource Timing 中提取：

```javascript
performance.getEntriesByType("resource")
```

过滤关键字：

```text
.flv
.m3u8
hls
live-source-play
```

在线直播间实测拉流地址：

```text
https://live-source-play.xhscdn.com/live/570294708029245530_hcv520e.flv?userId=6a1701760000000002000400
```

建议提取规则：

1. 优先从 Playwright `request` / `response` 事件中捕获资源请求。
2. 兜底从 `performance.getEntriesByType("resource")` 中过滤。
3. 优先返回 `.flv` 或 `.m3u8`。
4. 记录拉流地址和发现来源，便于后续 ffmpeg 录制链路使用。

## 7. CLI MVP 建议行为

建议新增命令形态：

```bash
uv run smhelper live-assistant enter-room \
  --account account-1 \
  --room-url "https://www.xiaohongshu.com/livestream/..." \
  [--comment "留言内容"] \
  [--no-proxy]
```

建议流程：

1. 使用账号 profile 打开 CloakBrowser。
2. 导航到直播间 URL。
3. 等待并判断直播状态。
4. 如果直播已结束，打印 `not_live` 并退出。
5. 如果正在直播，提取并打印拉流地址。
6. 如果检测到静音，点击 `.xgplayer-volume` 取消静音。
7. 如果传入 `--comment`，填入 `#input-area` 并点击 `button.send`。
8. 打印结构化结果，包括：
   - 直播状态。
   - 是否找到视频元素。
   - 是否找到拉流地址。
   - 是否取消静音。
   - 是否尝试留言。
   - 留言发送结果或失败原因。

## 8. 风险与待确认点

- 小红书页面 selector 可能随前端版本变化，需要把 selector 集中在基础设施适配层，避免散落在 CLI。
- 直播间页面与探索页不同，探索页的登录状态可用左侧 `我` 判断，但直播间页面可能不展示同样的侧边导航，不应复用探索页登录判断。
- 当前只验证了留言控件和发送按钮出现，未实测点击发送后的成功/失败反馈。
- 拉流地址中的 `userId` 和签名参数可能与账号、会话或时间有关，不能长期缓存。
- 若页面加载慢，应设置明确超时并输出当前状态，避免 CLI 无提示等待。
