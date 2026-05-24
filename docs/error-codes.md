# gAIOps 错误码编目

所有跨层错误码统一注册于此。新增或变更需更新此文件并同步三层的 `ErrorClassifier` / `_is_retryable()`。

## 错误码格式

`<模块前缀>_<错误名称>`，全大写，下划线分隔。

| 前缀 | 模块 |
|------|------|
| `TOOL_*` | Worker 工具执行 |
| `WORKER_*` | Worker 通用 |
| `MASTER_*` | Master |
| `BRAIN_*` | Brain |
| `PARAM_*` | 参数消毒（Brain ParamFilter） |
| `PROTO_*` | 协议层 |
| `AUTH_*` | 认证 |
| `EXEC_*` | 执行环境 |
| `DEPLOY_*` | 动态工具部署 |
| `CODE_*` | 工具代码生成（Brain） |
| `MEM_*` | 记忆模块 |

---

## Worker 工具错误码

### TOOL_PANIC
- **含义**: 工具执行时发生 panic
- **模块**: Worker / executor
- **处理策略**: `human` — 代码缺陷，不重试，需人工排查
- **触发条件**: 工具代码中未捕获的 panic
- **Payload**: `error.raw` 包含 panic 信息和堆栈

### EXECUTION_TIMEOUT
- **含义**: 工具执行超过声明超时时间
- **模块**: Worker / executor (sandbox)
- **处理策略**: `retry` — 可能临时负载高，可重试
- **触发条件**: `context.WithTimeout` 到期，工具未返回
- **建议配置**: Master tracker 的超时应略大于 Worker 工具超时

### COMMAND_NOT_ALLOWED
- **含义**: `exec.run` 的命令不在白名单中
- **模块**: Worker / tools/exec
- **处理策略**: `replan` — Brain 应调整参数
- **触发条件**: 命令路径不在 `worker.yaml` 的 `tools.exec.allowed_commands` 中

### INVALID_ARGS
- **含义**: 命令参数包含 shell 元字符
- **模块**: Worker / tools/exec
- **处理策略**: `replan` — 参数需要消毒
- **触发条件**: 参数匹配 `[;&|\`$(){}]` 模式

### PATH_NOT_ALLOWED
- **含义**: 文件路径不在允许目录中
- **模块**: Worker / safety/path
- **处理策略**: `replan` — 路径需要调整
- **触发条件**: `filepath.Clean` + `filepath.Abs` 后不在 `allowed_log_paths` / `allowed_disk_paths` 中

### OUTPUT_TOO_LARGE
- **含义**: 工具输出超过 1MB 被截断
- **模块**: Worker / safety/limiter
- **处理策略**: 非错误 — 数据截断但执行成功，`truncated=true`，Brain 可缩小查询范围
- **触发条件**: data > 1MB 或 error.raw > 100KB

### SERVICE_NOT_FOUND
- **含义**: 目标服务不存在
- **模块**: Worker / tools/service
- **处理策略**: `replan` — Brain 应检查服务名

### SERVICE_ALREADY_RUNNING
- **含义**: 服务已在运行
- **模块**: Worker / tools/service
- **处理策略**: `replan` — 无需再次启动

### PING_FAILED
- **含义**: ICMP/TCP ping 探测失败
- **模块**: Worker / tools/ping
- **处理策略**: `replan` — Brain 可换目标

### PROCESS_NOT_FOUND
- **含义**: 目标进程不存在
- **模块**: Worker / tools/process
- **处理策略**: `replan` — Brain 应检查进程名

### DISK_READ_ERROR
- **含义**: 磁盘信息读取失败
- **模块**: Worker / tools/disk
- **处理策略**: `human` — 可能是系统级问题

---

## Worker 通用错误码

### WORKER_OFFLINE
- **含义**: Worker 已从 Master 断开
- **模块**: Master / connection
- **处理策略**: `retry` — 等待重连或切其他 Worker
- **触发条件**: Master 心跳超时或 Worker 主动断开

### WORKER_ID_CONFLICT
- **含义**: 同一 `worker_id` 已有连接在线
- **模块**: Master / ws-server
- **处理策略**: `human` — 管理员需确保 worker_id 唯一
- **触发条件**: 新连接 `worker_id` 与已注册的重复

### WORKER_OVERLOAD
- **含义**: Worker 当前并发数已达上限
- **模块**: Worker / executor
- **处理策略**: `retry` — 等 Worker 空闲后重试
- **触发条件**: `semaphore` 满，无法获取执行许可

### SHUTTING_DOWN
- **含义**: Worker 正在优雅关闭，不接受新任务
- **模块**: Worker / cmd/main
- **处理策略**: `retry` — Worker 重启后重新注册

---

## Master 错误码

### MASTER_OVERLOAD
- **含义**: Master tracker 已满，拒绝新请求
- **模块**: Master / orchestrator/tracker
- **处理策略**: `retry` — 等 pending 排空后重试
- **触发条件**: `pending.size >= MAX_PENDING (10000)`

### NO_AVAILABLE_WORKER
- **含义**: 没有在线 Worker 能执行该 action
- **模块**: Master / orchestrator/router
- **处理策略**: `retry` — 等待 Worker 上线；若长时间无 Worker 则升级 human
- **触发条件**: 路由时无 Worker 具备该 capability 或所有 Worker 满载

