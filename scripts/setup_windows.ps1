<#
.SYNOPSIS
  One-shot Windows setup: Python venv, dependencies, simulated dataset, database,
  reports, Power BI exports and frontend packages.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -SkipFrontend
#>
param(
    [switch]$SkipFrontend,
    [switch]$SkipData
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Run($exe, [string[]]$argList) {
    & $exe @argList
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $exe $($argList -join ' ')" }
}

Step "Locating Python 3.11+"
$py = $null
foreach ($cand in @(@("python"), @("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3"))) {
    try {
        $v = & $cand[0] $cand[1..($cand.Length)] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.11") { $py = $cand; break }
    } catch { }
}
if (-not $py) { throw "Python 3.11+ not found. Install it from https://www.python.org/downloads/ (tick 'Add to PATH')." }
Write-Host "Using: $($py -join ' ') (Python $v)"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Step "Creating virtual environment .venv"
    Run $py[0] ($py[1..($py.Length)] + @("-m", "venv", ".venv"))
}
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"

Step "Installing backend dependencies"
Run $VenvPy @("-m", "pip", "install", "--upgrade", "pip", "--quiet")
Run $VenvPy @("-m", "pip", "install", "-r", "backend\requirements.txt", "--quiet")

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

if (-not $SkipData) {
    Step "Generating SIMULATED SCADA dataset (data\generated)"
    Run $VenvPy @("scripts\generate_data.py")
    Step "Validating data and building SQLite database (data\wind_turbine.db)"
    Run $VenvPy @("scripts\run_pipeline.py")
    Step "Generating monthly Excel / PDF / CSV reports (reports\)"
    Run $VenvPy @("scripts\generate_reports.py")
    Step "Exporting Power BI datasets (powerbi\datasets)"
    Run $VenvPy @("scripts\export_powerbi.py")
}

if (-not $SkipFrontend) {
    Step "Installing frontend packages"
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm not found. Install Node.js 20+ from https://nodejs.org/" }
    Push-Location frontend
    try { Run "npm" @("install", "--no-fund", "--no-audit") } finally { Pop-Location }
}

Step "Setup complete"
Write-Host "Start the backend : powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1"
Write-Host "Start the frontend: powershell -ExecutionPolicy Bypass -File scripts\start_frontend.ps1"
Write-Host "Dashboard         : http://localhost:5173   API docs: http://localhost:8000/docs"
