"""Pydantic validation models for DelayLens input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DelayLensSettings(BaseModel):
    """User-adjustable thresholds for delay classification."""

    late_departure_tolerance_minutes: int = Field(default=15, ge=0)
    late_arrival_tolerance_minutes: int = Field(default=15, ge=0)
    origin_dwell_threshold_minutes: int = Field(default=60, ge=0)
    hub_dwell_threshold_minutes: int = Field(default=45, ge=0)
    destination_dwell_threshold_minutes: int = Field(default=60, ge=0)
    baseline_delta_threshold_minutes: int = Field(default=30, ge=0)
    critical_arrival_delay_threshold_minutes: int = Field(default=120, ge=0)


class TripRecord(BaseModel):
    """Validated trip plan row used for delay classification."""

    trip_id: str
    vehicle_id: str
    customer_name: str | None = None
    carrier_name: str | None = None
    lane_id: str | None = None
    origin: str
    destination: str
    planned_departure: datetime
    promised_arrival: datetime


class VisitEventRecord(BaseModel):
    """Validated GeoReplay visit event row."""

    trip_id: str | None = None
    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    geofence_type: str | None = None
    enter_time: datetime | None = None
    exit_time: datetime | None = None
    dwell_minutes: float | None = Field(default=None, ge=0)


class LaneBaselineRecord(BaseModel):
    """Validated optional lane baseline row."""

    lane_id: str | None = None
    origin: str | None = None
    destination: str | None = None
    baseline_minutes: float = Field(ge=0)
    p50_minutes: float | None = Field(default=None, ge=0)
    p75_minutes: float | None = Field(default=None, ge=0)
    p90_minutes: float | None = Field(default=None, ge=0)
    sample_size: int | None = Field(default=None, ge=0)
