# gAIOps v2.0 Architecture Overview

## Core Architecture Principle

**Worker runs directly on target hosts (Agent mode). No Docker sandbox for Worker.**
Master and Brain can run anywhere (Docker, bare metal, k8s).

```
                        ┌─────────────────────────────────────┐
                        │         Access Channels             │
                        │  CLI │ Web API │ Webhook │ (Future) │
                        └────────────────┬────────────────────┘
                                         │
                        ┌────────────────▼──────────────────┐
                        │       Master (Node.js)            │
                        │  ┌──────┬──────┬──────┬────────┐ │
                        │  │Router│Tracker│ Queue│ Auditer│ │
                        │  ├──────┴──────┴──────┴────────┤ │
                        │  │ Approver │ Interceptor       │ │
                        │  ├─────────────────────────────┤ │
                        │  │ Inspection Engine            │ │
                        │  │ Scheduler → Probe → Alert   │ │
                        │  └──────────────┬──────────────┘ │
                        └─────────────────┼────────────────┘
                                          │ WebSocket
              ┌───────────────────────────┼───────────────────────────┐
              │                           │                           │
     ┌────────▼────────┐      ┌──────────▼─────────┐     ┌──────────▼─────────┐
     │  Brain (Python)  │      │  Worker Agent (Go)  │     │  Worker Agent (Go)  │
     │                  │      │  [Host-A]           │     │  [Host-B]           │
     │  ┌────────────┐  │      │                     │     │                     │
     │  │ Agent Loop  │  │      │  ┌───────────────┐  │     │  ┌───────────────┐  │
     │  │ (LangGraph) │  │      │  │ Built-in Tools│  │     │  │ Built-in Tools│  │
     │  ├────────────┤  │      │  │ - exec.run     │  │     │  │ - exec.run     │  │
     │  │ Knowledge   │  │      │  │ - ping.icmp   │  │     │  │ - ping.icmp   │  │
     │  │ Engine      │  │      │  │ - port.check  │  │     │  │ - port.check  │  │
     │  │ ├─ SKILL    │  │      │  │ - disk.usage  │  │     │  │ - disk.usage  │  │
     │  │ ├─ RAG      │  │      │  │ - ssl.check   │  │     │  │ - ssl.check   │  │
     │  │ └─ Memory   │  │      │  │ - process.*   │  │     │  │ - process.*   │  │
     │  ├────────────┤  │      │  │ - service.*   │  │     │  │ - service.*   │  │
     │  │ LLM Provider│  │      │  │ - http.*      │  │     │  │ - http.*      │  │
     │  │ Manager     │  │      │  │ - dns.lookup  │  │     │  │ - dns.lookup  │  │
     │  │ (Multi-     │  │      │  │ ...and more   │  │     │  │ ...and more   │  │
     │  │  Provider)  │  │      │  ├───────────────┤  │     │  ├───────────────┤  │
     │  └────────────┘  │      │  │ WASM Plugins   │  │     │  │ WASM Plugins   │  │
     └──────────────────┘      │  │ (Dynamic       │  │     │  │ (Dynamic       │  │
                               │  │  Extensions)   │  │     │  │  Extensions)   │  │
                               │  └───────────────┘  │     │  └───────────────┘  │
                               └─────────────────────┘     └─────────────────────┘
```

## Key Components

### 1. Worker Agent (Go)
- **Single binary** (~15MB) — no Docker, no runtime dependencies
- **Install**: `curl -fsSL https://install.gaiops.io/worker | sh`
- **Run**: `sudo gaiops-worker --master ws://master:8080/ws --token xxx`
- **30+ built-in tools**: ping, exec, port, disk, ssl, process, service, http, dns, etc.
- **Dynamic plugins via WASM**: language-agnostic, sandboxed extension system
- **Safety**: command whitelist, param filtering, non-root user, capabilities bounding
- **Auto-reconnect**: exponential backoff, heartbeat-based health

### 2. Master Scheduler (Node.js)
- **Request routing**: intelligently routes tasks to the least-loaded capable Worker
- **Security**: cluster token auth, high-risk action approval, rate limiting
- **Inspection Engine** (new in v2.0):
  - Schedules periodic probes across all workers
  - Supports port.check, http.health, ping.icmp, disk.usage, ssl.cert_check, process.list, dns.lookup, service.status
  - Evaluates results against configurable alert thresholds
  - Generates alert events with severity (info/warning/critical)
  - REST API for managing inspections and viewing results
- **Audit**: complete audit trail for all operations
- **Webhook entry**: external systems (Prometheus, Zabbix, custom) can trigger actions

### 3. Brain Decision Engine (Python)
- **Multi-Agent loop** (LangGraph): Analyst → Planner → ReAct Executor → Reflector
- **Knowledge Engine** (new in v2.0):
  - **SKILL System**: versioned fault → fix → rollback procedures
  - **RAG Engine**: semantic retrieval from fault history and documentation
  - **Memory Isolation**: session/user/node level isolation prevents cross-contamination
- **Multi-Provider LLM**: Ollama, OpenAI, Anthropic, Gemini — hot-reloadable
- **Auto-learning**: Reflector agent creates new SKILLs from novel incidents

## Quick Start

### 1. Start Master + Brain (Docker)
```bash
docker compose up -d master brain
```

### 2. Install Worker Agents on target hosts
```bash
# On each target machine:
curl -fsSL https://install.gaiops.io/worker | sh -s -- \\
  --master ws://<master-ip>:8080/ws \\
  --token my-secret-token
```

### 3. Configure inspections
```bash
curl -X POST http://localhost:8080/api/v1/inspections \\
  -H "Authorization: Bearer my-secret-token" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Web Health Check",
    "probe_type": "http.health",
    "probe_params": {"url": "http://localhost:80/health"},
    "schedule_mode": "interval",
    "interval_seconds": 60,
    "alert_rules": [
      {"metric": "status_code", "operator": ">=", "threshold": 500, "severity": "critical", "message": "HTTP error on {worker_id}"}
    ]
  }'
```

### 4. View alerts
```bash
curl http://localhost:8080/api/v1/alerts/stats \\
  -H "Authorization: Bearer my-secret-token"
```

## Configuration Reference

### Worker (worker.yaml)
```yaml
worker_id: "host-01"
master_url: "ws://master:8080/ws"
cluster_token: "my-secret-token"
heartbeat_interval: 15
reconnect:
  base_delay: 1
  max_delay: 60
max_concurrent_tools: 10
tools:
  exec:
    allowed_commands:
      - "/usr/bin/systemctl"
      - "/usr/bin/docker"
      - "/bin/df"
```

### Brain (brain.yaml or env vars)
```yaml
llm:
  primary_provider: ollama
  providers:
    ollama:
      protocol: ollama
      base_url: "http://localhost:11434"
      models:
        - id: "qwen2.5:7b"
    openai:
      protocol: openai
      api_key: "${OPENAI_API_KEY}"
      models:
        - id: "gpt-4o"
          supports_tools: true
          supports_embeddings: true

knowledge:
  skills_dir: "/var/lib/gaiops/skills"
  rag:
    enabled: true
    chunk_size: 500
    chunk_overlap: 50

memory:
  isolation:
    enabled: true
    session_ttl: 3600
    user_ttl: 86400
    node_ttl: 86400
`

### Master (master.yaml)
```yaml
server:
  host: "0.0.0.0"
  ws_port: 8080
  api_port: 8080
cluster_token: "my-secret-token"
inspection:
  enabled: true
  tick_interval_ms: 10000
  max_inspections: 100
  max_alerts: 5000
  default_interval_seconds: 300
  probe_timeout_seconds: 30
```
