#Requires -Version 5.0
<#
.SYNOPSIS
    gAIOps 本地多终端启动脚本 (32xxx 端口段)
.DESCRIPTION
    编译 Worker → 启动 Master → 启动 Worker → 验证全链路
    端口: Master=32080, Worker=32090, Brain=32091
#>

$ProjectRoot = "E:\VScode(study)\Project\g-AIOps"
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  gAIOps 本地多终端启动 (32xxx 端口段)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Step 0: 清理旧进程和端口
# ============================================================
Write-Host "[0/4] 清理旧进程..." -ForegroundColor Yellow
Get-Process -Name "node","gaiops-worker" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# 使用 Get-NetTCPConnection 确保端口完全释放（比 netstat 更可靠，可捕获隐藏进程）
$targetPorts = @(32080, 32090, 32091)
foreach ($port in $targetPorts) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction Stop
        foreach ($c in $conns) {
            Write-Host "  -> 端口 $port 被 PID $($c.OwningProcess) 占用，释放中..." -ForegroundColor DarkYellow
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    } catch {
        # No connections on this port - good
    }
}
Start-Sleep -Seconds 2
Write-Host "  -> 所有端口空闲" -ForegroundColor Green

# ============================================================
# Step 1: 编译 Worker
# ============================================================
Write-Host "[1/4] 编译 Worker..." -ForegroundColor Yellow
$workerDir = Join-Path $ProjectRoot "worker"
$workerExe = Join-Path $workerDir "gaiops-worker.exe"

if (Test-Path $workerExe) {
    Write-Host "  -> Worker 已存在，跳过编译" -ForegroundColor Green
} else {
    Push-Location $workerDir
    go build -o $workerExe ".\cmd\worker\" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $size = [math]::Round((Get-Item $workerExe).Length / 1KB)
        Write-Host "  -> 编译成功! ($size KB)" -ForegroundColor Green
    } else {
        Write-Host "  -> 编译失败!" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
}

# ============================================================
# Step 2: 启动 Master
# ============================================================
Write-Host "[2/4] 启动 Master (端口 32080)..." -ForegroundColor Yellow
$masterDir = Join-Path $ProjectRoot "master"
Start-Process -FilePath "powershell" -WorkingDirectory $masterDir `
    -ArgumentList @("-NoExit", "-Command", "npm run dev") -WindowStyle Normal
Start-Sleep -Seconds 8

# 验证 Master 启动
$masterReady = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:32080/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Host "  -> Master 就绪 (HTTP $($r.StatusCode))" -ForegroundColor Green
        $masterReady = $true
        break
    } catch {
        Start-Sleep -Seconds 2
        Write-Host "  -> 等待... ($($i+1)/10)" -ForegroundColor DarkGray
    }
}
if (-not $masterReady) {
    Write-Host "  -> Master 启动失败，请手动检查窗口错误" -ForegroundColor Red
    exit 1
}

# ============================================================
# Step 3: 启动 Worker
# ============================================================
Write-Host "[3/4] 启动 Worker (连接 localhost:32080)..." -ForegroundColor Yellow
$workerCfg = Join-Path $ProjectRoot "config\worker.local.yaml"
Start-Process -FilePath "powershell" -WorkingDirectory $workerDir `
    -ArgumentList @("-NoExit", "-Command", ".\gaiops-worker.exe --config `"$workerCfg`"") -WindowStyle Normal
Start-Sleep -Seconds 8

# ============================================================
# Step 4: 验证全链路
# ============================================================
Write-Host "[4/4] 验证全链路..." -ForegroundColor Yellow

$allPass = $true

try {
    # 1. 健康检查
    $r = Invoke-WebRequest -Uri "http://localhost:32080/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $health = $r.Content | ConvertFrom-Json
    $online = $health.workers.online
    Write-Host "  [健康检查] workers在线=${online}" -ForegroundColor $(if ($online -gt 0) { "Green" } else { "Red" })
    if ($online -eq 0) { $allPass = $false }

    # 2. Worker 列表
    $r = Invoke-WebRequest -Uri "http://localhost:32080/api/v1/workers" -Headers @{"Authorization"="Bearer dev-token-change"} -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $workers = $r.Content | ConvertFrom-Json
    $toolCount = $workers.workers[0].actions.Count
    Write-Host "  [Worker列表] 工具数=${toolCount}" -ForegroundColor Green

    # 3. 创建巡检
    $body = '{"name":"端口巡检","probe_type":"port.check","probe_params":{"host":"localhost","port":80},"schedule_mode":"interval","interval_seconds":60,"alert_rules":[{"metric":"reachable","operator":"==","threshold":false,"severity":"critical","message":"端口不可达"}]}'
    $r = Invoke-WebRequest -Uri "http://localhost:32080/api/v1/inspections" -Method Post -Body $body -ContentType "application/json" -Headers @{"Authorization"="Bearer dev-token-change"} -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $insp = $r.Content | ConvertFrom-Json
    Write-Host "  [创建巡检] status=$($insp.status)" -ForegroundColor Green

    # 4. 告警统计
    $r = Invoke-WebRequest -Uri "http://localhost:32080/api/v1/alerts/stats" -Headers @{"Authorization"="Bearer dev-token-change"} -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $alerts = $r.Content | ConvertFrom-Json
    Write-Host "  [告警统计] total=$($alerts.total)" -ForegroundColor Green

    # 5. 巡检列表
    $r = Invoke-WebRequest -Uri "http://localhost:32080/api/v1/inspections" -Headers @{"Authorization"="Bearer dev-token-change"} -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $list = $r.Content | ConvertFrom-Json
    Write-Host "  [巡检列表] total=$($list.total)" -ForegroundColor Green

    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    if ($allPass) {
        Write-Host "  ✅ 全链路验证通过！" -ForegroundColor Cyan
    } else {
        Write-Host "  ⚠️  部分验证未通过" -ForegroundColor Yellow
    }
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "当前运行的窗口:" -ForegroundColor White
    Write-Host "  [1] Master (:32080)" -ForegroundColor White
    Write-Host "  [2] Worker" -ForegroundColor White
    Write-Host ""
    Write-Host "测试命令:" -ForegroundColor Gray
    Write-Host '  curl.exe http://localhost:32080/health' -ForegroundColor Gray
    Write-Host '  curl.exe http://localhost:32080/api/v1/workers -H "Authorization: Bearer dev-token-change"' -ForegroundColor Gray
    Write-Host ""
    Write-Host "关闭: taskkill /f /im node.exe & taskkill /f /im gaiops-worker.exe" -ForegroundColor Yellow

} catch {
    Write-Host "  -> 验证失败: $_" -ForegroundColor Red
    $allPass = $false
}

if (-not $allPass) { exit 1 }
