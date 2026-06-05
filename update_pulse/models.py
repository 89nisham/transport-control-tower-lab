"""Pydantic validation models for UpdatePulse input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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

    update_id: str | None = None
    trip_id: str | None = None
    vehicle_id: str
    update_time: datetime
    status: str
    source: str | None = None
    note: str | None = None


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