### TTL_EXPIRED
- **含义**: 消息 TTL 已过期被丢弃
- **模块**: Master / orchestrator/tracker
- **处理策略**: `retry` — 重新发送
- **触发条件**: `sentAt + ttl_seconds * 1000 < now`

### APPROVAL_REJECTED
- **含义**: 高危指令审批被拒绝
- **模块**: Master / security/approver
- **处理策略**: `human` — 已被人为拒绝，不再重试

### APPROVAL_TIMEOUT
- **含义**: 高危指令审批超时未响应
- **模块**: Master / security/approver
- **处理策略**: `replan` — Brain 可尝试其他方案

### BROADCAST_PARTIAL_FAILURE
- **含义**: 广播指令部分 Worker 未响应
- **模块**: Master / orchestrator/router
- **处理策略**: 非错误 — 部分成功可用，Brain 自行分析结果集

---

## Brain 错误码

### BRAIN_LLM_UNAVAILABLE
- **含义**: LLM 服务（Ollama）不可达或超时
- **模块**: Brain / llm
- **处理策略**: `human` — 基础设施故障，需管理员介入
- **触发条件**: Ollama API 连接失败或连续超时

### BRAIN_STREAM_ERROR
- **含义**: LLM 流式响应异常（断连、格式错误）
- **模块**: Brain / llm/stream_handler
- **处理策略**: `retry` — 重试一次流式请求

### BRAIN_CYCLE_DETECTED
- **含义**: LLM 连续多次以相同方式失败，检测到自循环
- **模块**: Brain / agents/reflector
- **处理策略**: `human` — 熔断触发，自动升级人工
- **触发条件**: 同一 action + 同一 error_code 连续失败 3 次，或总重试超 5 次

### BRAIN_CONTEXT_OVERFLOW
- **含义**: LLM 上下文窗口超限
- **模块**: Brain / llm/context_window
- **处理策略**: `human` — 摘要压缩失败或步骤太长

---

## 参数消毒错误码（Brain → Master 前拦截）

### PARAM_SANITIZED
- **含义**: 指令参数被 ParamFilter 拦截，未发送到 Master
- **模块**: Brain / safety/param_filter
- **处理策略**: `replan` — Brain 需重新规划调整参数
- **触发条件**: 参数含 shell 元字符、路径遍历、敏感路径、命令链

### PARAM_TOO_LONG
- **含义**: 参数长度超过上限被截断
- **模块**: Brain / safety/param_filter
- **处理策略**: 非错误 — 截断后继续执行，但 Brain 应收到截断标记

### PARAM_MISSING
- **含义**: LLM 输出缺少必填参数
- **模块**: Brain / llm/sanitizer
- **处理策略**: `replan` — LLM 输出不完整，重新生成

### UNKNOWN_TOOL
- **含义**: LLM 生成了不存在的 action 名称
- **模块**: Brain / llm/sanitizer
- **处理策略**: `replan` — LLM 幻觉，需重新生成

---

## 协议层错误码

### PROTO_VERSION_MISMATCH
- **含义**: 双方协议版本不兼容
- **模块**: Master / protocol/version
- **处理策略**: `human` — 需要版本协调升级

### MISSING_TRACE_ID
- **含义**: 请求缺少 trace_id
- **模块**: Master / server/brain-api
- **处理策略**: `replan` — Brain 需修复代码

### MISSING_ACTION
- **含义**: 请求缺少 action 字段
- **模块**: Master / server/brain-api
- **处理策略**: `replan` — Brain 需修复代码

### INVALID_ENVELOPE
- **含义**: 信封格式校验失败（字段类型错误、缺少必填字段）
- **模块**: Master / protocol/envelope
- **处理策略**: `replan` — 发送方需修正格式

---

## 认证错误码

### AUTH_FAILED
- **含义**: cluster token 校验失败
- **模块**: Master / server (ws-server / brain-api)
- **处理策略**: `human` — 密钥不匹配，需管理员介入
- **触发条件**: token 无效或已过期

### AUTH_TOKEN_MISSING
- **含义**: 连接未携带 token
- **模块**: Master / server
- **处理策略**: `human` — 配置缺失

---

## 动态工具错误码

### TOOL_DEPLOY_FAILED
- **含义**: 工具部署到 Worker 失败（编译/语法检查未通过）
- **模块**: Worker / dynamic/compiler
- **处理策略**: `replan` — Brain 调整代码后重试

### TOOL_COMPILE_ERROR
- **含义**: 工具代码语法检查失败
- **模块**: Worker / dynamic/compiler
- **处理策略**: `replan` — Brain 修复代码后重试

### TOOL_SANDBOX_VIOLATION
- **含义**: 工具执行时触发了沙箱限制
- **模块**: Worker / dynamic/sandbox
- **处理策略**: `human` — 代码可能包含恶意行为，需人工审查

### TOOL_MEMORY_LIMIT
- **含义**: 动态工具超出内存限制
- **模块**: Worker / dynamic/sandbox
- **处理策略**: `replan` — Brain 优化代码

### TOOL_RUNTIME_UNAVAILABLE
- **含义**: Worker 没有所需的