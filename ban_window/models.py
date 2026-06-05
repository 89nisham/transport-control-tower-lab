"""Pydantic validation models for BanWindow input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BanWindowSettings(BaseModel):
    """User-adjustable BanWindow planning settings."""

    watch_buffer_minutes: int = Field(default=60, ge=0)
    expansion_padding_days: int = Field(default=1, ge=0)


class TripRecord(BaseModel):
    """Validated planned trip row."""

    trip_id: str
    vehicle_id: str
    origin: str
    destination: str
    planned_departure: datetime | None = None
    promised_arrival: datetime | None = None
    customer_name: str | None = None
    carrier_name: str | None = None
    city: str | None = None
    vehicle_class: str | None = None
    planned_city_entry: datetime | None = None
    planned_city_exit: datetime | None = None


class BanWindowRecord(BaseModel):
    """Validated user-supplied restriction window row."""

    ban_id: str
    city: str
    start_time: str
    end_time: str
    location_name: str | None = None
    vehicle_class: str | None = None
    days_of_week: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    rule_note: str | None = None

