"""Pydantic validation models for DetentionClock input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VisitEventRecord(BaseModel):
    """Validated GeoReplay visit event row used for detention calculations."""

    trip_id: str | None = None
    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    geofence_type: str
    enter_time: datetime | None = None
    exit_time: datetime | None = None
    dwell_minutes: float | None = Field(default=None, ge=0)


class DetentionRuleRecord(BaseModel):
    """Validated detention rule row supplied by the user."""

    rule_id: str
    customer_name: str | None = None
    geofence_type: str | None = None
    geofence_id: str | None = None
    free_minutes: float = Field(ge=0)
    rate_type: str = "hourly"
    rate_per_hour: float = Field(ge=0)
    minimum_charge: float | None = Field(default=None, ge=0)
    currency: str


class TripRecord(BaseModel):
    """Validated optional trip context row."""

    trip_id: str
    customer_name: str | None = None
    carrier_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    planned_arrival: datetime | None = None
    planned_departure: datetime | None = None

