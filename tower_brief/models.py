"""Pydantic models for TowerBrief settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TowerBriefSettings(BaseModel):
    """User-adjustable TowerBrief thresholds."""

    brief_date: str = "2026-06-06"
    high_priority_limit: int = Field(default=10, ge=1)
    detention_exposure_threshold: float = Field(default=500.0, ge=0)
    fuel_liter_threshold: float = Field(default=150.0, ge=0)
    stale_update_minutes_threshold: float = Field(default=120.0, ge=0)

