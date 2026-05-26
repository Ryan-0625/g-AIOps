# gAIOps 二次开发重构计划

> **版本**: v2.0-refactor-plan
> **状态**: 待实施
> **基于**: gAIOps v1.x（现有代码基线）
> **覆盖需求**: Worker 动态工具引擎 / Brain 三重认知循环 / Master 粘合增强 / 工具矩阵扩展

---

## 目录

1. [目标架构总览](#1-目标架构总览)
2. [工作流拆分与演进路线图](#2-工作流拆分与演进路线图)
3. [Phase 1 — 基础设施与协议升级](#3-phase-1--基础设施与协议升级)
4. [Phase 2 — Worker 动态工具引擎](#4-phase-2--worker-动态工具引擎)
5. [Phase 3 — Master 粘合增强](#5-phase-3--master-粘合增强)
6. [Phase 4 — Brain 三重认知循环](#6-phase-4--brain-三重认知循环)
7. [Phase 5 — 工具矩阵扩展](#7-phase-5--工具矩阵扩展)
8. [Phase 6 — E2E 验证与生产加固](#8-phase-6--e2e-验证与生产加固)
9. [Breaking Changes 管控清单](#9-breaking-changes-管控清单)
10. [风险评估与缓解策略](#10-风险评估与缓解策略)

---

## 1. 目标架构总览

### 1.1 现状 vs 目标

```
现状 (v1.x)                                目标 (v2.0)
                                            
Brain                                        Brain
┌─────────────────┐                        ┌──────────────────────────┐
│ Analyst         │                        │  Analyst                 │
│   ↓             │                        │    ↓                     │
│ Planner         │                        │  Memory Load             │
│   ↓             │                        │    ↓                     │
│ Execute         │   线性循环              │  Plan (外层)             │
│   ↓             │   Plan-and-execute     │    ↓                     │
│ Reflector       │   + 简单重试            │  ReAct (中层) ──┐       │
│   ↑↓ (replan)   │                        │  │ Thought       │       │
└─────────────────┘                        │  │ Action        │       │
                                            │  │ Observation  │       │
Master                                      │  └──────────────┘       │
┌─────────────────┐                        │  Reflect (内层评分)      │
│ Router          │  普通消息路由           │  ↑↓ (replan/backtrack)   │
│ Tracker         │                        └──────────────────────────┘
│ Approver        │                           ↕ Memory(episodic+semantic)
└─────────────────┘                        
                                            Master
Worker                                      ┌──────────────────────────┐
┌─────────────────┐                        │  Router (增强:工具感知)   │
│ ping.icmp       │  静态编译工具           │  Tracker (增强:部署追踪)  │
│ disk.usage      │                        │  Tool Deployer (新)      │
│ service.status  │                        │  Tool Registry (新)      │
│ process.list    │                        │  Code Relay (新)         │
│ ...             │                        │  Approver (增强:代码审查) │
└─────────────────┘                        └──────────────────────────┘
                                            
                                            Worker
                                            ┌──────────────────────────┐
                                            │ 编译工具 (保持不变)       │
                                            │  ping.icmp / disk / ... │
                                            ├──────────────────────────┤
                                            │ 动态工具引擎 (新增)       │
                                            │  Runtime Pool            │
                                            │  ├─ bash interpreter      │
                                            │  ├─ python3 interpreter   │
                                            │  ├─ node interpreter     │
                                            │  │                        │
                                            │  Sandbox                 │
                                            │  Lifecycle Manager       │
                                            │  Code Compiler (预检)    │
                                            └──────────────────────────┘
```

### 1.2 新增/修改文件总清单

| 层 | 文件 | 操作 | 说明 |
|----|------|------|------|
| **协议** | `proto/envelope.schema.json` | 修改 | 新增 `msg_type` 枚举、`code_body`/`runtime_hints`/`deploy_id` 字段 |
| **协议** | `docs/error-codes.md` | 修改 | 新增动态工具错误码分类 |
| **协议** | `docs/log-schema.md` | 修改 | 新增 `tool_lifecycle`、`memory_op` 标签 |
| **Worker** | `internal/dynamic/compiler.go` | **新增** | 代码语法检查 + 安全预检 |
| **Worker** | `internal/dynamic/sandbox.go` | **新增** | 沙箱执行环境（seccomp/namespace） |
| **Worker** | `internal/dynamic/lifecycle.go` | **新增** | 工具生命周期管理 |
| **Worker** | `internal/dynamic/runtime.go` | **新增** | 运行时进程池管理 |
| **Worker** | `internal/executor/stream.go` | **新增** | 长时间任务流式进度回传 |
| **Worker** | `internal/executor/sandbox.go` | 修改 | 集成动态工具执行路径 |
| **Worker** | `internal/registry/registry.go` | 修改 | 工具结构体扩展、动态工具跟踪 |
| **Worker** | `internal/connection/client.go` | 修改 | 支持 tool_deploy 消息类型 |
| **Worker** | `internal/connection/envelope.go` | 修改 | 扩展消息编解码 |
| **Worker** | `internal/safety/code_scanner.go` | **新增** | 代码静态扫描（敏感 API、危险模式） |
| **Worker** | `internal/config/config.go` | 修改 | 新增动态工具配置节 |
| **Master** | `src/protocol/envelope.ts` | 修改 | 扩展消息工厂和校验 |
| **Master** | `src/protocol/types.ts` | 修改 | 新增可选字段类型 |
| **Master** | `src/server/brain-api.ts` | 修改 | 新增工具部署/查询 API 端点 |
| **Master** | `src/orchestrator/tool-deployer.ts` | **新增** | 工具部署编排引擎 |
| **Master** | `src/orchestrator/router.ts` | 修改 | 工具部署路由逻辑 |
| **Master** | `src/store/registry.ts` | 修改 | 动态工具注册表 |
| **Master** | `src/store/tool-registry.ts` | **新增** | 集群级动态工具目录 |
| **Master** | `src/security/code-approver.ts` | **新增** | 工具代码安全审批 |
| **Master** | `src/security/interceptor.ts` | 修改 | 代码部署拦截规则 |
| **Brain** | `core/graph.py` | **重构** | Plan-ReAct-Reflect 三重循环 |
| **Brain** | `core/state.py` | 修改 | 扩展状态结构 |
| **Brain** | `agents/planner.py` | 重构 | ReAct 推理引擎 |
| **Brain** | `agents/reactor.py` | **新增** | Thought→Action→Observation 循环 |
| **Brain** | `agents/reflector.py` | 重构 | 增强 Reflection 评分 |
| **Brain** | `agents/code_generator.py` | **新增** | LLM 工具代码生成 |
| **Brain** | `agents/deployer.py` | 重构 | 代码生成 → 安全审查 → 部署协调 |
| **Brain** | `memory/episodic.py` | **新增** | 情景记忆 |
| **Brain** | `memory/semantic.py` | **新增** | 语义记忆 |
| **Brain** | `memory/working.py` | **新增** | 工作记忆 |
| **Brain** | `memory/summarizer.py` | **新增** | 记忆压缩检索 |
| **Brain** | `llm/context_window.py` | 重构 | 分层上下文管理 |
| **Brain** | `llm/tokenizer.py` | **新增** | Token 计数与预算管理 |
| **Brain** | `safety/code_scanner.py` | **新增** | Brain 侧代码安全预检 |
| **Brain** | `tools/tool_lifecycle.py` | **新增** | 工具生命周期跟踪 |
| **Brain** | `tools/tool_registry.py` | 修改 | 扩展注册表 |
| **测试** | `worker/internal/dynamic/*_test.go` | **新增** | 动态工具引擎测试 |
| **测试** | `master/src/orchestrator/__tests__/tool-deployer.test.ts` | **新增** | 部署编排测试 |
| **测试** | `master/src/store/__tests__/tool-registry.test.ts` | **新增** | 工具目录测试 |
| **测试** | `brain/memory/*_test.py` | **新增** | 记忆模块测试 |
| **测试** | `brain/agents/reactor_test.py` | **新增** | ReAct 引擎测试 |
| **测试** | `brain/agents/code_generator_test.py` | **新增** | 代码生成测试 |
| **测试** | `brain/llm/tokenizer_test.py` | **新增** | Tokenizer 测试 |

---

## 2. 工作流拆分与演进路线图

### 2.1 时间线概览

```
Phase 1: 基础设施与协议升级          ████████░░░░  ≈ 2 周
  协议扩展 + 配置 + 测试框架

Phase 2: Worker 动态工具引擎          ████████████  ≈ 3 周
  运行时 + 沙箱 + 生命周期

Phase 3: Master 粘合增强             ████████░░░░  ≈ 2 周  
  部署编排 + 工具目录 + API

Phase 4: Brain 三重认知循环           ████████████  ≈ 4 周
  ReAct + 记忆 + 代码生成 + 上下文

Phase 5: 工具矩阵扩展                ██████░░░░░░  ≈ 1.5 周
  新增 10+ 运维工具

Phase 6: E2E 验证与生产加固            ██████░░░░░░  ≈ 1.5 周
  集成测试 + 性能 + 文档
──────────────────────────────────
总计: ≈ 14 周（3.5 月）
```

### 2.2 依赖关系

```
Phase 1 ───┬──→ Phase 2 ──→ Phase 5 (Worker 工具)
           │
           └──→ Phase 3 ──→ Phase 4 (Brain 循环)
                         │
                         └──→ Phase 5 (Brain 工具)
                                    │
                                    ↓
                               Phase 6
```

**关键路径**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 6
**可并行**: Phase 5（部分工具）可与 Phase 3/4 并行

---

## 3. Phase 1 — 基础设施与协议升级

> **目标**: 在不破坏现有通信的前提下，为动态工具能力铺平协议和配置基础
> **周期**: 2 周
> **P0 破坏性变更管控**: 协议枚举扩展 + 版本号提升

### 3.1 协议升级（Envelope Protocol v1 → v1.1）

#### 3.1.1 `proto/envelope.schema.json` 修改

```diff
+ "msg_type": {
+   "enum": ["request", "response", "event", "ack", "heartbeat",
+            "tool_deploy",        # 新增: 工具部署请求（Brain→Master→Worker）
+            "tool_code",          # 新增: 工具代码传输（分片）
+            "tool_status"         # 新增: 工具状态上报（Worker→Master）
+          ]
+ },

+ "code_body": {
+   "type": "string",
+   "description": "工具代码体（tool_deploy/tool_code 消息使用）",
+   "maxLength": 1048576           # 1MB 代码上限（大代码自动分片）
+ },

+ "runtime_hints": {
+   "type": "object",
+   "description": "运行时提示（tool_deploy 消息使用）",
+   "properties": {
+     "interpreter": { "type": "string", "enum": ["bash", "python3", "node"] },
+     "entrypoint": { "type": "string" },
+     "env_vars": { "type": "object" },
+     "resource_limits": {
+       "type": "object",
+       "properties": {
+         "max_memory_mb": { "type": "integer" },
+         "max_cpu_cores": { "type": "number" },
+         "max_timeout_s": { "type": "integer" }
+       }
+     }
+   }
+ },

+ "deploy_id": {
+   "type": "string",
+   "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
+   "description": "工具部署追踪 ID，用于关联 deploy→ack→status 全链路"
+ }
```

#### 3.1.2 版本号策略

```typescript
// master/src/protocol/version.ts
// 当前: VersionRange { min: "1.0", max: "1.0" }
// 升级为:
export const LOCAL_VERSION: VersionRange = { min: "1.0", max: "1.1" };

// 兼容性规则:
// - 主版本号匹配 (1 == 1) → 兼容
// - 选中版本 = min(本地次版本, 远端次版本)
// - v1.0 节点收到 v1.1 消息 → validateEnvelope 中不认识新 msg_type
//   但在 "未知消息类型" 分支中不会崩溃，只会记录校验错误
```

#### 3.1.3 `master/src/protocol/types.ts` 扩展

```typescript
// 新增类型
export type MsgType = "request" | "response" | "event" | "ack" | "heartbeat"
                    | "tool_deploy" | "tool_code" | "tool_status";

export interface RuntimeHints {
  interpreter?: "bash" | "python3" | "node";
  entrypoint?: string;
  env_vars?: Record<string, string>;
  resource_limits?: {
    max_memory_mb?: number;
    max_cpu_cores?: number;
    max_timeout_s?: number;
  };
}

// Envelope 接口扩展（所有新增字段为 optional，零值安全）
export interface Envelope {
  // ... 现有字段不变 ...
  
  // 新增可选字段
  code_body?: string;
  runtime_hints?: RuntimeHints;
  deploy_id?: string;
}
```

#### 3.1.4 `master/src/protocol/envelope.ts` 扩展

```typescript
// 新增消息工厂函数
export function newToolDeploy(
  traceId: string,
  deployId: string,
  action: string,
  codeBody: string,
  runtimeHints: RuntimeHints,
  opts: EnvelopeOptions = {},
): Envelope {
  return {
    proto_version: "1.1",
    trace_id: traceId,
    msg_id: uuidv4(),
    msg_type: "tool_deploy",
    timestamp: Math.floor(Date.now() / 1000),
    source: "master",
    target: "worker",
    target_id: opts.targetId ?? "*",
    correlation_id: "",
    deploy_id: deployId,
    payload: {
      action,
      params: {},
      status: "pending",
    },
    code_body: codeBody,
    runtime_hints: runtimeHints,
  };
}
```

### 3.2 错误码扩展

```markdown
# docs/error-codes.md 新增:

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
- **含义**: Worker 没有所需的解释器运行时
- **模块**: Worker / dynamic/runtime
- **处理策略**: `replan` — Brain 选择 Worker 支持的解释器

### TOOL_DEPLOY_TIMEOUT
- **含义**: 工具部署超时（代码传输或编译超时）
- **模块**: Master / tool-deployer
- **处理策略**: `retry` — 重试部署

### BRAIN_CODE_GEN_FAILED
- **含义**: Brain 代码生成器无法生成有效工具代码
- **模块**: Brain / agents/code_generator
- **处理策略**: `human` — 需要人工编写工具代码

### MEMORY_RETRIEVAL_FAILED
- **含义**: 记忆模块检索失败（向量库不可达）
- **模块**: Brain / memory
- **处理策略**: 非错误 — 降级为无记忆模式
```

```python
# brain/safety/error_classifier.py — 策略扩展
STRATEGIES["replan"].update({
    "TOOL_DEPLOY_FAILED", "TOOL_COMPILE_ERROR",
    "TOOL_MEMORY_LIMIT", "TOOL_RUNTIME_UNAVAILABLE",
})
STRATEGIES["human"].add("TOOL_SANDBOX_VIOLATION")
STRATEGIES["retry"].add("TOOL_DEPLOY_TIMEOUT")
```

### 3.3 配置扩展

```yaml
# config/worker.yaml.example — 新增 [可选] 节

# === 动态工具引擎（可选，默认禁用） ===
dynamic_tools:
  enabled: false                            # 启用动态工具支持
  interpreters:                             # Worker 提供的运行时
    bash: "/bin/bash"
    python3: "/usr/bin/python3"
    node: "/usr/bin/node"
  sandbox:
    enabled: true
    temp_dir: "/tmp/gaiops-dynamic/"        # 代码执行临时目录
    max_output: 1048576                     # 最大输出字节
    max_memory_mb: 512                      # 最大内存
    enforce_timeout: true                   # 强制超时
  runtime_pool:
    max_bash_procs: 5                       # bash 进程池大小
    max_python_procs: 3                     # python 进程池大小
    max_node_procs: 2                       # node 进程池大小
    idle_timeout: 300                       # 空闲回收秒数
  lifecycle:
    max_deployed_tools: 20                  # 最大部署工具数
    auto_cleanup_interval: 3600             # 自动清理间隔（秒）
    persist_on_disk: false                  # 重启后是否持久化
```

### 3.4 测试框架准备

```bash
# 新增测试分类（统一 Makefile 入口）
make test-protocol    # 协议版本协商 + 编解码兼容性测试
make test-safe-upgrade # 滚动升级兼容性矩阵测试
```

---

## 4. Phase 2 — Worker 动态工具引擎

> **目标**: Worker 支持接收 Brain 下发的脚本代码，在沙箱中安全执行，并上报执行状态和进度
> **周期**: 3 周
> **前序依赖**: Phase 1 协议升级完成

### 4.1 分层架构

```
Worker 动态工具引擎

┌──────────────────────────────────────────────────────┐
│                    Connection Layer                   │
│  接收 tool_deploy → 解析 code_body + runtime_hints    │
│  回传 tool_status → 部署结果/执行进度                  │
└──────────────────────┬───────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────┐
│               Dynamic Tool Manager                    │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │ Compiler │→ │ Sandbox  │→ │ Lifecycle Manager  │   │
│  │ 代码预检  │  │ 环境隔离  │  │ 注册/GC/持久化    │   │
│  └──────────┘  └────┬─────┘  └───────────────────┘   │
│                      ↓                                │
│  ┌─────────────────────────────────────────────┐      │
│  │           Runtime Pool                       │      │
│  │  ┌──────┐  ┌────────┐  ┌──────┐             │      │
│  │  │ bash │  │python3 │  │ node │   ...       │      │
│  │  │进程池│  │ 进程池  │  │进程池 │             │      │
│  │  └──────┘  └────────┘  └──────┘             │      │
│  └─────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────┘
```

### 4.2 `internal/dynamic/compiler.go` — 代码编译/预检

```go
package dynamic

import (
    "fmt"
    "os"
    "os/exec"
    "strings"
)

// CompileResult 代码预检结果
type CompileResult struct {
    Valid       bool
    Language    string   // bash | python3 | node
    Errors      []string // 语法错误列表
    Warnings    []string // 安全警告
    RiskLevel   string   // safe | suspicious | dangerous
    Entrypoint  string   // 入口函数/文件
}

// Compiler 代码编译器，负责语法检查和基本安全扫描
type Compiler struct {
    tempDir string
    scanners []CodeScanner // 安全扫描器链
}

// CodeScanner 代码安全扫描接口（策略模式）
type CodeScanner interface {
    Scan(code string, language string) ([]string, error)
    Name() string
}

// Compile 执行完整的代码预检流水线
func (c *Compiler) Compile(code string, lang string) *CompileResult {
    result := &CompileResult{Valid: false, Language: lang}
    
    // 1. 写入临时文件
    tmpFile := c.writeTemp(code, lang)
    defer os.Remove(tmpFile)
    
    // 2. 语法检查
    switch lang {
    case "bash":
        result.Errors = c.checkBashSyntax(tmpFile)
    case "python3":
        result.Errors = c.checkPythonSyntax(tmpFile)
    case "node":
        result.Errors = c.checkNodeSyntax(tmpFile)
    }
    
    if len(result.Errors) > 0 {
        return result
    }
    
    // 3. 安全扫描（扫描器链）
    for _, scanner := range c.scanners {
        warnings, err := scanner.Scan(code, lang)
        if err != nil {
            result.Warnings = append(result.Warnings, err.Error())
        }
        result.Warnings = append(result.Warnings, warnings...)
    }
    
    result.Valid = true
    return result
}
```

### 4.3 `internal/dynamic/sandbox.go` — 沙箱执行环境

```go
package dynamic

import (
    "context"
    "os/exec"
    "syscall"
    "time"
)

// SandboxConfig 沙箱配置
type SandboxConfig struct {
    TempDir      string        // 临时目录
    MaxOutput    int64         // 最大输出字节
    MaxMemoryMB  int64         // 最大内存（MB）
    MaxCPUCores  float64       // 最大 CPU 核数
    EnableNet    bool          // 是否允许网络
    Timeout      time.Duration // 强制超时
}

// SandboxExecutor 沙箱执行器
type SandboxExecutor struct {
    config SandboxConfig
    interpreter string
}

// Execute 在沙箱中执行脚本代码
func (se *SandboxExecutor) Execute(ctx context.Context, code string, params map[string]interface{}) (map[string]interface{}, error) {
    // 1. 写入临时脚本文件
    scriptFile := se.writeScript(code)
    defer cleanupScript(scriptFile)
    
    // 2. 构建执行命令（不使用 shell 包装）
    cmd := exec.CommandContext(ctx, se.interpreter, scriptFile)
    
    // 3. 设置进程级隔离（Linux namespace）
    cmd.SysProcAttr = &syscall.SysProcAttr{
        Cloneflags: syscall.CLONE_NEWPID |  // PID 隔离
                    syscall.CLONE_NEWNS  |  // Mount 隔离
                    syscall.CLONE_NEWIPC,   // IPC 隔离
    }
    
    // 4. 通过环境变量传入参数（安全，无注入风险）
    cmd.Env = append(cmd.Env,
        fmt.Sprintf("TOOL_PARAMS=%s", jsonEncode(params)),
        fmt.Sprintf("TOOL_TIMEOUT=%d", se.config.Timeout.Seconds()),
    )
    
    // 5. 捕获输出（受 MaxOutput 限制）
    output, err := cmd.Output()
    if err != nil {
        return nil, fmt.Errorf("execution failed: %w", err)
    }
    
    // 6. 解析 JSON 输出
    return parseJSONOutput(output[:min(len(output), int(se.config.MaxOutput))])
}
```

### 4.4 `internal/dynamic/runtime.go` — 运行时进程池

```go
package dynamic

import (
    "context"
    "os/exec"
    "sync"
    "time"
)

// RuntimePool 运行时进程池
// 维护一个预热的解释器进程池，减少冷启动延迟
type RuntimePool struct {
    mu       sync.Mutex
    pool     map[string][]*warmProcess
    config   map[string]RuntimeConfig
    maxIdle  time.Duration
}

type warmProcess struct {
    cmd      *exec.Cmd
    lastUsed time.Time
    id       int
}

type RuntimeConfig struct {
    Interpreter string // 解释器路径
    MaxProcs    int    // 最大进程数
}

// Acquire 从池中获取一个预热进程（或创建新的）
func (rp *RuntimePool) Acquire(ctx context.Context, lang string) (*warmProcess, error) {
    rp.mu.Lock()
    defer rp.mu.Unlock()
    
    // 1. 尝试从池中获取闲置进程
    procs := rp.pool[lang]
    for i, p := range procs {
        if time.Since(p.lastUsed) < rp.maxIdle {
            rp.pool[lang] = append(procs[:i], procs[i+1:]...)
            p.lastUsed = time.Now()
            return p, nil
        }
    }
    
    // 2. 池中无可用进程 → 创建新进程（预热）
    cfg := rp.config[lang]
    cmd := exec.CommandContext(ctx, cfg.Interpreter)
    if err := cmd.Start(); err != nil {
        return nil, err
    }
    
    return &warmProcess{cmd: cmd, lastUsed: time.Now()}, nil
}

// Release 将进程归还池中
func (rp *RuntimePool) Release(p *warmProcess) {
    rp.mu.Lock()
    defer rp.mu.Unlock()
    
    p.lastUsed = time.Now()
    lang := "" // 从进程推断语言
    procs := rp.pool[lang]
    
    cfg := rp.config[lang]
    if len(procs) >= cfg.MaxProcs {
        p.cmd.Process.Kill() // 池满，直接终止
        return
    }
    
    rp.pool[lang] = append(procs, p)
}

// ReapIdle 定期回收闲置进程
func (rp *RuntimePool) ReapIdle() int {
    rp.mu.Lock()
    defer rp.mu.Unlock()
    
    reaped := 0
    for lang, procs := range rp.pool {
        remaining := make([]*warmProcess, 0)
        for _, p := range procs {
            if time.Since(p.lastUsed) > rp.maxIdle {
                p.cmd.Process.Kill()
                reaped++
            } else {
                remaining = append(remaining, p)
            }
        }
        rp.pool[lang] = remaining
    }
    return reaped
}
```

### 4.5 `internal/dynamic/lifecycle.go` — 工具生命周期管理

```go
package dynamic

import "sync"

// ToolState 工具状态
type ToolState string

const (
    StatePending    ToolState = "pending"     // 代码接收中
    StateCompiling  ToolState = "compiling"   // 语法检查中
    StateDeployed   ToolState = "deployed"    // 部署完成，可执行
    StateRunning    ToolState = "running"     // 正在执行
    StateFailed     ToolState = "failed"      // 部署/执行失败
    StateUninstalled ToolState = "uninstalled" // 已卸载
)

// DynamicTool 动态工具元数据
type DynamicTool struct {
    Action       string            `json:"action"`
    Source       string            `json:"source"`       // "brain"
    Language     string            `json:"language"`     // bash/python3/node
    CodeHash     string            `json:"code_hash"`    // SHA256
    RiskLevel    string            `json:"risk_level"`   // 继承自 tool.create
    State        ToolState         `json:"state"`
    DeployedAt   int64             `json:"deployed_at"`
    LastUsed     int64             `json:"last_used"`
    ExecuteCount int64             `json:"execute_count"`
    FailCount    int64             `json:"fail_count"`
    ParamsSchema map[string]interface{} `json:"params_schema,omitempty"`
}

// LifecycleManager 动态工具生命周期管理器
type LifecycleManager struct {
    mu      sync.RWMutex
    tools   map[string]*DynamicTool   // action → tool
    maxTools int
    compiler *Compiler
    sandbox  *SandboxExecutor
    registry *registry.Registry       // 注入 Worker 的全局注册表
}

// Deploy 部署新工具: 编译 → 注册 → 标记可用
func (lm *LifecycleManager) Deploy(action string, code string, lang string, hints map[string]interface{}) error {
    lm.mu.Lock()
    if len(lm.tools) >= lm.maxTools {
        lm.mu.Unlock()
        return fmt.Errorf("max dynamic tools reached (%d)", lm.maxTools)
    }
    lm.mu.Unlock()
    
    // 1. 代码预检
    result := lm.compiler.Compile(code, lang)
    if !result.Valid {
        return &DeployError{Code: "TOOL_COMPILE_ERROR", Errors: result.Errors}
    }
    
    // 2. 通过 RegisterDynamic 注册到 Worker 全局注册表
    lm.registry.RegisterDynamic(registry.Tool{
        Action:       action,
        Timeout:      lm.parseTimeout(hints),
        IsIdempotent: false,
        RiskLevel:    lm.parseRiskLevel(hints),
        Execute:      lm.makeDynamicExecutor(action, lang, code),
        Source:       "dynamic",
    })
    
    // 3. 记录元数据
    lm.mu.Lock()
    lm.tools[action] = &DynamicTool{
        Action:     action,
        Language:   lang,
        CodeHash:   sha256Hash(code),
        RiskLevel:  lm.parseRiskLevel(hints),
        State:      StateDeployed,
        DeployedAt: nowUnix(),
    }
    lm.mu.Unlock()
    
    return nil
}

// makeDynamicExecutor 为动态工具创建执行函数（闭包）
func (lm *LifecycleManager) makeDynamicExecutor(action, lang, code string) registry.ToolFn {
    return func(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
        // 更新状态
        lm.trackUsage(action)
        
        // 通过沙箱执行
        return lm.sandbox.Execute(ctx, code, params)
    }
}
```

### 4.6 `internal/connection/client.go` 扩展

```go
// handleToolDeploy 处理 Master 下发的工具部署消息
func (c *WSClient) handleToolDeploy(env *envelope.Envelope) {
    deployID := env.DeployID
    action := env.Payload.Action
    code := env.CodeBody
    hints := env.RuntimeHints
    
    logger.Info("receiving tool deploy", "deploy_id", deployID, "action", action)
    
    // 1. 部署工具
    err := c.dynamicManager.Deploy(action, code, hints.Interpreter, hints)
    
    // 2. 回传部署状态
    status := "success"
    errorCode := ""
    errorMsg := ""
    if err != nil {
        status = "failure"
        errorCode = extractErrorCode(err)
        errorMsg = err.Error()
    }
    
    c.sendEnvelope(envelope.NewEnvelope{
        MsgType:  "tool_status",
        DeployID: deployID,
        Payload: envelope.Payload{
            Action: action,
            Status: status,
            Error:  &envelope.ErrorInfo{Code: errorCode, Message: errorMsg},
        },
    })
}
```

### 4.7 `internal/executor/stream.go` — 长时间任务进度流式回传

```go
package executor

// ProgressReporter 进度报告器
// 长时间运行的动态工具可通过此接口回传进度
type ProgressReporter interface {
    Report(percent int, message string)
}

// progressWriter 包装 stderr 用于工具内嵌进度输出
// 工具向 stderr 写 JSON 行: {"progress": 45, "message": "正在清理..."}
type progressWriter struct {
    callback func(percent int, message string)
    buffer   []byte
}

func (pw *progressWriter) Write(p []byte) (n int, err error) {
    pw.buffer = append(pw.buffer, p...)
    // 尝试解析 progress JSON
    if entry := tryParseProgress(pw.buffer); entry != nil {
        pw.callback(entry.Percent, entry.Message)
        pw.buffer = pw.buffer[:0]
    }
    return len(p), nil
}
```

### 4.8 `internal/safety/code_scanner.go` — 代码安全扫描

```go
package safety

// ShellInjectionScanner 检测 shell 注入模式
type ShellInjectionScanner struct{}

func (s *ShellInjectionScanner) Scan(code string, language string) ([]string, error) {
    warnings := []string{}
    patterns := map[string]*regexp.Regexp{
        "rm -rf /":          regexp.MustCompile(`rm\s+(-rf?|--recursive)\s+/`),
        "format_disk":       regexp.MustCompile(`mkfs\.|dd\s+if=.*of=\/dev`),
        "reverse_shell":     regexp.MustCompile(`(bash|sh|nc|perl|python).*(-i|reverse|>&/dev/tcp/)`),
        "crypto_miner":      regexp.MustCompile(`(stratum|minerd|xmrig|cryptonight)`),
        "etc_shadow_access": regexp.MustCompile(`/etc/(shadow|passwd|sudoers)`),
    }
    
    for name, pattern := range patterns {
        if pattern.MatchString(code) {
            warnings = append(warnings, fmt.Sprintf("suspicious pattern detected: %s", name))
        }
    }
    return warnings, nil
}

// ResourceScanner 检测资源滥用模式
type ResourceScanner struct{}

func (s *ResourceScanner) Scan(code string, language string) ([]string, error) {
    warnings := []string{}
    // 检测 fork 炸弹
    if regexp.MustCompile(`:\{\s*\|:\s*&\s*\};:`).MatchString(code) {
        warnings = append(warnings, "fork bomb detected")
    }
    // 检测无限循环
    if regexp.MustCompile(`while\s+(true|1)\s*;?\s*do`).MatchString(code) {
        warnings = append(warnings, "potential infinite loop")
    }
    return warnings, nil
}
```

---

## 5. Phase 3 — Master 粘合增强

> **目标**: Master 作为 Brain 和 Worker 之间的可靠中间人，负责工具部署编排、代码传输、工具目录维护
> **周期**: 2 周
> **前序依赖**: Phase 1 协议升级完成

### 5.1 新增模块: `src/orchestrator/tool-deployer.ts`

```typescript
/**
 * ToolDeployer — 工具部署编排引擎
 * 
 * 负责将 Brain 生成的工具代码可靠地部署到目标 Worker：
 * 1. 接收 Brain 部署请求（含代码 + 运行时提示）
 * 2. 分片传输（代码 > 1MB 时自动分片）
 * 3. 等待 Worker ACK + 部署结果
 * 4. 超时重试（最多 2 次）
 * 5. 将部署结果回传给 Brain
 */
export class ToolDeployer {
  private pendingDeploys = new Map<string, DeployState>();
  private readonly MAX_RETRIES = 2;
  private readonly CHUNK_SIZE = 1_000_000; // 1MB

  async deploy(
    action: string,
    codeBody: string,
    runtimeHints: RuntimeHints,
    targetWorkerId?: string,
  ): Promise<DeployResult> {
    const deployId = uuidv4();
    
    // 1. 写入追踪状态
    this.pendingDeploys.set(deployId, {
      action,
      deployId,
      status: "deploying",
      startedAt: Date.now(),
      retryCount: 0,
    });

    // 2. 路由到目标 Worker（或广播）
    const workers = targetWorkerId
      ? [this.registry.getWorker(targetWorkerId)!]
      : this.registry.findWorkersForDynamicDeploy();

    if (workers.length === 0) {
      return { deployId, status: "failure", error: { code: "NO_AVAILABLE_WORKER_FOR_DEPLOY" } };
    }

    // 3. 分片发送
    const chunks = this.chunkCode(codeBody);
    for (const worker of workers) {
      for (let i = 0; i < chunks.length; i++) {
        await this.sendChunk(worker.workerId, deployId, action, chunks[i], i, chunks.length);
      }
    }

    // 4. 等待部署确认（带超时）
    return this.waitForDeployCompletion(deployId, 30_000);
  }

  private chunkCode(code: string): string[] {
    if (code.length <= this.CHUNK_SIZE) return [code];
    const chunks: string[] = [];
    for (let i = 0; i < code.length; i += this.CHUNK_SIZE) {
      chunks.push(code.slice(i, i + this.CHUNK_SIZE));
    }
    return chunks;
  }

  private async sendChunk(
    workerId: string,
    deployId: string,
    action: string,
    chunk: string,
    index: number,
    total: number,
  ): Promise<void> {
    const envelope = newToolDeploy(
      deployId,
      deployId,
      action,
      chunk,
      { interpreter: "bash" }, // runtime hints from Brain
    );
    // 附加分片元数据到 params
    envelope.payload.params = {
      _chunk_index: index,
      _chunk_total: total,
    };
    
    await this.wsServer.send(workerId, envelope);
  }
}
```

### 5.2 新增模块: `src/store/tool-registry.ts`

```typescript
/**
 * ToolRegistry — 集群级动态工具目录
 * 
 * 维护整个集群中所有 Worker 上部署的动态工具清单。
 * Brain 可通过 REST API 查询哪些工具在哪些 Worker 上可用。
 */
export interface DynamicToolEntry {
  action: string;
  workerId: string;
  language: "bash" | "python3" | "node";
  riskLevel: string;
  deployedAt: number;
  state: "deployed" | "running" | "failed";
  version: number;          // 每次重新部署递增
  codeHash: string;         // SHA256
}

export class ToolRegistry {
  private tools = new Map<string, Map<string, DynamicToolEntry>>();
  // ↑ 外层 key: action, 内层 key: workerId

  /** 注册一个部署成功的动态工具 */
  register(workerId: string, action: string, meta: Partial<DynamicToolEntry>): void {
    if (!this.tools.has(action)) {
      this.tools.set(action, new Map());
    }
    const byWorker = this.tools.get(action)!;
    const existing = byWorker.get(workerId);
    
    byWorker.set(workerId, {
      action,
      workerId,
      language: meta.language || "bash",
      riskLevel: meta.riskLevel || "dangerous",
      deployedAt: Date.now(),
      state: "deployed",
      version: (existing?.version || 0) + 1,
      codeHash: meta.codeHash || "",
    });
  }

  /** 卸载工具 */
  unregister(workerId: string, action: string): void {
    this.tools.get(action)?.delete(workerId);
  }

  /** Brain 查询某个 action 在哪些 Worker 上可用 */
  findWorkersForAction(action: string): DynamicToolEntry[] {
    const byWorker = this.tools.get(action);
    if (!byWorker) return [];
    return Array.from(byWorker.values())
      .filter(e => e.state === "deployed");
  }

  /** 查询所有动态工具的聚合视图（Brain 调用） */
  listAll(): Record<string, DynamicToolEntry[]> {
    const result: Record<string, DynamicToolEntry[]> = {};
    for (const [action, byWorker] of this.tools) {
      result[action] = Array.from(byWorker.values());
    }
    return result;
  }
}
```

### 5.3 REST API 扩展

```typescript
// master/src/server/brain-api.ts

// 新增端点（不影响现有端点）：

/**
 * POST /api/v1/tools/deploy
 * Brain → Master: 部署新工具到 Worker
 * Body: {
 *   action: "custom.healthcheck",
 *   code: "#!/bin/bash\ncurl -s $1",
 *   interpreter: "bash",
 *   target_worker_id?: string,
 *   timeout: 30
 * }
 */
router.post("/api/v1/tools/deploy",
  authenticate,
  validateDeployRequest,
  async (req, res) => {
    const { action, code, interpreter, target_worker_id } = req.body;
    
    const result = await toolDeployer.deploy(
      action,
      code,
      { interpreter },
      target_worker_id,
    );
    
    res.json(result);
  },
);

/**
 * GET /api/v1/tools
 * 查询集群中所有动态工具
 * Response: { tools: { "custom.healthcheck": [{ workerId, state, ... }] } }
 */
router.get("/api/v1/tools",
  authenticate,
  async (req, res) => {
    res.json({ tools: toolRegistry.listAll() });
  },
);

/**
 * DELETE /api/v1/tools/:action
 * 从所有 Worker 上卸载指定工具
 */
router.delete("/api/v1/tools/:action",
  authenticate,
  async (req, res) => {
    const { action } = req.params;
    await toolDeployer.undeploy(action);
    res.json({ status: "success", action });
  },
);
```

### 5.4 安全审批: `src/security/code-approver.ts`

```typescript
/**
 * CodeApprover — 工具代码安全审批
 * 
 * 对于 Brain 生成的工具代码，在部署前执行安全检查：
 * 1. 静态规则扫描（禁止的危险模式）
 * 2. 风险等级评估
 * 3. 高风险代码 → 需要人工审批
 */
export class CodeApprover {
  private readonly DANGEROUS_PATTERNS = [
    /rm\s+(-rf?)\s+\//,
    /mkfs\.\w+/,
    /dd\s+if=.*of=\/dev\//,
    /chmod\s+777/,
    /(bash|sh|perl|python).*(-i|reverse)/,
  ];

  async approveCode(
    action: string,
    code: string,
    riskLevel: string,
  ): Promise<ApprovalResult> {
    // 1. 检查危险模式
    const violations = this.DANGEROUS_PATTERNS
      .filter(p => p.test(code))
      .map(p => p.source);

    if (violations.length > 0) {
      return {
        approved: false,
        reason: `Dangerous pattern(s) detected: ${violations.join(", ")}`,
        requiresHumanReview: true,
      };
    }

    // 2. 根据风险等级决定是否需要人工审批
    if (riskLevel === "dangerous") {
      return {
        approved: false,
        reason: "Dynamic tool with dangerous risk level requires human approval",
        requiresHumanReview: true,
      };
    }

    return { approved: true, requiresHumanReview: false };
  }
}
```

### 5.5 路由增强

```typescript
// master/src/orchestrator/router.ts — 新增工具部署路由

class Router {
  // 原有: route(action) — 工具执行路由
  // 新增: findWorkersForDynamicDeploy() — 工具部署路由
  
  findWorkersForDynamicDeploy(): WorkerNode[] {
    // 只选择支持动态工具的 Worker
    return Array.from(this.registry.workers.values())
      .filter(w => w.caps.supportsDynamicTools);  // 新增能力字段
  }
}

// master/src/store/registry.ts — Worker 能力扩展
export interface WorkerCapability {
  // ... 现有字段
  supportsDynamicTools?: boolean;  // 新增
  supportedInterpreters?: string[]; // 新增: ["bash", "python3"]
  maxCodeSize?: number;             // 新增: 最大代码体
}
```

---

## 6. Phase 4 — Brain 三重认知循环

> **目标**: 重构 Brain 推理引擎，从线性 Plan-and-Execute 升级为 Plan-ReAct-Reflect 三重循环，并植入记忆系统
> **周期**: 4 周
> **前序依赖**: Phase 3 Master API 就绪

### 6.1 整体架构

```
                    ┌──────────────────────────────────────────┐
                    │               Memory System               │
                    │  ┌──────────┐  ┌──────────┐  ┌────────┐ │
                    │  │ Episodic │  │ Semantic │  │Working │ │
                    │  │ History  │  │ Knowhow  │  │Context │ │
                    │  └──────────┘  └──────────┘  └────────┘ │
                    └──────────────────┬───────────────────────┘
                                       │ 加载记忆
                                       ▼
Analyst → Memory Load → ┌──────────────────────────────────────┐
                        │         Plan (外层循环)               │
                        │  • 定义目标状态                        │
                        │  • 分解为子任务                        │
                        │  • 依赖分析 & 优先级                   │
                        └──────────────┬───────────────────────┘
                                       │ 选择下一个子任务
                                       ▼
                        ┌──────────────────────────────────────┐
                        │        ReAct (中层循环)               │
                        │                                      │
                        │  ┌──────────┐                        │
                        │  │ Thought  │  LLM推理: "我需要..."│
                        │  └────┬─────┘                        │
                        │       ▼                              │
                        │  ┌──────────┐                        │
                        │  │ Action   │ 调用工具/部署工具       │
                        │  └────┬─────┘                        │
                        │       ▼                              │
                        │  ┌──────────┐                        │
                        │  │ Observe  │ 解析工具输出           │
                        │  └────┬─────┘                        │
                        │       │  需要更多信息?                │
                        │  ─────┘  ───→ 回到 Thought           │
                        │                                      │
                        └──────────────┬───────────────────────┘
                                       │ 子任务完成/失败
                                       ▼
                        ┌──────────────────────────────────────┐
                        │       Reflect (内层评分)              │
                        │  • 评估子任务结果                     │
                        │  • 检测自循环                         │
                        │  • 决策: continue/replan/backtrack   │
                        │  • 更新 Episodic Memory              │
                        └──────┬───────────────┬───────────────┘
                               │              │
                        continue         replan/backtrack
                               │              │
                               ▼              └──→ Plan
                        下一个子任务
                               │
                               ▼
                    ┌──────────────────────┐
                    │  所有子任务完成        │
                    │  → 生成结论           │
                    │  → 存入 Semantic Mem  │
                    │  → 返回结果           │
                    └──────────────────────┘
```

### 6.2 `core/graph.py` — 重构为三重循环

```python
"""LangGraph state graph — Plan-ReAct-Reflect triple loop."""

class GraphEngine:
    async def _run_graph(self, state: GraphState, context: str) -> None:
        set_trace_id(state.trace_id)
        try:
            # Phase 0: Analyst — understand context
            state = await analyst_node(state, context, self.llm)
            
            # Phase 0.5: Memory Load — load relevant episodic + semantic memories
            state = await self.memory.load_relevant(state, context)
            
            # ── 外层循环: Plan ──────────────────────────────────
            while not state.is_done() and not state.needs_human:
                
                # Step 1: Generate/Refine Plan
                if not state.plan:
                    state = await planner_node(state, context, self.llm)
                    if not state.plan:
                        break
                
                # Select current sub-task
                step = state.plan[state.current_step]
                state.current_action = step["action"]
                
                # ── 中层循环: ReAct ─────────────────────────────
                react_result = await self._react_loop(state, step, context)
                
                # ── 内层: Reflect ───────────────────────────────
                state = await reflector_node(state, react_result)
                
                if state.needs_human:
                    break
                
                # Update Episodic Memory
                await self.memory.episodic.store(state, step, react_result)
                
                # Decide next action
                if state.current_step_dir == "backtrack":
                    continue  # 回到当前步骤重试
                elif state.current_step_dir == "replan":
                    state.plan = []  # 清除计划，外层循环重新规划
                    continue
                
                state.advance()  # 进入下一步
            
            # Store successful pattern to Semantic Memory
            if not state.needs_human and state.conclusion:
                await self.memory.semantic.store_success_pattern(state)
                
        except Exception as e:
            logger.error("Session failed", ...)
        finally:
            self.completed_sessions[state.trace_id] = state.to_dict()
    
    async def _react_loop(
        self, state: GraphState, step: dict, context: str
    ) -> ReActResult:
        """ReAct 中层循环: Thought → Action → Observation.
        
        循环直到:
        - 工具执行成功（返回 Observation）
        - 达到最大 ReAct 步数（3 步后强制 Reflect）
        - 检测到循环
        """
        max_react_steps = 3
        trajectory = []
        
        for react_step in range(max_react_steps):
            # Thought: LLM 推理当前情况
            thought = await self._generate_thought(state, step, trajectory, context)
            
            # Action: 执行工具或部署新工具
            action_result = await self._execute_action(
                state, thought, step, context
            )
            
            # Observation: 解析工具输出
            observation = self._parse_observation(action_result)
            trajectory.append({
                "thought": thought,
                "action": step["action"],
                "observation": observation,
            })
            
            # 成功 → 退出 ReAct
            if action_result.get("status") == "success":
                return ReActResult(
                    status="success",
                    data=action_result.get("data", {}),
                    trajectory=trajectory,
                )
            
            # 特定错误 → 尝试部署工具
            if self._should_attempt_deploy(action_result, trajectory):
                deploy_ok = await self.deployer.auto_deploy(
                    state, step, action_result
                )
                if deploy_ok:
                    continue  # 部署成功，重试执行
        
        return ReActResult(
            status="failure",
            error=action_result.get("error", {}),
            trajectory=trajectory,
            react_steps=len(trajectory),
        )
```

### 6.3 `memory/episodic.py` — 情景记忆

```python
"""Episodic Memory — 记录历史执行轨迹。

每个 session 的执行步骤、成功/失败模式、错误上下文都会存入情景记忆。
后续 session 可通过相似度检索找到历史模式，避免重复犯错。
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Episode:
    """一条执行记录"""
    trace_id: str
    context_hash: str          # 上下文特征（用于相似度匹配）
    action: str
    params: dict[str, Any]
    status: str                # "success" | "failure"
    error_code: Optional[str]
    error_message: Optional[str]
    summary: str               # LLM 生成的一句话摘要
    duration_ms: int
    timestamp: int = 0


class EpisodicMemory:
    """情景记忆存储。
    
    当前使用内存存储（开发期），后续可对接向量数据库。
    """
    
    def __init__(self, max_episodes: int = 1000):
        self.episodes: list[Episode] = []
        self.max_episodes = max_episodes
    
    async def store(self, episode: Episode) -> None:
        """存储一条执行记录。超过上限时淘汰最旧记录。"""
        self.episodes.append(episode)
        if len(self.episodes) > self.max_episodes:
            self.episodes.pop(0)
    
    async def retrieve_similar(
        self, action: str, error_code: Optional[str] = None, top_k: int = 3
    ) -> list[Episode]:
        """检索相似历史执行记录。
        
        简易实现: 按 action 和 error_code 精确匹配。
        后续可升级为 embedding 相似度检索。
        """
        candidates = [e for e in self.episodes if e.action == action]
        if error_code:
            candidates = [e for e in candidates if e.error_code == error_code]
        return candidates[-top_k:]  # 返回最近的 top_k
    
    def stats(self) -> dict[str, int]:
        return {
            "total_episodes": len(self.episodes),
            "success_count": sum(1 for e in self.episodes if e.status == "success"),
            "failure_count": sum(1 for e in self.episodes if e.status == "failure"),
        }
```

### 6.4 `memory/semantic.py` — 语义记忆

```python
"""Semantic Memory — 运维知识库。

存储:
- 工具用法模式（什么场景用什么工具、常见参数模式）
- 已知修复策略（特定错误码的最佳处理方式）
- 部署模式（什么工具代码适合什么任务）
"""

@dataclass
class KnowledgeEntry:
    """一条运维知识"""
    topic: str                      # 主题标签
    pattern: str                    # 匹配模式（action/error组合）
    solution: str                   # 解决策略
    confidence: float               # 置信度 [0, 1]
    source: str                     # "learned" | "predefined" | "human"
    created_at: int
    last_used: int
    use_count: int


class SemanticMemory:
    def __init__(self):
        # 预置知识（初始种子）
        self.entries: list[KnowledgeEntry] = [
            KnowledgeEntry(
                topic="disk_full",
                pattern="disk.usage:usage_pct>90",
                solution="execute disk.cleanup or exec.run with cleanup script",
                confidence=0.9, source="predefined",
            ),
            KnowledgeEntry(
                topic="service_down",
                pattern="service.status:status=inactive",
                solution="execute service.restart, then verify with service.status",
                confidence=0.8, source="predefined",
            ),
            KnowledgeEntry(
                topic="tool_not_found",
                pattern="NO_AVAILABLE_WORKER:*",
                solution="check deployer templates; if exists, deploy; else ask LLM to generate code",
                confidence=0.7, source="predefined",
            ),
        ]
    
    async def query(self, action: str, error_code: Optional[str], context: str) -> Optional[KnowledgeEntry]:
        """根据当前执行上下文检索相关知识"""
        pattern_key = f"{action}:{error_code}" if error_code else f"{action}:*"
        for entry in self.entries:
            if entry.pattern == pattern_key or entry.pattern.endswith(":*"):
                entry.last_used = int(time.time())
                entry.use_count += 1
                return entry
        return None
    
    async def learn(self, entry: KnowledgeEntry) -> None:
        """从成功经验中学习新知识"""
        # 去重：相同 pattern 的更新置信度
        for existing in self.entries:
            if existing.pattern == entry.pattern:
                existing.confidence = min(1.0, existing.confidence + 0.1)
                existing.solution = entry.solution
                return
        self.entries.append(entry)
```

### 6.5 `memory/working.py` — 工作记忆

```python
"""Working Memory — 当前会话的短期上下文。

管理:
- 当前计划（plan stack）
- ReAct 轨迹缓冲（最近的 thought-action-observation 三元组）
- 当前目标与已完成子目标
- 临时变量（工具输出中提取的关键值）
"""

@dataclass
class WorkingMemory:
    trace_id: str
    goal: str                           # 当前最高目标
    plan_stack: list[dict] = field(default_factory=list)  # 计划栈
    react_trajectory: list[dict] = field(default_factory=list)  # ReAct 轨迹
    variables: dict[str, Any] = field(default_factory=dict)  # 临时变量
    completed_goals: list[str] = field(default_factory=list)
    max_trajectory: int = 10
    
    def add_react_step(self, thought: str, action: str, observation: str) -> None:
        self.react_trajectory.append({
            "thought": thought,
            "action": action,
            "observation": observation,
        })
        if len(self.react_trajectory) > self.max_trajectory:
            # 压缩: 丢弃最旧的，保留最近的
            self.react_trajectory.pop(0)
    
    def set_variable(self, key: str, value: Any) -> None:
        self.variables[key] = value
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)
```

### 6.6 `memory/summarizer.py` — 记忆压缩与检索

```python
"""Memory Summarizer — 对话历史压缩 & 相关记忆检索。

将长历史压缩为结构化摘要供 LLM 使用。
"""

class MemorySummarizer:
    def __init__(self, llm: Optional[LLMAdapter] = None):
        self.llm = llm  # 可选: 使用 LLM 做智能摘要
    
    def summarize_trajectory(self, trajectory: list[dict]) -> str:
        """将 ReAct 轨迹压缩为单行摘要"""
        if not trajectory:
            return ""
        
        steps = len(trajectory)
        success = sum(1 for t in trajectory if t.get("observation", {}).get("status") == "success")
        failures = steps - success
        
        failed_actions = set()
        for t in trajectory:
            obs = t.get("observation", {})
            if obs.get("status") == "failure":
                ec = obs.get("error", {}).get("code", "UNKNOWN")
                failed_actions.add(f"{t.get('action', '?')}[{ec}]")
        
        parts = [f"ReAct({steps}步, {success}成功/{failures}失败)"]
        if failed_actions:
            parts.append(f"失败: {', '.join(failed_actions)}")
        
        return " | ".join(parts)
    
    def build_memory_prompt(
        self, 
        episodic: list[Episode], 
        semantic: Optional[KnowledgeEntry],
        working: WorkingMemory,
    ) -> str:
        """构建记忆增强提示"""
        lines = ["[Memory Context]"]
        
        if semantic:
            lines.append(f"Known pattern: {semantic.pattern}")
            lines.append(f"Suggested: {semantic.solution}")
        
        if episodic:
            lines.append("Similar past episodes:")
            for ep in episodic[-3:]:
                lines.append(f"  [{ep.status}] {ep.action}: {ep.summary}")
        
        if working.react_trajectory:
            lines.append("Current trajectory:")
            lines.append(self.summarize_trajectory(working.react_trajectory[-3:]))
        
        return "\n".join(lines)
```

### 6.7 `llm/context_window.py` — 重构为分层上下文管理

```python
"""分层上下文管理。

将 LLM 上下文分为四个层次:
1. System Layer   — 系统提示 + 工具描述（固定，最长）
2. Memory Layer   — 记忆增强（情景+语义+工作记忆摘要）
3. Trajectory Layer — ReAct 轨迹（最近 N 步，动态窗口）
4. Current Step   — 当前要处理的问题（最短，最重要）
"""

from dataclasses import dataclass

@dataclass
class LayeredContext:
    system: str          # 系统提示 + 工具描述
    memory: str          # 记忆摘要
    trajectory: str      # 轨迹摘要
    current: str         # 当前步骤

MAX_TOKENS_BY_LAYER = {
    "system": 16000,     # 系统提示（含工具描述）
    "memory": 4000,      # 记忆增强
    "trajectory": 8000,  # ReAct 轨迹
    "current": 4000,     # 当前步骤
}

class ContextManager:
    def __init__(self, tokenizer=None):
        self.tokenizer = tokenizer  # 可选: tiktoken
        self.max_total_tokens = 32000
    
    async def build_messages(
        self,
        layered: LayeredContext,
        summaries: list[str],
        llm_response_format: str = "openai",
    ) -> list[dict]:
        """构建 LLM 消息列表"""
        # System prompt (不受窗口滑动影响)
        messages = [{"role": "system", "content": layered.system}]
        
        # Memory layer (摘要形式注入)
        if layered.memory:
            messages.append({
                "role": "system",
                "content": f"[Memory Context]\n{layered.memory}",
            })
        
        # Trajectory layer
        if layered.trajectory:
            messages.append({
                "role": "system",
                "content": f"[Execution Trajectory]\n{layered.trajectory}",
            })
        
        # Current user request
        messages.append({"role": "user", "content": layered.current})
        
        # Token 预算检查（如已接入 tokenizer）
        if self.tokenizer:
            total = sum(self.tokenizer(len(m["content"])) for m in messages)
            if total > self.max_total_tokens:
                # 裁剪 trajectory 层
                messages = self._trim_to_budget(messages, total)
        
        return messages
```

### 6.8 `agents/code_generator.py` — LLM 驱动的工具代码生成

```python
"""Code Generator — LLM 驱动的运维工具代码生成器。

当现有工具库无法满足任务需求时，CodeGenerator 负责:
1. 分析任务目标，确定需要什么工具
2. 调用 LLM 生成工具代码（bash/python3/node）
3. 安全预检（静态分析）
4. 通过 Master 部署到 Worker

代码生成安全原则:
- 只生成非交互式脚本（参数通过环境变量传入）
- 必须输出有效 JSON 到 stdout
- 禁止使用网络下载或执行外部代码
- 禁止访问敏感路径
"""

from dataclasses import dataclass, field
from typing import Optional


TOOL_GENERATION_PROMPT = """You are gAIOps Code Generator. Generate a {language} script that:

## Requirements
- Task: {task_description}
- Input: Parameters via TOOL_PARAMS environment variable (JSON string)
- Output: Valid JSON to stdout (ONLY JSON, no extra text)
- Timeout: {timeout} seconds

## Constraints
- No interactive input
- No network downloads or external code execution
- No access to /etc/shadow, /etc/passwd, /root/.ssh/
- No fork bombs or infinite loops
- No system modification outside {allowed_paths}
- Handle errors gracefully (output JSON with error field)

## Output Format
Success: {{"status": "ok", "data": {{...key values...}}}}
Error:   {{"status": "error", "error": "description"}}

Generate ONLY the script code, no explanations."""


@dataclass
class GeneratedTool:
    action: str
    language: str          # bash | python3 | node
    code: str
    description: str
    risk_level: str        # readonly | write | dangerous
    timeout: int
    params_schema: dict = field(default_factory=dict)


class CodeGenerator:
    def __init__(self, llm: LLMAdapter, max_retries: int = 2):
        self.llm = llm
        self.max_retries = max_retries
    
    async def generate(
        self,
        task: str,
        language: str = "bash",
        timeout: int = 30,
    ) -> GeneratedTool:
        """Generate a tool script for the given task."""
        prompt = TOOL_GENERATION_PROMPT.format(
            language=language,
            task_description=task,
            timeout=timeout,
            allowed_paths="/tmp, /var/tmp",
        )
        
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30.0,
                )
                
                code = self._extract_code(response, language)
                if not code:
                    continue
                
                # Auto-generate action name from task
                action = self._generate_action_name(task)
                
                # Estimate risk level
                risk = self._estimate_risk(code, language)
                
                return GeneratedTool(
                    action=action,
                    language=language,
                    code=code,
                    description=task[:200],
                    risk_level=risk,
                    timeout=timeout,
                )
                
            except Exception as e:
                if attempt < self.max_retries:
                    continue
                raise CodeGenerationError(f"Failed to generate code after {self.max_retries} retries: {e}")
        
        raise CodeGenerationError("Failed to generate valid tool code")
    
    def _extract_code(self, llm_response: dict, language: str) -> Optional[str]:
        """从 LLM 响应中提取代码块"""
        content = (llm_response.get("message", {}) or {}).get("content", "")
        if not content:
            return None
        
        # 尝试提取 ``` 代码块
        import re
        pattern = rf"```(?:{language}|bash|python|sh)?\n(.*?)```"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 如果没有代码块标记但内容看起来像代码
        if self._looks_like_code(content, language):
            return content.strip()
        
        return None
    
    def _estimate_risk(self, code: str, language: str) -> str:
        """估算代码的风险等级"""
        dangerous_patterns = [
            r"rm\s+(-rf?)\s+/", r"mkfs\.", r"dd\s+if=",
            r"/etc/(shadow|passwd|sudoers)", r"chmod\s+777",
            r"kill\s+-9", r"reboot", r"shutdown",
        ]
        write_patterns = [
            r">\s*/", r"mv\s+", r"cp\s+", r"chown", r"chmod",
            r"systemctl\s+(restart|stop|start)",
            r"docker\s+(rm|kill|stop)",
        ]
        
        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, code):
                return "dangerous"
        for pattern in write_patterns:
            if re.search(pattern, code):
                return "write"
        return "readonly"
    
    def _generate_action_name(self, task: str) -> str:
        """根据任务描述生成 action 名称"""
        import re
        # 提取关键动宾短语
        task_lower = task.lower()
        
        mappings = [
            (r"(check|get|show|list)\s+(disk|storage)", "custom.disk_check"),
            (r"(check|get)\s+(memory|mem|cpu|load)", "custom.system_check"),
            (r"(restart|stop|start)\s+(service|nginx|app)", "custom.service_op"),
            (r"(deploy|install|setup)\s+", "custom.deploy"),
            (r"(backup|archive|compress)", "custom.backup"),
            (r"(clean|purge|remove)\s+(temp|log|old)", "custom.cleanup"),
        ]
        
        for pattern, action in mappings:
            if re.search(pattern, task_lower):
                return action
        
        # Fallback: 生成基于时间的唯一名称
        import time, hashlib
        hash_suffix = hashlib.md5(task.encode())[:8]
        return f"custom.gen_{hash_suffix}"
```

### 6.9 `core/state.py` — 状态结构扩展

```python
@dataclass
class GraphState:
    # Tracing (不变)
    trace_id: str = ""
    
    # Plan execution (扩展)
    plan: list[dict] = field(default_factory=list)
    current_step: int = 0
    current_action: str = ""
    current_step_dir: str = "advance"  # "advance" | "retry" | "backtrack" | "replan"
    
    # ReAct loop (新增)
    react_trajectory: list[dict] = field(default_factory=list)
    react_step_count: int = 0
    max_react_steps: int = 3
    
    # Execution results (增强)
    last_action: str = ""
    last_status: str = ""
    last_error: str = ""
    last_data: dict = field(default_factory=dict)
    last_observation: str = ""
    
    # Memory (新增)
    memory_context: str = ""
    relevant_episodes: list = field(default_factory=list)
    working: Optional['WorkingMemory'] = None  # lazy init
    
    # Summaries (不变)
    summaries: list[str] = field(default_factory=list)
    
    # Flow control (不变)
    needs_human: bool = False
    cycle_detected: bool = False
    conclusion: str = ""
    
    # Truncation (不变)
    truncated_responses: list[bool] = field(default_factory=list)
    
    # Dynamic tool tracking (新增)
    deployed_tools: set[str] = field(default_factory=set)
    deploy_attempts: int = 0
    
    def to_dict(self) -> dict:
        """序列化为兼容旧格式的 dict"""
        return {
            "trace_id": self.trace_id,
            "conclusion": self.conclusion,
            "summaries": list(self.summaries),
            "needs_human": self.needs_human,
            "cycle_detected": self.cycle_detected,
            "last_action": self.last_action,
            "last_status": self.last_status,
            "last_data": self.last_data,
            "truncated": len(self.truncated_responses) > 0,
            # 新增字段（旧消费者忽略）
            "react_steps": self.react_step_count,
            "deployed_tools": list(self.deployed_tools),
        }
```

---

## 7. Phase 5 — 工具矩阵扩展

> **目标**: 基于当前工具注册表，补充运维场景所需的工具
> **周期**: 1.5 周
> **可并行**: 与 Phase 3/4 并行执行
> **兼容性**: 完全向后兼容（新增工具不影响现有接口）

### 7.1 工具扩展矩阵

| 类别 | 现有工具 | 新增工具 | 运维场景 |
|------|---------|---------|---------|
| **网络** | `ping.icmp`, `dns.lookup`, `network.connections`, `http.get`, `http.post` | `traceroute`, `ssl.cert_check`, `port.scan`, `bandwidth.test` | 网络故障排查、证书到期监控 |
| **磁盘** | `disk.usage` | `disk.io_stats`, `disk.inode_usage`, `disk.smart_info`, `disk.find_large_files` | 磁盘性能分析、大文件清理 |
| **进程** | `process.list`, `process.kill` | `process.monitor`, `process.thread_dump`, `process.open_files` | 进程性能诊断、资源泄露排查 |
| **服务** | `service.status`, `service.restart`, `service.start` | `service.logs`, `service.dependency`, `service.config_check` | 服务故障排查、配置验证 |
| **系统** | `system.info`, `cpu.usage`, `memory.usage` | `system.uptime`, `system.kernel_params`, `system.firewall_rules`, `system.scheduled_tasks` | 系统巡检、安全审计 |
| **容器** | `container.list`, `container.logs` | `container.stats`, `container.inspect`, `container.network`, `container.cleanup` | 容器运维、资源监控 |
| **日志** | `log.tail` | `log.search`, `log.watch`, `log.rotate`, `log.compress` | 日志分析、日志轮转 |
| **文件** | `file.read`, `file.write`, `file.list` | `file.search(grep)`, `file.diff`, `file.permissions`, `file.hash`, `file.sync` | 文件运维、配置比对 |
| **安全** | — | `security.check_ssh`, `security.check_failed_logins`, `security.port_listening`, `security.audit_logs` | 安全审计 |
| **数据库** | — | `db.query(mysql/pg)`, `db.status`, `db.backup`, `db.slow_queries` | 数据库运维 |

### 7.2 单工具实现模板

```go
// worker/internal/tools/traceroute.go
package tools

import (
    "context"
    "fmt"
    "os/exec"
    "strings"
    "time"

    "github.com/gaiops/worker/internal/registry"
)

func init() {
    registry.Global.Register(registry.Tool{
        Action:       "traceroute",
        Timeout:      30 * time.Second,
        IsIdempotent: true,
        RiskLevel:    "readonly",
        Execute:      executeTraceroute,
    })
}

func executeTraceroute(ctx context.Context, params map[string]interface{}) (map[string]interface{}, error) {
    target, _ := params["target"].(string)
    if target == "" {
        return nil, fmt.Errorf("target is required")
    }

    cmd := exec.CommandContext(ctx, "traceroute", "-n", "-m", "15", target)
    out, err := cmd.Output()
    if err != nil {
        return nil, fmt.Errorf("traceroute failed: %w", err)
    }

    lines := strings.Split(strings.TrimSpace(string(out)), "\n")
    hops := make([]map[string]interface{}, 0)
    for _, line := range lines {
        fields := strings.Fields(line)
        if len(fields) >= 2 {
            hop := map[string]interface{}{
                "hop": fields[0],
                "ip":  strings.TrimRight(fields[1], ":"),
            }
            hops = append(hops, hop)
        }
    }

    return map[string]interface{}{
        "target": target,
        "hops":   hops,
        "hop_count": len(hops),
    }, nil
}
```

### 7.3 工具注册表同步

Brain 侧每次新增工具后，同步更新：

```python
# brain/tools/tool_registry.py — 增量注册
REGISTRY["traceroute"] = {
    "description": "Perform traceroute to a target host",
    "required_params": ["target"],
    "risk_level": "readonly",
    "params": {
        "target": {"type": "string", "description": "Target hostname or IP"},
        "max_hops": {"type": "integer", "description": "Max hops (default 15)"},
    },
}
AVAILABLE_ACTIONS = list(REGISTRY.keys())
```

```python
# brain/llm/schemas.py — 增量注册 LLM schema
TRACEROUTE = tool_to_ollama_schema(
    "traceroute",
    "Traceroute to a target host showing network path",
    {
        "target": {"type": "string", "description": "Target hostname or IP", "required": True},
        "max_hops": {"type": "integer", "description": "Max hops (default 15)"},
    },
)
ALL_TOOLS.append(TRACEROUTE)
TOOL_NAMES = [t["function"]["name"] for t in ALL_TOOLS]
```

---

## 8. Phase 6 — E2E 验证与生产加固

> **目标**: 集成测试、性能压测、文档完善、部署配置
> **周期**: 1.5 周

### 8.1 测试矩阵

| 测试类别 | 覆盖场景 | 工具 |
|---------|---------|------|
| **协议兼容性** | v1.0 ↔ v1.1 互操作性、版本协商降级 | Go + TS 单元测试 |
| **Worker 动态工具** | 代码编译→部署→执行→卸载完整生命周期 | Go 测试 (60+ 项) |
| **Worker 沙箱** | 语法错误、超时、内存超限、危险模式拦截 | Go 测试 (20+ 项) |
| **Master 部署编排** | 工具部署、分片传输、超时重试、失败回退 | Jest (30+ 项) |
| **Master 工具目录** | 注册/查询/卸载/分布式状态一致性 | Jest (15+ 项) |
| **Brain ReAct 循环** | 正常执行、工具缺失→部署→执行、自循环熔断 | Pytest (40+ 项) |
| **Brain 记忆系统** | 情景记忆存取、语义记忆检索、记忆增强提示 | Pytest (20+ 项) |
| **Brain 代码生成** | LLM 响应解析、安全预检、多语言代码提取 | Pytest (15+ 项) |
| **E2E** | 全链路: Brain→Master→Worker→结果回流 | Pytest (30+ 项) |
| **故障注入** | 网络分区、Worker 崩溃、Master 重启、代码部署失败 | Pytest (20+ 项) |

### 8.2 核心 E2E 场景

```python
# e2e/test_dynamic_tool_lifecycle.py

class TestDynamicToolLifecycle:
    """动态工具全生命周期 E2E 测试"""
    
    async def test_deploy_and_execute_bash_tool(self, cluster):
        """部署 bash 工具 → 执行 → 验证结果"""
        tool_code = 'printf \'{"status":"ok","data":{"message":"hello"}}\\n\''
        
        # 1. Brain 生成工具代码
        tool = await cluster.brain.code_generator.generate(
            task="say hello", language="bash"
        )
        assert tool.language == "bash"
        
        # 2. 通过 Master 部署到 Worker
        result = await cluster.master.tool_deployer.deploy(
            action=tool.action,
            code_body=tool.code,
            runtime_hints={"interpreter": "bash"},
            target_worker_id=cluster.worker.id,
        )
        assert result.status == "success"
        
        # 3. 验证动态工具已注册
        tools = await cluster.brain.master.list_tools()
        assert any(t["action"] == tool.action for t in tools)
        
        # 4. 执行动态工具
        exec_result = await cluster.brain.master.execute(
            action=tool.action, params={}
        )
        assert exec_result["status"] == "success"
        assert exec_result["data"]["message"] == "hello"
        
        # 5. 卸载工具
        undeploy = await cluster.master.tool_deployer.undeploy(tool.action)
        assert undeploy is True
    
    async def test_react_loop_deploys_missing_tool(self, cluster):
        """ReAct 循环在工具缺失时自动部署"""
        context = "Check the system's current memory usage and report it"
        
        trace_id = await cluster.brain.engine.start_session(context)
        result = await cluster.brain.engine.wait_for_completion(trace_id)
        
        # 验证: 系统通过 ReAct 循环部署了 memory.usage（如果没有预装）
        assert result["status"] == "completed"
        # 验证结论中包含内存信息
        assert "memory" in result["conclusion"].lower() or "mem" in result["conclusion"].lower()
```

### 8.3 生产加固清单

| 项目 | 优先级 | 说明 |
|------|--------|------|
| **Docker Compose** | 🔴 高 | 补全 `docker-compose.yaml`，覆盖 Brain+Master+Worker 三容器 |
| **Dockerfile** | 🔴 高 | Worker 和 Master 的 Dockerfile（确认存在或补全） |
| **Makefile** | 🔴 高 | 补全 Makefile（参考 README 中已有的 make 命令） |
| **GitHub Actions CI** | 🟡 中 | 配置 CI 流水线（lint + test + build） |
| **资源限制配置** | 🟡 中 | 动态工具引擎的内存/CPU/超时硬限制可配置 |
| **错误日志增强** | 🟡 中 | 动态工具的全链路错误日志（含 deploy_id 关联） |
| **性能基线** | 🟢 低 | 动态工具启动延迟、部署吞吐量、最大并发动态工具数 |

---

## 9. Breaking Changes 管控清单

以下为整个计划中所有 P0/P1 破坏性变更及其具体管控措施：

| ID | 变更 | 等级 | 管控措施 | 验证方式 |
|----|------|------|---------|---------|
| BC-01 | Envelope `msg_type` 枚举扩展（v1.0→v1.1） | P0 | 版本协商 + 旧节点收到未知 msg_type 走校验错误但不崩溃 | `test_proto_backward_compat` 测试 |
| BC-02 | `worker.yaml` 新增 `dynamic_tools` 配置节 | P0 | YAML 解析库跳过未知字段，新节全为 optional | Go 配置加载测试（旧配置） |
| BC-03 | `registry.Tool` 新增 `Source` 等字段 | P1 | Go struct 零值安全（空字符串 = "builtin"），RegisterDynamic 兼容旧注册 | 现有 70+ 测试不失效 |
| BC-04 | Worker 能力声明新增 `supportsDynamicTools` | P1 | 旧 Worker 不声明此字段 → Master 视为不支持，不向其分发部署 | 路由逻辑兼容测试 |
| BC-05 | Master REST API 新增端点 | P0 | 纯新增，不修改旧端点响应体 | API 路由不冲突测试 |
| BC-06 | `completed_sessions` 响应体新增字段 | P1 | 所有新增字段为 optional，旧消费者自动忽略 | 旧 CLI 解析测试 |
| BC-07 | GraphState 新增 `react_trajectory` 等字段 | P1 | Python dataclass `field(default_factory=...)` 零值安全 | state 序列化/反序列化测试 |
| BC-08 | 错误码编目扩展 | P1 | 旧 Brain 不认识新码 → `error_classifier` 保守 fallback 到 `replan` | 分类器 fallback 测试 |

---

## 10. 风险评估与缓解策略

### 10.1 关键风险矩阵

| 风险 | 概率 | 影响 | 等级 | 缓解措施 |
|------|------|------|------|---------|
| **动态工具执行导致 Worker 崩溃** | 中 | 高 | 🔴 高 | 沙箱隔离 + 进程池隔离 + panic recover（已有）+ 自动重启 |
| **LLM 生成的代码包含安全隐患** | 中 | 高 | 🔴 高 | 三层安全审查（Brain 侧 scanner + Master code-approver + Worker 运行时 sandbox） |
| **ReAct 循环 LLM Token 消耗爆炸** | 高 | 中 | 🟡 中 | ContextManager 严格预算管理 + 轨迹自动压缩 + max_react_steps 硬限制 |
| **动态工具与编译工具命名冲突** | 低 | 中 | 🟡 中 | Registry 注册时区分命名空间（builtin: / dynamic:），冲突时拒绝部署 |
| **Master 部署编排成为性能瓶颈** | 低 | 中 | 🟡 中 | 工具部署是低频操作，非关键路径；大代码分片并行投递 |
| **滚动升级期间新旧 Worker 混合** | 高 | 中 | 🟡 中 | Master 通过能力声明识别 Worker 版本，仅向支持动态工具的 Worker 分发部署 |

### 10.2 回退策略

```
如果动态工具引擎在生产环境导致问题:
1. 设置 worker.yaml 中 dynamic_tools.enabled = false → 完全禁用
2. 回退到 v1.0 协议（仅使用编译工具）
3. Brain 侧检测到无 Worker 支持动态工具 → 自动降级到旧 plan-and-execute 模式
4. 原有功能不受任何影响
```

---

## 附：PRD 路线图对照

| Phase | v1.x 状态 | v2.0 变更 | 工作量占比 |
|-------|-----------|-----------|-----------|
| **Worker** | 编译工具 + 基础安全 | + 动态工具引擎 + 运行时池 + 沙箱 | **~25%** |
| **Master** | WS 服务 + REST API + 队列 + 路由 | + 工具部署编排 + 工具目录 + 代码审批 | **~20%** |
| **Brain** | 线性 Plan-and-Execute + 基础消毒 | + Plan-ReAct-Reflect + 记忆系统 + 代码生成 | **~35%** |
| **协议** | Envelope v1 + 5 msg_type | v1.1 + 3 新 msg_type | **~5%** |
| **测试** | 70+75+80 单元 + E2E | + 200+ 新增测试项 | **~15%** |

---

> **本文档制定人**: 首席架构师
> **状态**: 已就绪，等待实施指令
> **建议**: 建议按 Phase 1 → 2 → 3 → 4 → 5 → 6 顺序推进，其中 Phase 5（工具扩展）可与 Phase 3/4 并行执行以减少总工期约 1 周
