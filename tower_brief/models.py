"""Pydantic models for TowerBrief settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TowerBriefSettings(BaseModel):
    """User-adjustable TowerBrief thresholds."""

    brief_date: str = "2026-06-06"
    critical_detention_exposure: float = Field(default=1000.0, ge=0)
    high_detention_exposure: float = Field(default=500.0, ge=0)
    critical_ban_overlap_minutes: float = Field(default=120.0, ge=0)
    critical_pod_age_hours: float = Field(default=168.0, ge=0)
    max_critical_rows: int = Field(default=20, ge=1)
    max_high_priority_rows: int = Field(default=20, ge=1)
