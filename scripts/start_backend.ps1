# Starts the FastAPI backend on http://localhost:8000 (docs at /docs)
$Root = Split-Path -Parent $PSScriptRoot
& (Join-Path $Root ".venv\Scripts\python.exe") -m uvicorn app.main:app --reload --port 8000 --app-dir (Join-Path $Root "backend")
