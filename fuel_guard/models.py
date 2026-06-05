"""Pydantic validation models for FuelGuard input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FuelEventRecord(BaseModel):
    """Validated fuel transaction row used for evidence reconciliation."""

    fuel_event_id: str
    vehicle_id: str
    fuel_time: datetime
    liters: float = Field(ge=0)
    station_name: str | None = None
    station_id: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    amount: float | None = Field(default=None, ge=0)
    odometer: float | None = Field(default=None, ge=0)
    receipt_no: str | None = None
    currency: str | None = None
    driver_name: str | None = None
    carrier_name: str | None = None
    trip_id: str | None = None


class VisitEventRecord(BaseModel):
    """Validated GeoReplay visit row used as stop evidence."""

    trip_id: str | None = None
    vehicle_id: str
    geofence_id: str | None = None
    geofence_name: str | None = None
    geofence_type: str | None = None
    enter_time: datetime | None = None
    exit_time: datetime | None = None
    dwell_minutes: float | None = Field(default=None, ge=0)


class GpsPointRecord(BaseModel):
    """Validated GPS point row used as location evidence."""

    vehicle_id: str
    timestamp: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_kph: float | None = Field(default=None, ge=0)


class FuelSiteRecord(BaseModel):
    """Validated fuel-site master row used for location matching."""

    station_id: str | None = None
    station_name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: float | None = Field(default=250, gt=0)


class TripRecord(BaseModel):
    """Validated optional trip context used for window checks."""

    trip_id: str
    vehicle_id: str
    customer_name: str | None = None
    carrier_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    planned_departure: datetime | None = None
    promised_arrival: datetime | None = None
