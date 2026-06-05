"""Pydantic validation models for PODPulse input records."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PODPulseSettings(BaseModel):
    """User-adjustable POD aging thresholds."""

    pod_sla_hours: int = Field(default=48, ge=0)
    warning_threshold_hours: int = Field(default=24, ge=0)
    critical_threshold_hours: int = Field(default=168, ge=0)


class DeliveryRecord(BaseModel):
    """Validated delivered trip row."""

    trip_id: str
    customer_name: str
    delivered_time: datetime | None = None
    vehicle_id: str | None = None
    carrier_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    promised_arrival: datetime | None = None


class PODStatusRecord(BaseModel):
    """Validated proof-of-delivery status row."""

    trip_id: str
    pod_status: str
    pod_received_time: datetime | None = None
    pod_rejected_time: datetime | None = None
    rejection_reason: str | None = None
    uploaded_by: str | None = None
    approved_time: datetime | None = None
    resubmitted_time: datetime | None = None


class InvoiceStatusRecord(BaseModel):
    """Validated invoice status row."""

    trip_id: str
    invoice_status: str
    invoice_no: str | None = None
    invoice_date: datetime | None = None
    blocked_reason: str | None = None

