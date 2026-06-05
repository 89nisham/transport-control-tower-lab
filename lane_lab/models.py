"""Pydantic validation models for LaneLab input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LaneLabSettings(BaseModel):
    """User-adjustable lane baseline settings."""

    low_sample_threshold: int = Field(default=5, ge=1)
    unstable_p90_p50_ratio_threshold: float = Field(default=1.5, ge=0)
    outlier_iqr_multiplier: float = Field(default=1.5, ge=0)
    extreme_duration_min_minutes: int = Field(default=30, ge=0)
    extreme_duration_max_minutes: int = Field(default=2880, ge=1)
    min_usable_trips_for_percentiles: int = Field(default=2, ge=1)


class HistoricalTripRecord(BaseModel):
    """Validated historical trip row."""

    trip_id: str
    vehicle_id: str
    origin: str
    destination: str
    lane_id: str | None = None
    customer_name: str | None = None
    carrier_name: str | None = None
    planned_departure: datetime | None = None
    promised_arrival: datetime | None = None


class VisitEventRecord(BaseModel):
    """Validated GeoReplay visit event row."""

    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    geofence_type: str | None = None
    enter_time: datetime | None = None
    exit_time: datetime | None = None
    dwell_minutes: float | None = None
    trip_id: str | None = None
