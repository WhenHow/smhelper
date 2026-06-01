# smhelper live 分布式执行架构设计

## 架构定位

smhelper 的长期方向是自媒体运营助手。第一阶段聚焦小红书直播助手闭环：中心节点监听直播间、录制直播内容、转写音频、生成候选问题；后台人工审核编辑后，中心调度远端操作节点使用自有授权账号进入直播间并发送留言。

架构目标不是一开始做成微服务，而是先把领域规则、应用编排、平台适配和基础设施能力分开，让系统可以从单中心节点 + 多远端操作节点自然演进。第一阶段使用 Celery + Redis 作为异步任务与远端任务投递基础设施，MySQL 作为业务状态事实源。

核心判断：适合使用轻量 DDD。这里的 DDD 不是堆目录、堆抽象，而是用领域边界控制复杂度，避免直播调度、账号风控、节点会话、浏览器自动化和数据库访问互相缠在一起。

## 当前 CLI 定位：技术可行性验证

当前项目中已有的 `login-xhs`、`room-console` 等 CLI 能力，只用于验证小红书登录、CloakBrowser 可用性、直播间评论、静音处理、`storage_state.json` 可迁移等技术可行性。

这些 CLI 不是目标生产架构的一部分，后续正式重构时不要求保留代码兼容性，也不应继续沿用现在的文件组织方式。它们的价值是沉淀已经验证过的页面流程、选择器、异常处理经验、登录态保存方式和 CloakBrowser 操作细节。

后续进入正式架构实现时，应参考这些验证逻辑，把平台相关流程迁移到 `platforms/xhs`，把 CloakBrowser 通用能力迁移到 `infrastructure/browser/cloakbrowser`，把 CLI 入口收缩为运维/调试入口。运营审核编辑不再放 CLI，而是放 SQLAdmin 后台。

## 总体架构

系统拆成六类边界：

- `core`：极小的通用内核，只放纯代码能力，例如配置对象、时钟、ID、基础异常、结果类型和通用类型定义。
- `accounts`：账号领域，负责平台账号、登录态、账号可用性、冷却、配额和账号允许节点规则。
- `workers`：执行节点领域，负责节点注册信息、心跳、能力、浏览器容量和节点队列。
- `live`：直播助手领域，负责直播任务、中心观察会话、直播片段、转写、候选问题、账号直播会话、发送任务和发送记录。
- `platforms` 与 `infrastructure`：前者放具体平台语义，例如小红书页面流程和选择器；后者放通用技术适配，例如 CloakBrowser、ffmpeg、Celery、SQLAlchemy、LiteLLM、ASR 厂商 SDK。
- `web`：后台管理入口，第一阶段使用 FastAPI + SQLAdmin。

中心节点负责直播状态判断、拉流地址提取、ffmpeg 录制、ASR、LLM、候选问题生成、账号选择、节点分配和任务投递。远端操作节点只负责小红书具体浏览器操作：加载登录态、进入直播间、保持会话、发送留言、回传结果。

## 领域边界

`accounts` 是独立领域，因为账号不是直播助手的附属对象。账号以后会被不同平台、不同功能复用，例如直播间提问、评论区互动、私信、内容发布或数据采集。

`workers` 也是独立领域，因为节点不是单纯的技术配置。它承载节点能力、在线状态、平台支持、浏览器并发容量、Celery 队列名和账号允许节点关系。

`live` 是当前第一阶段的核心业务领域，依赖账号和 Worker 的能力，但不拥有账号和 Worker 的生命周期。

## 技术适配层边界

CloakBrowser、ffmpeg、Celery、Redis、SQLAlchemy、LiteLLM 和 ASR 厂商 SDK 都不属于领域，也不应该放进 `core`。它们是基础设施适配。

CloakBrowser 应抽象为通用浏览器能力：启动浏览器、创建上下文、加载登录态、保存登录态、打开页面、执行可观测动作。它不应该知道小红书页面上的登录按钮、验证码输入框或直播间留言框。

ffmpeg 应抽象为通用媒体处理能力：长期拉流、固定时长切片、截取首尾帧、提取音频、记录命令执行结果和错误原因。它不应该知道直播任务的业务状态机。

Celery + Redis 第一阶段就是基础设施，不是后续可选项。中心侧 Celery worker 执行录制后处理、ASR、LLM 等中心任务；远端操作节点作为 Celery worker 接入，消费节点专属浏览器队列。Redis/Celery 负责投递和执行，MySQL 仍是业务状态事实源。

