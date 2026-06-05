"""Pydantic validation models for UpdatePulse input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UpdatePulseSettings(BaseModel):
    """User-adjustable tolerances for update discipline review."""

    late_tolerance_minutes: int = Field(default=15, ge=0)
    early_tolerance_minutes: int = Field(default=15, ge=0)
    duplicate_update_window_minutes: int = Field(default=10, ge=0)
    assigned_lead_minutes: int = Field(default=120, ge=0)
    include_pod_collected: bool = False


class TripRecord(BaseModel):
    """Validated planned trip row used for update-discipline review."""

    trip_id: str
    vehicle_id: str
    driver_name: str | None = None
    carrier_name: str | None = None
    customer_name: str | None = None
    origin: str
    destination: str
    planned_departure: datetime
    promised_arrival: datetime


class UpdateRecord(BaseModel):
    """Validated TMS or driver update row."""

    trip_id: str
    vehicle_id: str | None = None
    update_time: datetime
    status: str
    updated_by: str | None = None
    source: str | None = None


class VisitEventRecord(BaseModel):
    """Validated optional GeoReplay visit row used as actual event evidence."""

    trip_id: str | None = None
    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    geofence_type: str | None = None
    enter_time: datetime | None = None
    exit_time: datetime | None = None
    dwell_minutes: float | None = Field(default=None, ge=0)
