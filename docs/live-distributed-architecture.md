# smhelper live 分布式执行架构设计

## 架构定位

smhelper 的长期方向是自媒体运营助手。第一阶段聚焦 live CLI MVP：围绕直播间监听、内容分析、候选问题生成、人工确认和授权账号发送问题，先跑通小红书端到端链路。

架构目标不是一开始做成微服务，而是先把领域规则、应用编排、平台适配和基础设施能力分开，让系统可以从单机 CLI 自然演进到中心调度 + 多 Worker 节点执行。

核心判断：适合使用轻量 DDD。这里的 DDD 不是堆目录、堆抽象，而是用领域边界控制复杂度，避免直播调度、账号风控、节点租约、浏览器自动化和数据库访问互相缠在一起。

## 当前 CLI 定位：技术可行性验证

当前项目中已有的 `login-xhs`、`room-console` 等 CLI 能力，只用于验证小红书登录、CloakBrowser 可用性、直播间评论、静音处理、`storage_state.json` 可迁移等技术可行性。

这些 CLI 不是目标生产架构的一部分，后续正式重构时不要求保留代码兼容性，也不应继续沿用现在的文件组织方式。它们的价值是沉淀已经验证过的页面流程、选择器、异常处理经验、登录态保存方式和 CloakBrowser 操作细节。

后续进入正式架构实现时，应参考这些验证逻辑，把平台相关流程迁移到 `platforms/xhs`，把 CloakBrowser 通用能力迁移到 `infrastructure/browser/cloakbrowser`，把 CLI 入口改成调用应用用例，而不是直接承载业务流程和浏览器细节。

## 总体架构

系统拆成五类边界：

- `core`：极小的通用内核，只放纯代码能力，例如配置对象、时钟、ID、基础异常、结果类型和通用类型定义。
- `accounts`：账号领域，负责平台账号、登录态、账号可用性、冷却、配额和账号与 Worker 的绑定规则。
- `workers`：执行节点领域，负责节点注册、心跳、能力、容量、健康状态和租约。
- `live`：直播助手领域，负责直播任务、直播间状态、录制片段、转写、候选问题、人工确认、发送计划和发送日志。
- `platforms` 与 `infrastructure`：前者放具体平台语义，例如小红书页面流程和选择器；后者放通用技术适配，例如 CloakBrowser、ffmpeg、Celery、SQLAlchemy。

中心节点负责监听直播任务状态、生成计划、调度 Worker；Worker 节点负责拿到任务后使用本机账号登录态和本机网络环境执行浏览器动作。

## 领域边界

`accounts` 是独立领域，因为账号不是直播助手的附属对象。账号以后会被不同平台、不同功能复用，例如直播间提问、评论区互动、私信、内容发布或数据采集。

`workers` 也是独立领域，因为节点不是单纯的技术配置。它承载容量、健康状态、平台能力、网络环境、账号绑定、租约和任务分配规则。后续分布式调度能否稳定，主要依赖 Worker 模型是否清晰。

`live` 是当前第一阶段的核心业务领域，依赖账号和 Worker 的能力，但不拥有账号和 Worker 的生命周期。

## 技术适配层边界

CloakBrowser、ffmpeg、Celery、SQLAlchemy 不属于领域，也不应该放进 `core`。它们是基础设施适配。

CloakBrowser 应抽象为通用浏览器能力：启动浏览器、创建上下文、加载登录态、保存登录态、打开页面、执行可观测动作。它不应该知道小红书页面上的登录按钮、验证码输入框或直播间留言框。

ffmpeg 应抽象为通用媒体处理能力：探测流、分段录制、截取首尾帧、提取音频、记录命令执行结果和错误原因。它不应该知道直播任务的业务状态机。

Celery 应放在任务队列适配层，用来实现应用层定义的任务发布、消费和重试接口。第一版可以先用数据库轮询完成中心调度到 Worker 的任务分发，等任务量和可靠性需求明确后再接 Celery。

SQLAlchemy 应作为 persistence 适配层。文件命名不要使用 `mysql_*.py` 这类数据库厂商前缀；MySQL、PostgreSQL 的差异优先通过 DSN、迁移和少量 dialect 适配处理。

## 设计原则

- 领域规则不依赖浏览器、数据库、队列、网络请求或具体平台页面。
- 应用层负责编排用例，例如创建直播任务、调度账号、提交人工确认、发送问题、停止任务。
- 平台层表达具体平台的页面语义，例如小红书如何判断登录、如何打开登录弹窗、如何发直播间留言。
- 基础设施层封装具体工具，例如 CloakBrowser、ffmpeg、Celery、SQLAlchemy。
- 不提前创建空目录和空抽象；目录跟随真实功能增长。
- 不把入口、业务规则、数据访问和外部调用堆进一个 CLI 文件。

