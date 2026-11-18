# Runs the backend test suite and the frontend type-check/build
$Root = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $Root "backend")
& (Join-Path $Root ".venv\Scripts\python.exe") -m pytest -v
$code = $LASTEXITCODE
Pop-Location
Push-Location (Join-Path $Root "frontend")
npm run build
Pop-Location
exit $code
