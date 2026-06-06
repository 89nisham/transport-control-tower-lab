"""Pydantic models for CarrierScore settings and records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CarrierScoreSettings(BaseModel):
    """User-adjustable CarrierScore settings."""

    score_floor: int = Field(default=0, ge=0, le=100)
    strong_threshold: int = Field(default=90, ge=0, le=100)
    stable_threshold: int = Field(default=75, ge=0, le=100)
    watchlist_threshold: int = Field(default=60, ge=0, le=100)
    minimum_high_confidence_trips: int = Field(default=5, ge=1)
    minimum_medium_confidence_trips: int = Field(default=3, ge=1)


class CarrierScoreRule(BaseModel):
    """Validated score weight rule."""

    metric: str
    weight: float = Field(gt=0)


class TripRecord(BaseModel):
    """Validated carrier-owned trip row."""

    trip_id: str
    carrier_name: str
    vehicle_id: str | None = None
    customer_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    lane_id: str | None = None
    planned_departure: datetime | None = None
    promised_arrival: datetime | None = None
    delivered_time: datetime | None = None