## 文件拆分原则

不要使用大而全的 `models.py`、`services.py`、`ports.py`、`repositories.py`。这些文件短期方便，长期会变成新版本的上帝文件。

建议按稳定业务概念拆文件：

- 一个文件表达一个核心概念或一组高度内聚的小概念。
- 同一领域内的实体、值对象、领域服务、仓储接口可以分目录，但不要为了“每个类一个文件”机械拆分。
- 应用层按用例拆分，例如 `start_live_task.py`、`confirm_question.py`、`assign_worker.py`。
- 基础设施实现按被适配的端口拆分，例如 `accounts.py`、`workers.py`、`live.py`，不要按数据库厂商拆成 `mysql_accounts.py`。

## 建议目录结构

```text
src/smhelper/
  __init__.py

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
        register_account.py
        update_account_auth.py
        select_account_for_task.py
      ports/
        account_repository.py
        auth_state_store.py
    infrastructure/
      # 仅放账号领域自己的基础设施实现；通用技术能力放顶层 infrastructure

  workers/
    domain/
      worker_node.py
      worker_capability.py
      worker_lease.py
      worker_heartbeat.py
      capacity_policy.py
    application/
      use_cases/
        register_worker.py
        record_heartbeat.py
        acquire_worker_lease.py
        release_worker_lease.py
      ports/
        worker_repository.py
        lease_repository.py

  live/
    domain/
      live_task.py
      live_room.py
      live_segment.py
      transcript.py
      candidate_question.py
      dispatch_job.py
      send_attempt.py
      policies/
        dispatch_policy.py
        question_policy.py
    application/
      use_cases/
        start_live_task.py
        stop_live_task.py
        poll_live_status.py
        generate_candidate_question.py
        confirm_question.py
        dispatch_question.py
        report_send_result.py
      ports/
        live_task_repository.py
        dispatch_job_repository.py
        transcript_repository.py
        question_generator.py
        live_platform_gateway.py
        media_recorder.py
        task_queue.py

  platforms/
    xhs/
      browser/
        login.py
        live_room.py
        selectors.py
      live_gateway.py
      account_auth.py

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
        recorder.py
        probe.py
        screenshots.py
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

  cli/
    main.py
    live.py
    accounts.py
    workers.py

  web/
    api/
      app.py
      routes/
        live_tasks.py
        accounts.py
        workers.py
    schemas/
      live_tasks.py
      accounts.py
      workers.py
```

后续如果前端独立建设，建议放在仓库顶层：

```text
frontend/
  package.json
  src/
```

## Web 与 CLI 入口层位置

CLI 和 Web 都是入口层，不属于任何一个领域。它们只负责参数解析、权限校验、输入输出和调用应用用例。

CLI 第一阶段用于跑通 MVP 闭环：任务启动、状态查看、日志查看、停止、人工确认发送。Web 管理后台后续放在 `src/smhelper/web`，不作为第一阶段闭环验收前置。

无论 CLI 还是 Web，都不应该直接调用 SQLAlchemy、CloakBrowser、ffmpeg 或具体平台选择器。入口层只调用 application use case。

## 多平台扩展边界

当前第一阶段只做小红书，但结构需要给未来平台留下清晰余地。

平台差异放在 `platforms/<platform>` 下，例如未来增加抖音时新增 `platforms/douyin`，而不是修改 `live` 领域规则。直播任务、候选问题、人工确认、账号调度、Worker 租约这些规则应该尽量保持平台无关。

平台适配层负责回答这些问题：

- 如何判断账号是否登录。
- 如何完成登录或恢复登录态。
- 如何判断直播是否进行中。
- 如何判断是否静音并取消静音。
- 如何发送直播间留言。
- 如何提取平台可见的直播流信息。

`platforms/xhs` 可以依赖 `infrastructure/browser/cloakbrowser`，但 `infrastructure/browser/cloakbrowser` 不能反向依赖 `platforms/xhs`。

## 核心领域对象

账号领域：

- `PlatformAccount`：某个平台上的自有授权账号。
- `AccountAuthState`：登录态元数据、过期时间、最近验证时间、存储位置。
- `AccountNodeBinding`：账号和 Worker 节点的绑定关系。
- `AccountQuota`：账号发送频率、每日上限、平台限制。
- `AccountCooldown`：账号冷却和临时不可用原因。

Worker 领域：

- `WorkerNode`：可执行浏览器动作的节点。
- `WorkerCapability`：节点支持的平台、浏览器能力、ffmpeg 能力、并发容量。
- `WorkerHeartbeat`：节点最近心跳和健康状态。
- `WorkerLease`：中心调度分配给节点的短期任务租约。

Live 领域：