SQLAlchemy 应作为 persistence 适配层。文件命名不要使用 `mysql_*.py` 这类数据库厂商前缀；MySQL、PostgreSQL 的差异优先通过 DSN、迁移和少量 dialect 适配处理。

## 通信与调度

第一阶段使用中心 Redis + Celery 调度任务：

- 中心任务队列：录制片段后处理、音频提取、ASR、LLM、候选问题生成。
- 远端节点队列：每个操作节点有专属 Celery queue，例如 `node.{node_id}.browser`。
- Celery task payload 只携带任务引用和必要业务参数，例如 `dispatch_job_id`、`session_id`、`account_id`、`room_url`、`final_text`。
- 完整 `storage_state.json` 不进入 Celery payload。远端节点收到任务后通过中心 API 拉取登录态，执行后通过中心 API 回传结果。
- 第一阶段不做节点鉴权，假设中心 API、Redis 和远端节点部署在可信内网或开发环境中。模型中保留 `node_id`，后续可以补 `node_token` 而不改变核心任务模型。

## 中心 Observer 与直播录制

LiveTask 启动时，中心节点使用匿名 observer 页面打开小红书直播间 URL。小红书匿名可观看直播，因此第一阶段 observer 不登录、不占用账号池，也不发送留言。

中心 observer 的职责：

- 判断直播是否进行中。
- 捕获 `.flv` / `.m3u8` 拉流地址。
- 维持页面打开，持续观察直播状态。
- 在 ffmpeg 拉流失败且页面仍显示直播中时，重新发现新的拉流地址。

ffmpeg 使用中心 observer 提取到的流地址，不要求人工配置直播流地址。拉流地址作为运行时产物保存，可能带时效和签名，不应长期复用。

录制策略：

- 使用单个长期运行的 ffmpeg 进程。
- 通过 ffmpeg segment muxer 固定 `segment_time_seconds` 连续切片，第一阶段默认 60 秒。
- 录制不加人为抖动，优先保证连续性和稳定性。
- 正常运行中，以下一个 segment 文件出现作为前一个 segment 完成信号。
- LiveTask 停止或 ffmpeg 退出时，对最后一个 segment 做一次收尾确认。
- segment 完成后立即异步提取首尾帧和音频，ASR 和 LLM 尽快执行，不额外添加人为抖动。

如果 ffmpeg 单段录制失败，中心 observer 重新发现流地址并继续后续片段录制。连续失败超过阈值后，LiveTask 进入录制异常或直播疑似结束状态。

## 账号入场与会话模式

第一阶段采用会话模式，不采用“发送时临时进房”：

1. 中心 observer 确认直播进行中并提取 stream URL。
2. 中心启动录制链路，同时筛选所有可用账号。
3. 中心使用 HRW/Rendezvous Hashing 根据 `account_id` 在账号允许节点集合中稳定选择目标节点。
4. 所有可用账号都尝试进入直播间等待，但不同时入场。
5. 中心按 15-45 秒随机间隔逐个投递入场任务。
6. 远端节点打开 CloakBrowser，加载账号登录态，进入直播间，必要时取消静音，进入 `waiting` 状态。

账号和节点关系：

- 账号可配置多个允许节点。
- HRW 保证节点集合稳定时，同一账号尽量固定在同一节点。
- 新增或移除节点时，只迁移少部分账号。
- 节点离线或无可用浏览器容量时，顺延到 HRW 排名下一节点。
- `WorkerNode.max_browser_sessions = N` 是第一阶段核心配置。节点应按账号规模规划容量；中心调度不得超过节点容量。

## 账号直播会话

新增核心对象 `AccountLiveSession`，表示某个账号在某个直播间的一段浏览器在线会话。

核心字段：

```text
session_id
live_task_id
platform
room_url
account_id
node_id
status
opened_at
last_heartbeat_at
last_send_at
failure_reason
```

建议状态机：

```text
planned -> starting -> waiting -> sending -> waiting
                              -> failed
                              -> closing -> closed
                              -> lost
```

远端节点负责页面级健康检查并上报：浏览器是否仍在、页面是否健康、登录是否失效、输入框是否可用、发送动作是否异常。中心负责持久化状态和决定关闭/重建 session。

直播是否结束只由中心节点裁决。中心通过 ffmpeg 拉流状态和匿名 observer 页面判断直播状态；远端节点不参与 LiveTask 结束裁决。

