# smhelper

自媒体运营助手。第一阶段聚焦小红书直播助手：中心节点监听直播间、录制与处理分段、生成候选问题；远端节点负责账号浏览器操作。

## 本地开发启动

默认配置：

- MySQL: `mysql+pymysql://root:@127.0.0.1:3306/smhelper`
- Redis broker: `redis://:tbui-666@127.0.0.1:6379/0`
- Redis result backend: `redis://:tbui-666@127.0.0.1:6379/1`

`smhelper` 数据库需要先存在；`db init` 只创建表，不创建 MySQL database。

```bash
uv sync
uv run smhelper db init
uv run smhelper live seed-dev --room-url "https://www.xiaohongshu.com/livestream/<room_id>" --account-id account-1 --storage-state-path data/auth/account-1/storage_state.json --node-id node-1
uv run smhelper live seed-dev --room-url "https://www.xiaohongshu.com/livestream/<room_id>" --account-id account-1 --storage-state-path data/auth/account-1/storage_state.json --node-id node-1 --with-review-demo
uv run smhelper live doctor
uv run smhelper web --host 127.0.0.1 --port 8000
```

启动后访问 `http://127.0.0.1:8000/admin` 查看 SQLAdmin 后台。

如需显式指定数据库：

```bash
uv run smhelper db init --database-url "mysql+pymysql://root:@127.0.0.1:3306/smhelper"
uv run smhelper live doctor --database-url "mysql+pymysql://root:@127.0.0.1:3306/smhelper"
uv run smhelper web --database-url "mysql+pymysql://root:@127.0.0.1:3306/smhelper"
```

`live doctor` 是只读检查命令，不会创建表或写入业务数据。它用于确认数据库表、直播任务、账号登录态、Worker 节点、Celery、ffmpeg、ASR 和 LLM 配置是否满足第一阶段本地测试前置条件。

`live seed-dev` 是本地开发数据入口，会创建或更新一组最小 LiveTask、PlatformAccount、AccountAuthState 和 WorkerNode 记录。它只用于本地测试，不替代后续正式后台录入流程。
`live seed-dev --with-review-demo` 会额外创建一条待审核候选问题和一条 waiting session，并将对应 LiveTask 置为 running，便于在 SQLAdmin 中直接测试 Approve 派发流程。

## Worker 入口

中心 worker 负责直播观察、分段处理、ASR 和 LLM。启动前需要配置 ASR 和 LLM：

```bash
uv run celery -A smhelper.infrastructure.task_queue.celery.center_worker.celery_app worker -Q center.live -l info
```

小红书远端操作节点负责 CloakBrowser 入场、保持会话、发送留言和回传结果：

```bash
uv run celery -A smhelper.platforms.xhs.celery_worker.celery_app worker -Q node.<node_id>.browser -l info
```

第一阶段旧的 `live-assistant` CLI 只用于可行性验证，正式链路以后以 Web 后台、中心 worker 和远端 worker 为准。
