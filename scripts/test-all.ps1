#Requires -Version 5.0
<#
.SYNOPSIS
    gAIOps 功能测试套件 v2 — 修正后的路由和认证
#>

$BASE = "http://localhost:32080"
$BRAIN = "http://localhost:32091"
$AUTH = @{"Authorization"="Bearer dev-token-change"}
$PASS = 0; $FAIL = 0
$traceId = [guid]::NewGuid().ToString()

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  gAIOps 功能测试套件 v2" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

function Test-Step {
    param($Name, $ScriptBlock)
    try {
        $result = & $ScriptBlock
        Write-Host "  [$($PASS+$FAIL+1)] $Name ..." -ForegroundColor Yellow -NoNewline
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Exit code: $LASTEXITCODE" }
        Write-Host " ✅" -ForegroundColor Green
        if ($result) { $result | ForEach-Object { Write-Host "       $_" -ForegroundColor Gray } }
        $global:PASS++
    } catch {
        Write-Host " ❌" -ForegroundColor Red
        Write-Host "       Error: $_" -ForegroundColor Red
        $global:FAIL++
    }
}

# ============================================================
# 1. 基础健康检查
# ============================================================
Write-Host "── 1. 基础健康检查 ──" -ForegroundColor White

Test-Step "Master 健康检查" {
    $r = Invoke-WebRequest -Uri "$BASE/health" -UseBasicParsing -TimeoutSec 5
    $h = $r.Content | ConvertFrom-Json
    "workers在线: $($h.workers.online), 运行时长: $([math]::Round($h.uptime))s"
}

Test-Step "Brain 健康检查" {
    $r = Invoke-WebRequest -Uri "$BRAIN/health" -UseBasicParsing -TimeoutSec 5
    $b = $r.Content | ConvertFrom-Json
    "状态: $($b.status), Master连接: $($b.dependencies.master), 降级: $($b.degraded)"
}

# ============================================================
# 2. Worker 能力验证 (通过 /api/v1/execute)
# ============================================================
Write-Host "── 2. Worker 能力验证 ──" -ForegroundColor White

Test-Step "Worker 列表 & 工具清单" {
    $r = Invoke-WebRequest -Uri "$BASE/api/v1/workers" -Headers $AUTH -UseBasicParsing -TimeoutSec 5
    $w = $r.Content | ConvertFrom-Json
    "Worker: $($w.workers[0].worker_id), 工具数: $($w.workers[0].actions.Count), 版本: $($w.workers[0].worker_version)"
}

function Exec-Tool($action, $params) {
    $body = @{
        action = $action
        params = $params
        trace_id = [guid]::NewGuid().ToString()
        target_worker_id = "local-worker-1"
    } | ConvertTo-Json -Compress

    $r = Invoke-WebRequest -Uri "$BASE/api/v1/execute" -Method Post -Body $body `
        -ContentType "application/json" -Headers $AUTH -UseBasicParsing -TimeoutSec 20
    $result = $r.Content | ConvertFrom-Json
    return $result
}

Test-Step "Worker 执行 system.info" {
    $resp = Exec-Tool "system.info" @{}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 ping.icmp" {
    $resp = Exec-Tool "ping.icmp" @{target="localhost"; count=2}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 cpu.usage" {
    $resp = Exec-Tool "cpu.usage" @{interval_ms=500}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 memory.usage" {
    $resp = Exec-Tool "memory.usage" @{unit="MB"}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 disk.usage" {
    $resp = Exec-Tool "disk.usage" @{path="C:\"}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 port.check (localhost:32080)" {
    $resp = Exec-Tool "port.check" @{host="localhost"; port=32080; timeout_seconds=3}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 process.list" {
    $resp = Exec-Tool "process.list" @{filter="powershell"}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

Test-Step "Worker 执行 dns.lookup" {
    $resp = Exec-Tool "dns.lookup" @{hostname="google.com"}
    "trace_id: $($resp.trace_id), status: $($resp.status)"
}

# ============================================================
# 3. 巡检系统
# ============================================================
Write-Host "── 3. 巡检系统测试 ──" -ForegroundColor White

Test-Step "创建端口巡检" {
    $body = '{"name":"Master端口监控","probe_type":"port.check","probe_params":{"host":"localhost","port":32080,"timeout_seconds":5},"schedule_mode":"interval","interval_seconds":30,"alert_rules":[{"metric":"reachable","operator":"==","threshold":false,"severity":"critical","message":"Master 端口不可达!"}]}'
    $r = Invoke-WebRequest -Uri "$BASE/api/v1/inspections" -Method Post -Body $body `
        -ContentType "application/json" -Headers $AUTH -UseBasicParsing -TimeoutSec 5
    $i = $r.Content | ConvertFrom-Json
    "inspection_id: $($i.id)"
}

