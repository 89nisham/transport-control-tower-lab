"""Pydantic validation models for GeoReplay input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GpsPoint(BaseModel):
    """Validated GPS ping input record."""

    vehicle_id: str
    timestamp: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kph: float | None = Field(default=None, ge=0)


class Geofence(BaseModel):
    """Validated circular geofence master-data record."""

    geofence_id: str
    name: str | None = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0)
    geofence_type: str | None = None


class PlannedStop(BaseModel):
    """Validated planned stop used for missed-stop detection."""

    vehicle_id: str
    geofence_id: str
    planned_arrival: datetime | None = None
    stop_sequence: int | None = None
