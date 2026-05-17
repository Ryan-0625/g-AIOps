# gAIOps CLI Full Demo Script (PowerShell)
# Fully automated, zero manual input required
# Usage: .\demo-full.ps1
# Prerequisites: docker compose up -d master worker brain

$env:CLUSTER_TOKEN = "dev-token-change"
$CLI = "python cli/gaiops"

function Section($title) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Start-Sleep -Milliseconds 600
}

function Comment($text) {
    Write-Host ""
    Write-Host "  >> $text" -ForegroundColor DarkYellow
    Start-Sleep -Milliseconds 400
}

# ── Demo Start ──────────────────────────────────────────────────────────────

Clear-Host

Section "gAIOps CLI Full Demo"
Write-Host "  LLM-powered distributed ops decision system" -ForegroundColor Gray
Start-Sleep -Seconds 1

# ── Part 1: Cluster Health ──────────────────────────────────────────────────

Section "Part 1: Cluster Health"

Comment "1.1 Health Check"
Invoke-Expression "$CLI health"
Start-Sleep -Seconds 2

Comment "1.2 Worker Nodes"
Invoke-Expression "$CLI worker list"
Start-Sleep -Seconds 2

# ── Part 2: System Inspection ───────────────────────────────────────────────

Section "Part 2: System Inspection"

Comment "2.1 System Info"
Invoke-Expression "$CLI execute system.info --wait"
Start-Sleep -Seconds 3

Comment "2.2 CPU Usage"
Invoke-Expression "$CLI execute cpu.usage --wait"
Start-Sleep -Seconds 3

Comment "2.3 Memory Usage"
Invoke-Expression "$CLI execute memory.usage --wait"
Start-Sleep -Seconds 3

Comment "2.4 Disk Usage"
Invoke-Expression "$CLI execute disk.usage --wait"
Start-Sleep -Seconds 3

# ── Part 3: Network Diagnosis ───────────────────────────────────────────────

Section "Part 3: Network Diagnosis"

Comment "3.1 DNS Lookup"
Invoke-Expression "$CLI execute dns.lookup hostname=baidu.com --wait"
Start-Sleep -Seconds 3

Comment "3.2 HTTP Check"
Invoke-Expression "$CLI execute http.get url=https://httpbin.org/get --wait"
Start-Sleep -Seconds 5

# ── Part 4: AI Chat ─────────────────────────────────────────────────────────

Section "Part 4: AI Natural Language Interaction"

Comment "4.1 Ask: system status"
Write-Host "  User: 'check system status'" -ForegroundColor White
$chatFile1 = [System.IO.Path]::GetTempFileName()
Set-Content -Path $chatFile1 -Value "check system status`n/exit" -NoNewline
cmd /c "python cli/gaiops chat < ""$chatFile1"""
Remove-Item $chatFile1
Start-Sleep -Seconds 2

Comment "4.2 Ask: CPU load"
Write-Host "  User: 'how is CPU load'" -ForegroundColor White
$chatFile2 = [System.IO.Path]::GetTempFileName()
Set-Content -Path $chatFile2 -Value "how is CPU load`n/exit" -NoNewline
cmd /c "python cli/gaiops chat < ""$chatFile2"""
Remove-Item $chatFile2
Start-Sleep -Seconds 2

Comment "4.3 Ask: check baidu"
Write-Host "  User: 'is baidu.com accessible'" -ForegroundColor White
$chatFile3 = [System.IO.Path]::GetTempFileName()
Set-Content -Path $chatFile3 -Value "is baidu.com accessible`n/exit" -NoNewline
cmd /c "python cli/gaiops chat < ""$chatFile3"""
Remove-Item $chatFile3
Start-Sleep -Seconds 3

# ── Part 5: Trace ───────────────────────────────────────────────────────────

Section "Part 5: Trace Tracking"

Comment "5.1 Recent Traces"
Invoke-Expression "$CLI trace list"
Start-Sleep -Seconds 2

# ── Summary ─────────────────────────────────────────────────────────────────

Section "Demo Complete"
Write-Host ""
Write-Host "  Covered Features:" -ForegroundColor White
Write-Host "    [OK] Cluster Health Check"
Write-Host "    [OK] Worker Node Management"
Write-Host "    [OK] System Inspection (info, cpu, memory, disk)"
Write-Host "    [OK] Network Diagnosis (dns, http)"
Write-Host "    [OK] AI Natural Language Chat"
Write-Host "    [OK] Trace Tracking"
Write-Host ""
Write-Host "  Interactive modes for manual exploration:" -ForegroundColor Gray
Write-Host "    python cli/gaiops chat"
Write-Host "    python cli/gaiops shell"
Write-Host ""
