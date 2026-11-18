"""Shared request dependencies: validated date/turbine filters and pagination."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import repository as repo
from app.database.db import get_db


@dataclass
class Filters:
    start: date | None
    end: date | None
    turbine_id: str | None


def get_filters(
    start_date: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
    turbine_id: str | None = Query(None, description="Turbine ID, e.g. WTG01. Omit for the whole farm",
                                   pattern=r"^[A-Za-z0-9_-]{1,16}$"),
    db: Session = Depends(get_db),
) -> Filters:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date must be on or before end_date")
    if turbine_id and turbine_id not in repo.turbine_ids(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Turbine '{turbine_id}' not found")
    return Filters(start_date, end_date, turbine_id)


def get_date_range(
    start_date: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
) -> Filters:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date must be on or before end_date")
    return Filters(start_date, end_date, None)


@dataclass
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def pages(self, total: int) -> int:
        return max(1, math.ceil(total / self.page_size))


def get_pagination(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=1000)) -> Pagination:
    return Pagination(page, page_size)


def clean(v):
    """NaN/inf -> None for JSON."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if (np.isnan(f) or np.isinf(f)) else round(f, 3)
