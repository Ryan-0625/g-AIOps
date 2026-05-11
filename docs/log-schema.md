# gAIOps 结构化日志格式标准

三层统一输出 JSON 行日志到 stdout。生产环境可对接 ELK/Loki，开发期使用 `grep` + `tee`。

## 日志行格式

```json
{
  "timestamp": "2026-05-11T10:30:00.000Z",
  "level": "info | warn | error | debug",
  "module": "brain | master | worker",
  "trace_id": "uuid | \"no-trace\"",
  "msg_id": "uuid | \"\"",
  "action": "string | \"\"",
  "message": "human-readable description",
  "error_code": "string | null",
  "data": {},
  "duration_ms": 0,
  "pid": 12345
}
```

## 字段约束

| 字段 | 必填 | 约束 |
|------|------|------|
| `timestamp` | 是 | RFC3339 毫秒精度，UTC |
| `level` | 是 | debug/info/warn/error |
| `module` | 是 | brain/master/worker |
| `trace_id` | 是 | 不可为空，无法获取时填 `no-trace` 并记 warn |
| `msg_id` | 否 | 有则必填 |
| `action` | 否 | 有则必填 |
| `message` | 是 | 人类可读描述，不超过 200 字符 |
| `error_code` | 否 | 有错误时必填，取值见 error-codes.md |
| `data` | 否 | 结构化数据，不嵌入大文本 |
| `duration_ms` | 否 | 有耗时度量的操作必填 |
| `pid` | 是 | 进程 ID，用于区分多实例 |

## 分层实现

### Worker (Go)
```go
// internal/logger/logger.go
type LogEntry struct {
    Timestamp  string      `json:"timestamp"`
    Level      string      `json:"level"`
    Module     string      `json:"module"`
    TraceID    string      `json:"trace_id"`
    MsgID      string      `json:"msg_id"`
    Action     string      `json:"action"`
    Message    string      `json:"message"`
    ErrorCode  string      `json:"error_code,omitempty"`
    Data       interface{} `json:"data,omitempty"`
    DurationMs int64       `json:"duration_ms,omitempty"`
    PID        int         `json:"pid"`
}
```

### Master (TypeScript)
```typescript
// src/logger/index.ts
interface LogEntry {
  timestamp: string;
  level: "debug" | "info" | "warn" | "error";
  module: "master";
  trace_id: string;
  msg_id?: string;
  action?: string;
  message: string;
  error_code?: string;
  data?: Record<string, unknown>;
  duration_ms?: number;
  pid: number;
}
```

### Brain (Python)
```python
# brain/logger/structured_logger.py
import logging, json, time, os
from .trace_context import get_trace_id

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "level": record.levelname.lower(),
            "module": "brain",
            "trace_id": get_trace_id() or "no-trace",
            "msg_id": getattr(record, "msg_id", ""),
            "action": getattr(record, "action", ""),
            "message": record.getMessage(),
            "error_code": getattr(record, "error_code", None),
            "data": getattr(record, "data", {}),
            "duration_ms": getattr(record, "duration_ms", 0),
            "pid": os.getpid(),
        })
```

## 开发期全链路追踪

```bash
# scripts/trace.sh
# 用法: ./scripts/trace.sh <trace_id>
# 功能: 从所有日志中过滤指定 trace_id 的行，按时间排序
# 前提: 三个进程的 stdout 都重定向到统一目录或管道

#!/bin/bash
TRACE_ID=$1
if [ -z "$TRACE_ID" ]; then
    echo "Usage: $0 <trace_id>"
    exit 1
fi

# 搜索各层日志文件（路径由 dev-up.sh 创建）
for log in /tmp/gaiops/logs/*.log; do
    grep "$TRACE_ID" "$log" 2>/dev/null
done | sort
```