同一个 `account_id + live_task_id` 同一时间只能存在一个 active `AccountLiveSession`。active 状态包括 `planned`、`starting`、`waiting`、`sending`、`closing`。中心创建入场任务前必须检查防重，数据库层应提供唯一约束或等价防重机制，避免并发调度导致同一账号打开多个浏览器进入同一直播间。

异常 session 可以自动重建，但必须先终结旧 session，再创建新 session。每个账号在同一场直播中最多自动重建 2 次；超过限制后标记 session failed，等待人工处理。

直播结束后的收场流程由中心统一发起：

1. 中心判定 LiveTask 结束后，将任务状态置为 `ending`。
2. 停止创建新的 CandidateQuestion、DispatchJob 和 AccountLiveSession。
3. 取消尚未投递或尚未开始的入场计划。
4. 向所有 active sessions 所在节点投递 `close_session` 任务。
5. `waiting`、`starting` session 直接关闭；`sending` session 最多等待 30 秒 grace period。
6. 发送动作在 grace period 内完成则记录结果后关闭；超时则关闭浏览器并记录 `shutdown_timeout`。
7. 节点回传 closed 后，中心将 session 标记为 `closed`。
8. 节点无响应时，中心超时后将 session 标记为 `lost`。
9. 所有 active sessions 收敛为 `closed`、`failed` 或 `lost` 后，LiveTask 进入 `ended`。

## 候选问题生成

ASR 使用厂商能力，不走 LiteLLM。代码应抽象 `SpeechToTextService` 接口，第一阶段接一个默认厂商，配置层保留切换能力。应用层只暴露转写任务，ASR adapter 内部封装同步/异步厂商差异。

LLM 使用 LiteLLM Python SDK，不启动 LiteLLM Proxy。运行环境必须默认设置：

```text
LITELLM_LOCAL_MODEL_COST_MAP=True
```

这样 LiteLLM 不会在运行时依赖 GitHub 拉取模型价格数据。第一阶段不做账单统计。LLM 支持可选 fallback；如果没有配置 fallback，失败就记录错误，不硬编码备用模型。

每个完成 ASR 的 segment 默认触发一次 LLM 生成。每次只生成并保存 1 个候选问题。LLM 输出必须 JSON 化，最小结构：

```json
{
  "question": "候选问题文本",
  "reason": "生成理由",
  "risk_level": "low"
}
```

系统保存 `question`、`reason`、`risk_level`、`raw_response` 和解析状态。若模型返回多个问题，只取第一个有效候选并记录格式偏差；解析失败则记录失败产物，不进入待审核队列。

## 后台审核与发送

第一阶段不再把人工审核编辑放 CLI，而是使用 FastAPI + SQLAdmin 搭建轻量后台管理。

SQLAdmin 第一阶段承担：

- LiveTask 状态查看。
- CandidateQuestion 查看、编辑、拒绝。
- 候选问题批准并触发发送的自定义 action。
- AccountLiveSession 状态查看。
- DispatchJob 与 SendAttempt 查看。
- PlatformAccount、WorkerNode 等基础数据管理。

SQLAdmin 后台第一阶段做单管理员登录，不做复杂用户和角色权限。账号密码从配置或环境变量读取。

`storage_state.json` 第一阶段为了观察可以明文保存在中心本地 `data/` 或受控路径中，但不提交仓库，不打印到日志，不在 SQLAdmin 中直接展示或编辑完整内容。后台只展示登录态元数据、状态和存储路径。

人工审核时允许编辑候选问题。系统保存 LLM 原始候选文本和运营最终确认发送文本，`DispatchJob.final_text` 是实际发送内容。

## 发送策略

同一 LiveTask 允许多个账号并发发送。系统不做 LiveTask 全局发送间隔，也不做 LiveTask 全局发送锁。

发送约束：

- 同一个账号同一时刻只能执行一个发送动作。
- 同一个 `AccountLiveSession` 同一时刻只能发送一条消息。
- 发送账号从当前 LiveTask 的 `waiting` sessions 中带权随机选择，过滤掉账号不可用、登录失效、页面异常和处于冷却中的账号。
- 选择策略偏向近期发送较少、空闲更久的账号，但必须加入随机扰动，避免严格轮转。
- 只有发送成功才进入账号冷却；发送失败不冷却。
- 发送失败不自动重试，不换账号，不重复发送，只记录失败原因和页面状态。

第一阶段发送成功判定采用操作完成策略：

