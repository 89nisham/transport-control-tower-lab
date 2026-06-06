"""Pydantic models for CarrierScore settings and scoring rules."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CarrierScoreSettings(BaseModel):
    """User-adjustable CarrierScore settings."""

    minimum_trips_for_reliable_score: int = Field(default=3, ge=1)
    excellent_threshold: int = Field(default=90, ge=0, le=100)
    good_threshold: int = Field(default=75, ge=0, le=100)
    watch_threshold: int = Field(default=60, ge=0, le=100)
    detention_exposure_high_threshold: float = Field(default=500.0, ge=0)
    allow_uploaded_scoring_rules: bool = True


class CarrierScoreRule(BaseModel):
    """Validated configurable scoring rule."""

    metric_name: str
    weight: float = Field(gt=0)
    direction: str
    enabled: bool = True
    good_threshold: float | None = None
    bad_threshold: float | None = None

