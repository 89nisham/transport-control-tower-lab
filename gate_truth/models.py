"""Pydantic validation models for GateTruth input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TripRecord(BaseModel):
    """Validated trip row used for planned-vs-actual gate evidence."""

    trip_id: str
    vehicle_id: str
    customer_name: str | None = None
    carrier_name: str | None = None
    origin: str
    destination: str
    origin_geofence_id: str | None = None
    destination_geofence_id: str | None = None
    planned_departure: datetime | None = None
    promised_arrival: datetime | None = None


class VisitEventRecord(BaseModel):
    """Validated GeoReplay visit event row used as operational evidence."""

    trip_id: str | None = None
    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    geofence_type: str | None = None
    enter_time: datetime | None = None
    exit_time: datetime | None = None
    dwell_minutes: float | None = Field(default=None, ge=0)


class PlannedStopRecord(BaseModel):
    """Validated optional planned stop row used to strengthen matching."""

    trip_id: str
    vehicle_id: str
    geofence_id: str
    stop_sequence: int | None = Field(default=None, ge=0)
    stop_type: str | None = None
    planned_arrival: datetime | None = None
    planned_departure: datetime | None = None

