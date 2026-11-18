"""FastAPI application entry point.

Run (from backend/):  uvicorn app.main:app --reload --port 8000
Docs:                 http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import routes_core, routes_metrics, routes_operations, routes_reports
from app.core.config import settings
from app.database.db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("wta")

DESCRIPTION = """
REST API of the **Wind Turbine Performance Monitoring & Analytics Dashboard** (portfolio project).

All data served by this API is **SIMULATED** SCADA data generated for demonstration. It is not
real operational data and this is not an official product of any turbine manufacturer.

Common filters: `start_date`, `end_date` (inclusive, YYYY-MM-DD) and `turbine_id` (e.g. `WTG01`).
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    init_db()  # creates tables if missing; never drops data
    yield


app = FastAPI(title="Wind Turbine Performance Analytics API", version=routes_core.VERSION,
              description=DESCRIPTION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])
app.add_middleware(GZipMiddleware, minimum_size=2000)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={"detail": "Internal server error - see server log"})


for r in (routes_core.router, routes_metrics.router, routes_operations.router, routes_reports.router):
    app.include_router(r)


# Single-service deployment: if the React build exists, serve it from the same
# origin (no CORS needed). Unknown non-API paths fall back to index.html so
# client-side routes like /power-curve work on refresh.
STATIC_DIR = settings.static_dir
if STATIC_DIR and (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"name": app.title, "docs": "/docs", "health": "/api/health", "data": "SIMULATED"}
