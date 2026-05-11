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
```

浏览器访问 `http://localhost:8080/health` 查看集群状态。

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
│   ├── tools/      #   Master 客户端
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
│   └── Dockerfile
├── proto/          # 信封协议 JSON Schema
├── config/         # 配置模板
├── scripts/        # 开发脚本
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
make test          # 全部三层
make test-worker   # Go 测试（70+ 项）
make test-master   # TypeScript 测试（75+ 项）
make test-brain    # Python 测试（60+ 项）
```

## 架构

- **Brain**: 基于 LangGraph 的 AI 编排引擎。分析上下文 → 规划工具调用 → 执行 → 反思结果。支持 Ollama 和 OpenAI 双 LLM 提供商。
- **Master**: 集中式任务调度与安全管控。WebSocket 实时通信，REST API 接收指令，优先级队列调度，审批流控制，结构化审计。
- **Worker**: 安全沙箱执行环境。支持文件系统、进程管理、系统服务、网络探测等运维操作。心跳上报、速率限制、路径安全检查。

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 集群健康检查 |
| `/metrics` | GET | Prometheus 指标 |
| `/api/v1/execute` | POST | 执行指令（需 Bearer token） |
| `/api/v1/approve/:id` | POST | 批准高风险操作 |
| `/api/v1/reject/:id` | POST | 拒绝高风险操作 |

## 安全

- 集群令牌认证（所有 WebSocket 和 REST 请求）
- 操作审批流（高风险指令需人工确认）
- 参数过滤（shell 注入、路径遍历、命令链检测）
- 速率限制（每 Brain 实例 120 req/min）
- 审计日志（认证失败、限流命中、审批事件全记录）
- TLS 可选加密

## License

MIT