- `LiveTask`：一次直播助手任务。
- `LiveRoom`：直播间地址、平台、当前状态。
- `LiveSegment`：录制分片和首尾帧、音频产物。
- `Transcript`：ASR 转写结果。
- `CandidateQuestion`：LLM 生成的候选问题。
- `DispatchJob`：一次待发送问题的调度任务。
- `SendAttempt`：一次实际发送尝试和结果。

## DispatchJob 与 WorkerLease 的边界

`DispatchJob` 属于 live 领域，表示业务上有一个问题需要被某个账号发送到某个直播间。

`WorkerLease` 属于 workers 领域，表示某个 Worker 在一段时间内获得执行某个任务的资格，避免多个节点重复执行同一任务。

二者不要合并。DispatchJob 关心业务结果，WorkerLease 关心分布式执行安全。

## 工作原理

第一阶段的主链路：

1. 运营人员通过 CLI 创建直播任务，填写平台、小红书直播间 URL、直播流地址、产品资料和任务上下文。
2. 中心节点使用 ffmpeg 分段录制直播流，保存视频片段、首尾帧和音频。
3. ASR 对音频转写，系统保存近期转写文本。
4. LLM 根据产品资料、近期转写文本和任务上下文生成候选问题；首尾帧第一阶段只保存，不进入 LLM。
5. 运营人员通过 CLI 查看候选问题并人工确认。
6. 中心节点根据账号可用性、平台、冷却、配额、绑定 Worker 和节点容量创建 DispatchJob。
7. Worker 获取任务租约，使用本机 CloakBrowser 和账号登录态进入直播间。
8. Worker 判断直播是否仍在进行、是否静音、必要时取消静音，然后发送留言。
9. Worker 上报发送结果、截图或错误原因，中心节点更新任务状态和日志。

## DispatchJob 状态机

```text
pending -> leased -> running -> succeeded
                    -> failed_retryable -> pending
                    -> failed_final
                    -> canceled
leased -> expired -> pending
```

状态含义：

- `pending`：等待调度。
- `leased`：已被某个 Worker 获取租约，但尚未开始或尚未确认开始。
- `running`：Worker 正在执行浏览器动作。
- `succeeded`：发送成功。
- `failed_retryable`：可重试失败，例如节点临时掉线、页面加载超时。
- `failed_final`：不可重试失败，例如直播已结束、账号不可用、平台拒绝发送。
- `canceled`：任务被人工或系统取消。
- `expired`：租约超时，任务回到待调度。

## 第一版通信方案

第一版建议使用中心数据库 + Worker 轮询，不急着引入复杂消息系统。

中心节点写入 DispatchJob，Worker 定期拉取自己可执行的平台和账号绑定范围内的任务。Worker 获取任务时写入 WorkerLease，并通过租约过期时间避免任务永久卡住。

当单机轮询和数据库锁无法满足吞吐或可靠性要求时，再把任务发布、消费、重试迁移到 Celery。Celery 只作为 `task_queue` 端口的一个实现，不进入领域模型。

## 安全与风控边界

- 登录态属于账号认证资产，必须加密保存，不能明文散落在 Worker 本地。
- 中心节点可以保存和下发 `storage_state.json`，但应记录版本、平台、账号、有效期和最近验证时间。
- Worker 执行时只能获取自己被授权执行的账号登录态。
- 账号与节点应支持绑定策略，避免所有账号集中在同一机器、同一 IP 或同一运行环境。
- 浏览器自动化的页面选择器、弹窗处理和操作节奏属于平台适配层，不应混入业务规则。

## 实施路线

第一步：保留现有 POC CLI 作为参考，不继续在其上扩大功能；新增正式分层时从 `live`、`accounts`、`workers` 的最小真实用例开始。

第二步：迁移已验证的小红书页面逻辑到 `platforms/xhs`，迁移 CloakBrowser 通用能力到 `infrastructure/browser/cloakbrowser`。

第三步：建立账号登录态保存、读取、验证和下发流程，验证 `storage_state.json` 从中心到 Worker 的分发闭环。

第四步：建立中心调度和 Worker 轮询执行模型，先实现 DispatchJob、WorkerLease、SendAttempt 的最小闭环。

第五步：补齐 ffmpeg 录制、首尾帧、音频提取、ASR、LLM 候选问题和人工确认流程。

第六步：当 CLI MVP 稳定后，再建设 Web 管理后台，并复用同一批 application use case。

## 当前结论

smhelper 适合采用轻量 DDD + 分层端口适配架构。

账号、Worker 和 live 应作为独立领域协作；CloakBrowser、ffmpeg、Celery、SQLAlchemy 应作为基础设施适配；小红书页面流程应进入 `platforms/xhs`；CLI 和 Web 只是入口层。

现有 CLI 已经完成技术可行性验证，但后续不作为正式代码继续演进。正式实现应参考其中验证出的操作逻辑，重新落入新的架构边界。
