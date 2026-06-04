"""Pydantic validation models for ETA Watch input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TripRecord(BaseModel):
    """Validated trip row used by ETA Watch."""

    trip_id: str
    vehicle_id: str
    origin: str | None = None
    destination: str
    lane_id: str | None = None
    planned_departure: datetime | None = None
    promised_arrival: datetime


class VisitEventRecord(BaseModel):
    """Validated GeoReplay visit event row used as latest progress signal."""

    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    entry_time: datetime | None = None
    exit_time: datetime
    dwell_minutes: float | None = Field(default=None, ge=0)


class LaneBaselineRecord(BaseModel):
    """Validated lane baseline row for deterministic remaining-time estimates."""

    lane_id: str | None = None
    from_geofence_id: str | None = None
    to_destination: str | None = None
    remaining_minutes_after_geofence: float | None = Field(default=None, ge=0)
    default_remaining_minutes: float | None = Field(default=None, ge=0)

