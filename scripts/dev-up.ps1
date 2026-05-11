#Requires -Version 7.0
<#
.SYNOPSIS
  Starts the gAIOps development environment: Worker, Master, and Brain.
  Run from the repository root.
.DESCRIPTION
  Launches all three layers in separate PowerShell windows with hot-reload
  where available. Uses the config files from the project root.
.PARAMETER ConfigDir
  Path to directory containing worker.yaml, master.yaml, brain.yaml.
  Defaults to the current directory.
.EXAMPLE
  .\scripts\dev-up.ps1
  .\scripts\dev-up.ps1 -ConfigDir C:\gaiops\config
#>

param(
  [string]$ConfigDir = (Get-Location).Path
)

$Root = (Get-Location).Path
$LogDir = "$Root\.dev-logs"

# Ensure log directory exists
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

function Start-DevProcess {
  param(
    [string]$Name,
    [string]$WorkDir,
    [string]$Command,
    [string]$Args
  )
  $logFile = "$LogDir\$Name.log"
  $title = "gAIOps - $Name"
  $cmd = "cd '$WorkDir'; $Command $Args *>'$logFile' 2>&1; pause"
  Write-Host "[+] Starting $Name..." -ForegroundColor Green
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}

# ── Validate prerequisites ──────────────────────────────────────────────────
function Test-Command {
  param([string]$Exe, [string]$Label)
  $found = Get-Command $Exe -ErrorAction SilentlyContinue
  if (-not $found) {
    Write-Warning "$Label not found in PATH — install it first"
    return $false
  }
  Write-Host "  [✓] $Label" -ForegroundColor Gray
  return $true
}

Write-Host "`n=== gAIOps Development Environment ===`n" -ForegroundColor Cyan

$goOk = Test-Command go "Go"
$nodeOk = Test-Command node "Node.js"
$pythonOk = Test-Command python "Python"

if (-not ($goOk -or $nodeOk -or $pythonOk)) {
  Write-Error "No runtimes found — install Go, Node.js, or Python as needed"
  exit 1
}

# ── Worker (Go) ─────────────────────────────────────────────────────────────
if ($goOk) {
  $workerCfg = Join-Path $ConfigDir "worker.yaml"
  if (-not (Test-Path $workerCfg)) {
    Write-Warning "worker.yaml not found at $workerCfg — Worker will use defaults"
  }
  Start-DevProcess -Name "Worker" -WorkDir "$Root\worker" `
    -Command "go run .\cmd\worker" `
    -Args "--config '$workerCfg'"
}
else {
  Write-Warning "Skipping Worker (Go not found)"
}

# ── Master (TypeScript/Node) ────────────────────────────────────────────────
if ($nodeOk) {
  # Install dependencies if missing.
  if (-not (Test-Path "$Root\master\node_modules")) {
    Write-Host "  [i] Installing Master dependencies..." -ForegroundColor Yellow
    Push-Location "$Root\master"
    npm install | Out-Null
    Pop-Location
  }
  Start-DevProcess -Name "Master" -WorkDir "$Root\master" `
    -Command "npx ts-node" `
    -Args "src\index.ts"
}
else {
  Write-Warning "Skipping Master (Node.js not found)"
}

# ── Brain (Python) ─────────────────────────────────────────────────────────
if ($pythonOk) {
  # Install dependencies if missing.
  $venvDir = "$Root\brain\.venv"
  if (-not (Test-Path $venvDir)) {
    Write-Host "  [i] Creating Brain virtual environment..." -ForegroundColor Yellow
    Push-Location "$Root\brain"
    python -m venv .venv | Out-Null
    .\.venv\Scripts\pip install -r requirements.txt | Out-Null
    Pop-Location
  }
  Start-DevProcess -Name "Brain" -WorkDir "$Root\brain" `
    -Command ".venv\Scripts\python" `
    -Args "main.py"
}
else {
  Write-Warning "Skipping Brain (Python not found)"
}

Write-Host "`n[+] All processes started. Logs: $LogDir" -ForegroundColor Cyan
Write-Host "[i] Close each PowerShell window to stop the corresponding service.`n"