- 成功填入留言并点击发送按钮，且 CloakBrowser/Playwright 操作未抛异常，则记录 `success`。
- 不验证消息列表、接口响应或平台实际送达。
- 如果页面操作异常、找不到输入框、找不到发送按钮、浏览器崩溃，则记录 `failed`。
- 日志中记录 `success_detection = operation_completed`，后续版本再补真实送达检测。

## 建议目录结构

```text
src/smhelper/
  core/
    config.py
    clock.py
    ids.py
    errors.py
    result.py

  accounts/
    domain/
      platform_account.py
      account_auth_state.py
      account_node_binding.py
      account_quota.py
      account_cooldown.py
      availability_policy.py
    application/
      use_cases/
        update_account_auth.py
        select_accounts_for_live_task.py
      ports/
        account_repository.py
        auth_state_store.py

  workers/
    domain/
      worker_node.py
      worker_capability.py
      worker_heartbeat.py
      browser_capacity.py
      rendezvous_hashing.py
    application/
      use_cases/
        record_heartbeat.py
        select_node_for_account.py
      ports/
        worker_repository.py

  live/
    domain/
      live_task.py
      live_observer_session.py
      live_segment.py
      transcript.py
      candidate_question.py
      account_live_session.py
      dispatch_job.py
      send_attempt.py
      policies/
        account_entry_policy.py
        send_account_policy.py
    application/
      use_cases/
        start_live_task.py
        stop_live_task.py
        discover_stream.py
        process_segment.py
        generate_candidate_question.py
        approve_candidate_question.py
        dispatch_send_job.py
        report_session_status.py
        report_send_result.py
      ports/
        live_task_repository.py
        account_live_session_repository.py
        dispatch_job_repository.py
        transcript_repository.py
        question_generator.py
        speech_to_text.py
        live_stream_discoverer.py
        media_recorder.py
        task_queue.py

  platforms/
    xhs/
      browser/
        login.py
        live_room.py
        stream_discovery.py
        selectors.py
      live_gateway.py

  infrastructure/
    browser/
      cloakbrowser/
        launcher.py
        context_factory.py
        profile_store.py
        storage_state.py
    media/
      ffmpeg/
        runner.py
        segment_recorder.py
        segment_scanner.py
        probe.py
        screenshots.py
        audio.py
    ai/
      litellm_question_generator.py
    asr/
      provider_adapter.py
    task_queue/
      celery/
        app.py
        publisher.py
        tasks.py
    persistence/
      sqlalchemy/
        session.py
        unit_of_work.py
        accounts.py
        workers.py
        live.py

  web/
    app.py
    admin.py
    admin_views/
      accounts.py
      workers.py
      live_tasks.py
      candidates.py
      sessions.py
      dispatch_jobs.py

  cli/
    main.py
    ops.py
```

## 实施路线

第一步：保留现有 POC CLI 作为参考，不继续在其上扩大功能。

第二步：建立正式数据模型和 SQLAlchemy persistence：账号、节点、LiveTask、ObserverSession、LiveSegment、Transcript、CandidateQuestion、AccountLiveSession、DispatchJob、SendAttempt。

第三步：建立 FastAPI + SQLAdmin 后台，先覆盖候选问题查看、编辑、批准发送和基础状态查看。

第四步：实现中心匿名 observer：打开直播间 URL、判断直播状态、提取流地址、维持观察会话。

第五步：实现长期 ffmpeg 固定切片录制，以及以下一个 segment 出现为完成信号的后处理流水线。

第六步：接入 ASR provider adapter 和 LiteLLM question generator，并默认设置 `LITELLM_LOCAL_MODEL_COST_MAP=True`。

第七步：实现远端 Celery worker 浏览器节点：拉取登录态、进入直播间、保持 session、发送留言、回传结果。

第八步：实现全量账号 HRW 分配、15-45 秒抖动入场、带权随机发送账号选择、账号成功发送后冷却。

第九步：实现 session 防重、直播结束收场、close_session 任务和异常 session 重建上限。

## 当前结论

smhelper 第一阶段应采用轻量 DDD + FastAPI/SQLAdmin + Celery/Redis + MySQL + 多远端 Celery worker 的架构。

中心节点负责直播观察、流地址提取、录制、ASR、LLM、后台审核、账号调度和状态持久化；远端操作节点只负责小红书浏览器会话与留言动作。现有 CLI 已经完成技术可行性验证，但后续不作为正式代码继续演进。正式实现应参考其中验证出的操作逻辑，重新落入新的架构边界。
