# gAIOps CLI Demo Script (PowerShell)
# Usage: .\demo.ps1
# Prerequisites: docker compose up -d master worker brain

$env:CLUSTER_TOKEN = "dev-token-change"
$CLI = "python cli/gaiops"
$Delay = 2

function Section($title) {
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "==============================================================" -ForegroundColor Cyan
    Start-Sleep -Milliseconds 500
}

function Comment($text) {
    Write-Host ""
    Write-Host "  [NOTE] $text" -ForegroundColor Yellow
    Start-Sleep -Milliseconds 300
}

# ── Demo Start ───────────────────────────────────────────────────────────────

Clear-Host

Section "gAIOps CLI Demo"
Start-Sleep -Seconds 1

# 1. Logo
Section "1. Logo & Help"
Comment "Show gaiops logo and available commands"
Start-Sleep -Seconds 1
Invoke-Expression $CLI
Start-Sleep -Seconds $Delay

# 2. Health
Section "2. Health Check"
Comment "Check cluster health status"
Invoke-Expression "$CLI health"
Start-Sleep -Seconds $Delay

# 3. Workers
Section "3. Worker Nodes"
Comment "List connected worker nodes"
Invoke-Expression "$CLI worker list"
Start-Sleep -Seconds $Delay

# 4. System Inspection
Section "4. System Inspection"
Comment "System overview"
Invoke-Expression "$CLI execute system.info --wait"
Start-Sleep -Seconds $Delay

Comment "CPU usage"
Invoke-Expression "$CLI execute cpu.usage --wait"
Start-Sleep -Seconds $Delay

Comment "Memory usage"
Invoke-Expression "$CLI execute memory.usage --wait"
Start-Sleep -Seconds $Delay

Comment "Disk usage"
Invoke-Expression "$CLI execute disk.usage --wait"
Start-Sleep -Seconds $Delay

# 5. Network
Section "5. Network Diagnosis"
Comment "DNS lookup test"
Invoke-Expression "$CLI execute dns.lookup hostname=baidu.com --wait"
Start-Sleep -Seconds $Delay

Comment "HTTP connectivity test"
Invoke-Expression "$CLI execute http.get url=https://httpbin.org/get --wait"
Start-Sleep -Seconds $Delay

# 6. Status Dashboard
Section "6. Status Dashboard"
Comment "Aggregated cluster status"
Invoke-Expression "$CLI status"
Start-Sleep -Seconds $Delay

# 7. Trace
Section "7. Trace Tracking"
Comment "Recent operation traces"
Invoke-Expression "$CLI trace list"
Start-Sleep -Seconds $Delay

# 8. Config
Section "8. Configuration"
Comment "Show current config with masked token"
Invoke-Expression "$CLI config show"
Start-Sleep -Seconds $Delay

# ── End ─────────────────────────────────────────────────────────────────────

Section "Demo Complete"
Write-Host ""
Write-Host "Covered features:"
Write-Host "  - health, worker list, execute"
Write-Host "  - status, trace, config"
Write-Host "  - system inspection, network diagnosis"
Write-Host ""
Write-Host "For interactive modes (chat/shell), run manually:"
Write-Host "  python cli/gaiops chat"
Write-Host "  python cli/gaiops shell"
Write-Host ""