Test-Step "创建HTTP健康巡检" {
    $body = '{"name":"Web服务监控","probe_type":"http.health","probe_params":{"url":"http://localhost:32080/health","timeout_seconds":5,"expected_status":200},"schedule_mode":"interval","interval_seconds":60,"alert_rules":[{"metric":"status_code","operator":"!=","threshold":200,"severity":"critical","message":"HTTP 状态异常!"}]}'
    $r = Invoke-WebRequest -Uri "$BASE/api/v1/inspections" -Method Post -Body $body `
        -ContentType "application/json" -Headers $AUTH -UseBasicParsing -TimeoutSec 5
    $i = $r.Content | ConvertFrom-Json
    "inspection_id: $($i.id)"
}

Test-Step "巡检列表" {
    $r = Invoke-WebRequest -Uri "$BASE/api/v1/inspections" -Headers $AUTH -UseBasicParsing -TimeoutSec 5
    $list = $r.Content | ConvertFrom-Json
    "巡检总数: $($list.total)"
}

Test-Step "告警统计" {
    $r = Invoke-WebRequest -Uri "$BASE/api/v1/alerts/stats" -Headers $AUTH -UseBasicParsing -TimeoutSec 5
    $a = $r.Content | ConvertFrom-Json
    "告警总数: $($a.total), 未确认: $($a.unacknowledged), 严重: $($a.critical)"
}

# ============================================================
# 4. Brain 聊天测试 (带认证)
# ============================================================
Write-Host "── 4. Brain AI 测试 (DeepSeek) ──" -ForegroundColor White

Test-Step "Brain 聊天 - 系统状态查询" {
    $body = '{"message":"检查一下系统状态","user_id":"admin","session_id":"test-001"}'
    $brainAuth = @{"Authorization"="Bearer dev-token-change"}
    $r = Invoke-WebRequest -Uri "$BRAIN/api/chat" -Method Post -Body $body `
        -ContentType "application/json" -Headers $brainAuth -UseBasicParsing -TimeoutSec 30
    $c = $r.Content | ConvertFrom-Json
    "trace_id: $($c.trace_id), status: $($c.status)"
    if ($c.conclusion) { "结论: $($c.conclusion)" }
}

# ============================================================
# 5. 异常边界测试
# ============================================================
Write-Host "── 5. 异常边界测试 ──" -ForegroundColor White

Test-Step "未授权访问 Master (401预期)" {
    try {
        $r = Invoke-WebRequest -Uri "$BASE/api/v1/workers" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        throw "应该返回401但返回了200"
    } catch {
        if ($_.Exception.Response.StatusCode -eq 401) { "正确返回 401" }
        else { throw "期望401, 实际: $($_.Exception.Response.StatusCode)" }
    }
}

Test-Step "无效路由 (404预期)" {
    try {
        $r = Invoke-WebRequest -Uri "$BASE/api/v1/nonexistent" -Headers $AUTH -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        throw "应该返回404"
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) { "正确返回 404" }
        else { throw "期望404, 实际: $($_.Exception.Response.StatusCode)" }
    }
}

Test-Step "无效巡检 (参数缺失, 400预期)" {
    $body = '{"name":"incomplete"}'
    try {
        $r = Invoke-WebRequest -Uri "$BASE/api/v1/inspections" -Method Post -Body $body `
            -ContentType "application/json" -Headers $AUTH -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        throw "应该返回4xx"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -ge 400) { "正确拒绝 (HTTP $code)" }
        else { throw "期望4xx, 实际: $code" }
    }
}

Test-Step "未授权访问 Brain (401预期)" {
    try {
        $body = '{"message":"hi","user_id":"admin","session_id":"test-002"}'
        $r = Invoke-WebRequest -Uri "$BRAIN/api/chat" -Method Post -Body $body `
            -ContentType "application/json" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        throw "应该返回401"
    } catch {
        if ($_.Exception.Response.StatusCode -eq 401) { "正确返回 401" }
        else { throw "期望401, 实际: $($_.Exception.Response.StatusCode)" }
    }
}

# ============================================================
# 6. Metrics
# ============================================================
Write-Host "── 6. Metrics ──" -ForegroundColor White

Test-Step "Prometheus Metrics" {
    $r = Invoke-WebRequest -Uri "$BASE/metrics" -UseBasicParsing -TimeoutSec 3
    $lines = ($r.Content -split "`n") | Where-Object { $_ -match "^gaiops_" }
    "指标数: $($lines.Count)"
    $lines | ForEach-Object { "  $_" }
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  测试结果: $PASS 通过, $FAIL 失败" -ForegroundColor $(if ($FAIL -eq 0) { "Green" } else { "Red" })
Write-Host "================================================" -ForegroundColor Cyan
if ($FAIL -gt 0) {
    Write-Host "  失败项可进一步排查" -ForegroundColor Yellow
}
