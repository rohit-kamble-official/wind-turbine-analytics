"""Central configuration.

All paths are resolved relative to the project root so the application works
the same way on Windows, Linux and inside Docker. Every value can be
overridden with an environment variable (see `.env.example`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(PROJECT_ROOT / ".env")


def _path(env: str, default: Path) -> Path:
    value = os.environ.get(env)
    return Path(value).resolve() if value else default


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = field(default_factory=lambda: _path("WTA_DATA_DIR", PROJECT_ROOT / "data"))
    reports_dir: Path = field(default_factory=lambda: _path("WTA_REPORTS_DIR", PROJECT_ROOT / "reports"))
    powerbi_dir: Path = field(default_factory=lambda: _path("WTA_POWERBI_DIR", PROJECT_ROOT / "powerbi" / "datasets"))
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "WTA_DATABASE_URL", f"sqlite:///{(PROJECT_ROOT / 'data' / 'wind_turbine.db').as_posix()}"
        )
    )
    cors_origins: list[str] = field(
        default_factory=lambda: os.environ.get(
            "WTA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )
    random_seed: int = int(os.environ.get("WTA_RANDOM_SEED", "42"))
    # Public demo deployments: disable data uploads (read-only dataset)
    demo_mode: bool = os.environ.get("WTA_DEMO_MODE", "0").lower() in ("1", "true", "yes")
    # Built React app to serve from FastAPI (single-service deployment); unset = API only
    static_dir: Path | None = field(default_factory=lambda: _path("WTA_STATIC_DIR", PROJECT_ROOT / "frontend" / "dist")
                                    if os.environ.get("WTA_STATIC_DIR") else None)

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    def ensure_dirs(self) -> None:
        for p in (
            self.generated_dir,
            self.raw_dir,
            self.processed_dir,
            self.reports_dir / "excel",
            self.reports_dir / "pdf",
            self.reports_dir / "csv",
            self.powerbi_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
