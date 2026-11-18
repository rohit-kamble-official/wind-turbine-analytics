# Starts the React dashboard on http://localhost:5173 (proxies /api to port 8000)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "frontend")
npm run dev
