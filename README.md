# gAIOps — 分布式 AI 运维平台

[![CI](https://img.shields.io/github/actions/workflow/status/Ryan-0625/g-AIOps/ci.yml?branch=main&label=CI)](https://github.com/Ryan-0625/g-AIOps/actions)
[![Go](https://img.shields.io/badge/Go-1.25-00ADD8?logo=go)](worker/)
[![Node](https://img.shields.io/badge/Node-20-339933?logo=nodedotjs)](master/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)](brain/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

三层分布式 AI Ops 系统：Brain（Python/LangGraph）推理决策，Master（TypeScript/Node.js）调度安全，Worker（Go）沙箱执行。

```
┌─────────┐    REST    ┌──────────┐   WebSocket  ┌──────────┐
│  Brain  │──────────▶│  Master  │◄────────────▶│  Worker  │
│ (Python)│◀──────────│ (Node.js)│─────────────▶│   (Go)   │
│LangGraph│  Webhook   │  Express │  Envelope v1 │ Sandbox  │
└─────────┘            └──────────┘              └──────────┘
```

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/Ryan-0625/g-AIOps.git
cd g-AIOps

# 启动所有服务（需要先安装 Docker Compose）
export CLUSTER_TOKEN=my-secret-token
docker compose up -d

# 验证
curl http://localhost:8080/health

# 使用 CLI
python cli/gaiops health --token my-secret-token
python cli/gaiops worker list --token my-secret-token
python cli/gaiops execute ping.icmp target=localhost --token my-secret-token
```

浏览器访问 `http://localhost:8080/health` 查看集群状态。

## CLI — 命令行工具

`cli/gaiops` 是一个纯 Python 3 CLI，零外部依赖（仅用标准库），通过 REST API 与 Master 交互。

```bash
# 认证方式（任选其一）
python cli/gaiops --token my-token <command>           # 显式传 token
export CLUSTER_TOKEN=my-token && python cli/gaiops <command>  # 环境变量
python cli/gaiops config init --token my-token         # 写入配置文件 ~/.gaiops/config

# 全局选项
python cli/gaiops --base-url http://localhost:8080 --json <command>

# 命令列表
gaiops health                       # 集群健康检查
gaiops worker list                  # 列出已连接的 Worker
gaiops execute <action> [key=val]   # 执行工具（如 ping.icmp target=8.8.8.8 count=3）
gaiops result <msg_id>              # 轮询工具执行结果
gaiops approve <id>                 # 批准高风险操作
gaiops reject <id>                  # 拒绝高风险操作
gaiops trace list                   # 列出最近的追踪记录
gaiops trace get <trace_id>         # 查看追踪详情
gaiops config init                  # 创建配置文件
gaiops config show                  # 查看当前配置
```

示例：

```bash
# 执行并获取结果
CLUSTER_TOKEN=my-token python cli/gaiops execute ping.icmp target=localhost count=1
# → msg_id: abc-123, status: pending
# → Poll result: gaiops result abc-123

CLUSTER_TOKEN=my-token python cli/gaiops result abc-123
# → 完整 response envelope，含 Worker 执行结果

# JSON 输出（脚本友好）
CLUSTER_TOKEN=my-token python cli/gaiops --json health

# 指定目标 Worker 执行
CLUSTER_TOKEN=my-token python cli/gaiops execute service.status name=nginx target_worker_id=worker-1
```

## 配置

| 变量 | 默认值 | 层 | 说明 |
|---|---|---|---|
| `CLUSTER_TOKEN` | `dev-token-change` | ALL | 集群共享认证令牌 |
| `LOG_LEVEL` | `info` | ALL | 日志级别 (debug/info/warn/error) |
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Brain | Ollama 服务地址 |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Brain | LLM 模型名称 |
| `LLM_PROVIDER` | `ollama` | Brain | LLM 提供商 (ollama/openai) |
| `OPENAI_API_KEY` | — | Brain | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Brain | OpenAI API 地址 |
| `MASTER_API_URL` | `http://master:8080` | Brain | Master API 地址 |
| `MASTER_PORT` | `8080` | Master | HTTP/WS 监听端口 |
| `TLS_CERT_PATH` | — | Master | TLS 证书路径（可选） |
| `TLS_KEY_PATH` | — | Master | TLS 密钥路径（可选） |
| `AUDIT_LOG_PATH` | — | Master | 审计日志文件路径（可选） |
| `AUDIT_ENABLED` | `true` | Master | 审计开关 |
| `WORKER_ID` | `worker-{hostname}` | Worker | Worker 标识 |
| `MASTER_WS_URL` | `ws://localhost:8080/ws` | Worker | Master WebSocket 地址 |
| `HEARTBEAT_INTERVAL` | `15` | Worker | 心跳间隔（秒） |

完整配置参考：[Master](config/master.yaml.example)、[Worker](config/worker.yaml.example)、[Brain](config/brain.yaml.example)。

## 项目结构

```
gAIOps/
├── brain/          # 决策引擎 (Python/LangGraph)
│   ├── agents/     #   分析、规划、反射节点
│   ├── core/       #   图引擎、状态定义
│   ├── llm/        #   Ollama/OpenAI 适配器
│   ├── tools/      #   Master 客户端、工具注册表
│   └── safety/     #   参数过滤、错误分类
├── master/         # 调度安全中心 (TypeScript/Node.js)
│   ├── src/
│   │   ├── server/ #   REST + WebSocket 服务
│   │   ├── security/#  认证、审批、审计、拦截
│   │   ├── orchestrator/ # 路由、队列、追踪
│   │   ├── store/  #   注册表、指标、会话
│   │   └── protocol/#  信封协议
│   └── Dockerfile
├── worker/         # 远程执行者 (Go)
│   ├── cmd/worker/ #   入口
│   ├── internal/   #   连接、执行器、安全、工具
│   │   └── tools/  #   ping, disk, dns, http, file, network, container, service, process, exec, log + 动态工具
│   └── Dockerfile
├── cli/            # 命令行工具 (Python, 零外部依赖)
├── proto/          # 信封协议 JSON Schema
├── config/         # 配置模板
├── scripts/        # 开发脚本
├── e2e/            # 端到端测试 (pytest, 68+ 测试)
└── docs/           # 文档
```

## 开发

```bash
# 安装依赖
make init-worker  # Go 模块
make init-master  # npm install
make init-brain   # pip install

# 本地运行（三层分别在终端）
make run-worker   # Go Worker
make run-master   # Node.js Master
make run-brain    # Python Brain

# 或使用 Docker
docker compose up -d

# Linux/macOS 开发环境一键启动
bash scripts/dev-up.sh

# Windows 开发环境一键启动
powershell -File scripts/dev-up.ps1
```

## 测试

```bash
make test          # 全部三层（含 E2E）
make test-worker   # Go 测试（70+ 项）
make test-master   # TypeScript 测试（75+ 项）
make test-brain    # Python 测试（80+ 项）
make test-e2e      # E2E 测试（68+ 项）
```

## 架构

- **Brain**: 基于 LangGraph 的 AI 编排引擎。分析上下文 → 规划工具调用 → 执行 → 反思结果。支持 Ollama 和 OpenAI 双 LLM 提供商。
- **Master**: 集中式任务调度与安全管控。WebSocket 实时通信，REST API 接收指令，优先级队列调度，审批流控制，结构化审计。
- **Worker**: 安全沙箱执行环境。支持文件系统读写（file.read/write）、进程管理（process.list/kill）、系统服务（service.status/restart/stop）、网络探测（ping.icmp, dns.lookup, http.get/post, network.connections）、磁盘（disk.usage）、系统信息（system.info）、容器（container.list）、日志（log.tail）、命令执行（exec.run）以及运行时动态工具创建（tool.create/delete）。心跳上报、速率限制、路径安全检查。

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 集群健康检查 |
| `/metrics` | GET | Prometheus 指标 |
| `/api/v1/execute` | POST | 执行指令（需 Bearer token） |
| `/api/v1/result/:msg_id` | GET | 轮询执行结果 |
| `/api/v1/workers` | GET | 列出在线 Worker 及能力 |
| `/api/v1/approve/:id` | POST | 批准高风险操作 |
| `/api/v1/reject/:id` | POST | 拒绝高风险操作 |
| `/api/v1/traces` | GET | 追踪记录列表 |
| `/api/v1/trace/:trace_id` | GET | 追踪详情 |

## 部署

### 快速部署（Docker Compose）

```bash
# 1. 设置集群令牌并启动
export CLUSTER_TOKEN=my-secret-token
docker compose up -d

# 2. 验证所有服务就绪
curl http://localhost:8080/health
# → {"status":"ok","workers":{"online":1}}

# 3. 检查 Worker 连接
python cli/gaiops worker list --token my-secret-token
```

### 部署新 Worker 并绑定到 Master

Worker 可在任意能连接到 Master 的服务器上独立部署：

```bash
# 在目标服务器上创建 worker.yaml
cat > /etc/gaiops/worker.yaml << 'EOF'
worker_id: "worker-dc-01"
master_url: "ws://<master-public-ip>:8080/ws"
cluster_token: "my-secret-token"
heartbeat_interval: 15
reconnect:
  base_delay: 1
  max_delay: 60
max_concurrent_tools: 10
logging:
  level: "info"
  format: "json"
tools:
  exec:
    allowed_commands:
      - "/usr/bin/systemctl"
      - "/bin/df"
      - "/bin/ls"
      - "/usr/bin/tail"
EOF

# 启动 Worker（二进制或 Docker）
# 二进制方式：
./gaiops-worker --config /etc/gaiops/worker.yaml

# Docker 方式：
docker run -d \
  --name gaiops-worker \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v /var/log:/var/log:ro \
  -v /etc/gaiops/worker.yaml:/etc/gaiops/worker.yaml:ro \
  --network host \
  gaiops-worker

# 验证注册
python cli/gaiops worker list --token my-secret-token
# → 应看到新 Worker 出现在列表中
```

环境变量可覆盖 YAML 配置（优先级更高）：

```bash
CLUSTER_TOKEN=my-token WORKER_ID=worker-dc-02 MASTER_URL=ws://master:8080/ws ./gaiops-worker
```

### Master 独立部署

```bash
# Docker 方式（推荐）
docker run -d \
  --name gaiops-master \
  -p 8080:8080 \
  -e CLUSTER_TOKEN=my-secret-token \
  -e LOG_LEVEL=info \
  gaiops-master

# 或从源码运行
cd master && npm install && CLUSTER_TOKEN=my-token npm start
```

### Brain 独立部署

```bash
# Docker 方式
docker run -d \
  --name gaiops-brain \
  -e CLUSTER_TOKEN=my-secret-token \
  -e MASTER_API_URL=http://<master-ip>:8080 \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_URL=http://<ollama-ip>:11434 \
  gaiops-brain

# 或从源码运行
cd brain && pip install -r requirements.txt && \
  CLUSTER_TOKEN=my-token MASTER_API_URL=http://localhost:8080 python main.py
```

### 生产环境注意事项

| 关注点 | 建议 |
|--------|------|
| **高可用** | Master 无状态可水平扩展，前端加负载均衡；Worker 天然分布 |
| **认证** | `CLUSTER_TOKEN` 生产环境使用强随机串（`openssl rand -hex 32`） |
| **TLS** | 设置 `TLS_CERT_PATH` 和 `TLS_KEY_PATH` 启用 HTTPS/WSS |
| **审计** | 默认启用，审计日志位于 `/var/log/gaiops/audit.log` |
| **资源隔离** | Worker 通过 `tools.exec.allowed_commands` 限制可执行命令 |
| **沙箱增强** | 建议生产环境叠加 Docker seccomp / AppArmor 配置文件 |
| **日志** | 所有组件输出 JSON 结构化日志，可对接 ELK/Loki |
| **监控** | Master 暴露 `/metrics`（Prometheus），Worker 暴露 `/health`（:9090） |
| **限流** | Master 默认 120 req/min 每 Brain 实例，Worker 默认 5 并发工具 |
| **审批** | 高风险操作（exec.run, service.restart 等）需人工审批 |
| **Brain 降级** | LLM 不可用时自动跳过推理，仅返回已有结果（只读模式） |
| **Brain 限流** | 内置滑动窗口限流器，防止打满 Master 配额 |
| **动态工具** | Worker 支持运行时 `tool.create`/`tool.delete`（危险操作，需审批） |
| **网络** | Worker 的 http.get/http.post 默认禁止内网 IP，防止 SSRF |
| **更新** | 先升级 Master → Worker 自动重连 → 最后升级 Brain

## 安全

- 集群令牌认证（所有 WebSocket 和 REST 请求）
- 操作审批流（高风险指令需人工确认）
- 参数过滤（shell 注入、路径遍历、命令链检测）
- 速率限制（每 Brain 实例 120 req/min）
- 审计日志（认证失败、限流命中、审批事件全记录）
- TLS 可选加密

## License

MIT
