"""Deterministic POD aging and invoice-blocker engine for PODPulse."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from pod_pulse.models import DeliveryRecord, InvoiceStatusRecord, PODPulseSettings, PODStatusRecord


ACCEPTED_POD_STATUSES = {"NOT_REQUIRED", "MISSING", "RECEIVED", "REJECTED", "RESUBMITTED", "APPROVED"}
ACCEPTED_INVOICE_STATUSES = {"NOT READY", "READY", "BLOCKED", "INVOICED", "PAID", "ON HOLD"}
TERMINAL_POD_STATUSES = {"RECEIVED", "APPROVED"}
REQUIRED_DELIVERY_COLUMNS = {"trip_id", "customer_name", "delivered_time"}
REQUIRED_POD_COLUMNS = {"trip_id", "pod_status"}
REQUIRED_INVOICE_COLUMNS = {"trip_id", "invoice_status"}
REPORT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "origin",
    "destination",
    "promised_arrival",
    "delivered_time",
    "pod_status",
    "pod_received_time",
    "pod_rejected_time",
    "rejection_reason",
    "uploaded_by",
    "invoice_status",
    "invoice_no",
    "blocked_reason",
    "pod_age_hours",
    "pod_age_days",
    "aging_bucket",
    "pod_gap_type",
    "invoice_blocked",
    "risk_bucket",
    "severity",
    "evidence",
    "suggested_action",
]
OVERDUE_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "delivered_time",
    "pod_status",
    "pod_age_hours",
    "aging_bucket",
    "exception_type",
    "severity",
    "evidence",
    "suggested_action",
]


@dataclass(frozen=True)
class PODPulseResult:
    """Structured outputs from a PODPulse run."""

    pod_aging_report: pd.DataFrame
    overdue_pods: pd.DataFrame
    kpis: dict[str, float]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return normalized


def _normalize_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return " ".join(text.split())


def _normalize_key(value: Any) -> str | None:
    text = _normalize_text(value)
    return None if text is None else text.upper().replace(" ", "")


def _normalize_pod_status(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return "_".join(text.upper().replace("-", " ").split())


def _normalize_invoice_status(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return " ".join(text.upper().replace("_", " ").replace("-", " ").split())


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _hours_between(later: pd.Timestamp | pd.NaT, earlier: pd.Timestamp | pd.NaT) -> float | None:
    if pd.isna(later) or pd.isna(earlier):
        return None
    return round((later - earlier).total_seconds() / 3600, 2)


def _age_bucket(hours: float | None) -> str:
    if hours is None:
        return "DATA MISSING"
    if hours < 24:
        return "0-24H"
    if hours < 48:
        return "24-48H"
    if hours < 72:
        return "48-72H"
    if hours < 168:
        return "72H+"
    return "7D+"


def prepare_deliveries(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate delivered trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["vehicle_id", "carrier_name", "origin", "destination", "promised_arrival"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_DELIVERY_COLUMNS, "deliveries")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["delivered_time"] = _to_utc(source["delivered_time"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(subset=["trip_id"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            DeliveryRecord(
                trip_id=str(row.trip_id),
                customer_name="" if pd.isna(row.customer_name) else str(row.customer_name),
                delivered_time=None
                if pd.isna(row.delivered_time)
                else row.delivered_time.to_pydatetime(),
                vehicle_id=None if pd.isna(row.vehicle_id) else row.vehicle_id,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                origin=None if pd.isna(row.origin) else row.origin,
                destination=None if pd.isna(row.destination) else row.destination,
                promised_arrival=None
                if pd.isna(row.promised_arrival)
                else row.promised_arrival.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"deliveries contains invalid rows: {errors[0]}")

    return source[
        [
            "trip_id",
            "vehicle_id",
            "customer_name",
            "carrier_name",
            "origin",
            "destination",
            "promised_arrival",
            "delivered_time",
        ]
    ].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_pod_status(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate proof-of-delivery status rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in [
        "pod_received_time",
        "pod_rejected_time",
        "rejection_reason",
        "uploaded_by",
        "approved_time",
        "resubmitted_time",
    ]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_POD_COLUMNS, "pod_status")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["pod_status"] = source["pod_status"].map(_normalize_pod_status)
    for column in ["pod_received_time", "pod_rejected_time", "approved_time", "resubmitted_time"]:
        source[column] = _to_utc(source[column])
    source["rejection_reason"] = source["rejection_reason"].map(_normalize_text)
    source["uploaded_by"] = source["uploaded_by"].map(_normalize_text)
    source = source.dropna(subset=["trip_id"]).copy()
    invalid = sorted(set(source["pod_status"].dropna()) - ACCEPTED_POD_STATUSES)
    if invalid:
        raise ValueError(f"pod_status contains unsupported POD statuses: {', '.join(invalid)}")

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            PODStatusRecord(
                trip_id=str(row.trip_id),
                pod_status=str(row.pod_status),
                pod_received_time=None
                if pd.isna(row.pod_received_time)
                else row.pod_received_time.to_pydatetime(),
                pod_rejected_time=None
                if pd.isna(row.pod_rejected_time)
                else row.pod_rejected_time.to_pydatetime(),
                rejection_reason=None if pd.isna(row.rejection_reason) else row.rejection_reason,
                uploaded_by=None if pd.isna(row.uploaded_by) else row.uploaded_by,
                approved_time=None if pd.isna(row.approved_time) else row.approved_time.to_pydatetime(),
                resubmitted_time=None
                if pd.isna(row.resubmitted_time)
                else row.resubmitted_time.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"pod_status contains invalid rows: {errors[0]}")

    return source[
        [
            "trip_id",
            "pod_status",
            "pod_received_time",
            "pod_rejected_time",
            "rejection_reason",
            "uploaded_by",
            "approved_time",
            "resubmitted_time",
        ]
    ].drop_duplicates("trip_id", keep="last").reset_index(drop=True)


def prepare_invoice_status(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional invoice status rows."""
    columns = ["trip_id", "invoice_status", "invoice_no", "invoice_date", "blocked_reason"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["invoice_no", "invoice_date", "blocked_reason"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_INVOICE_COLUMNS, "invoice_status")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["invoice_status"] = source["invoice_status"].map(_normalize_invoice_status)
    source["invoice_no"] = source["invoice_no"].map(_normalize_text)
    source["invoice_date"] = _to_utc(source["invoice_date"])
    source["blocked_reason"] = source["blocked_reason"].map(_normalize_text)
    source = source.dropna(subset=["trip_id"]).copy()
    invalid = sorted(set(source["invoice_status"].dropna()) - ACCEPTED_INVOICE_STATUSES)
    if invalid:
        raise ValueError(f"invoice_status contains unsupported statuses: {', '.join(invalid)}")

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            InvoiceStatusRecord(
                trip_id=str(row.trip_id),
                invoice_status=str(row.invoice_status),
                invoice_no=None if pd.isna(row.invoice_no) else row.invoice_no,
                invoice_date=None if pd.isna(row.invoice_date) else row.invoice_date.to_pydatetime(),
                blocked_reason=None if pd.isna(row.blocked_reason) else row.blocked_reason,
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"invoice_status contains invalid rows: {errors[0]}")

    return source[columns].drop_duplicates("trip_id", keep="last").reset_index(drop=True)


def _classify_row(row: pd.Series, review_time: pd.Timestamp, settings: PODPulseSettings) -> dict[str, Any]:
    delivered_time = row.delivered_time
    pod_status = row.pod_status if pd.notna(row.pod_status) else "MISSING"
    invoice_status = row.invoice_status if pd.notna(row.invoice_status) else "NOT READY"
    received_time = row.pod_received_time
    approved_time = row.approved_time
    rejected_time = row.pod_rejected_time
    customer_name = _normalize_text(row.customer_name)

    missing_required = not row.trip_id or customer_name is None
    not_delivered = pd.isna(delivered_time)
    terminal_time = received_time if pd.notna(received_time) else review_time
    pod_age_hours = None if not_delivered else _hours_between(terminal_time, delivered_time)
    pod_age_days = None if pod_age_hours is None else round(pod_age_hours / 24, 2)
    aging_bucket = _age_bucket(pod_age_hours)

    pod_approved = pod_status == "APPROVED" or pd.notna(approved_time)
    pod_received = pod_status in TERMINAL_POD_STATUSES and pd.notna(received_time)
    invoice_blocked = (
        invoice_status in {"BLOCKED", "ON HOLD"}
        or pd.notna(row.blocked_reason)
        or (invoice_status == "NOT READY" and pod_status not in {"NOT_REQUIRED", "APPROVED"})
    )

    if not_delivered:
        pod_gap_type = "NOT DELIVERED"
        risk_bucket = "DATA MISSING"
        severity = "HIGH"
        suggested_action = "Confirm delivery timestamp before POD aging review."
    elif missing_required:
        pod_gap_type = "DATA MISSING"
        risk_bucket = "DATA MISSING"
        severity = "HIGH"
        suggested_action = "Complete required delivery fields before POD follow-up."
    elif pod_status == "NOT_REQUIRED":
        pod_gap_type = "POD NOT REQUIRED"
        risk_bucket = "OK"
        severity = "OK"
        suggested_action = "No POD follow-up needed for this delivery."
    elif pod_status == "REJECTED":
        pod_gap_type = "POD REJECTED"
        severity = "CRITICAL" if invoice_blocked else "HIGH"
        risk_bucket = "HIGH RISK"
        suggested_action = "Review rejection reason and request corrected POD document."
    elif pod_status == "RESUBMITTED":
        pod_gap_type = "POD RESUBMITTED"
        risk_bucket = "REVIEW"
        severity = "MEDIUM"
        suggested_action = "Check approval queue for the resubmitted POD."
    elif pod_received:
        if pod_age_hours is not None and pod_age_hours > settings.pod_sla_hours:
            pod_gap_type = "POD LATE"
            risk_bucket = "REVIEW"
            severity = "MEDIUM"
            suggested_action = "Record late POD receipt and confirm invoice readiness."
        elif pod_approved and not invoice_blocked:
            pod_gap_type = "OK"
            risk_bucket = "OK"
            severity = "OK"
            suggested_action = "POD is usable for billing review."
        else:
            pod_gap_type = "POD RECEIVED"
            risk_bucket = "WATCH"
            severity = "LOW"
            suggested_action = "Monitor POD approval before invoice release."
    else:
        overdue = pod_age_hours is not None and pod_age_hours > settings.pod_sla_hours
        pod_gap_type = "POD OVERDUE" if overdue else "POD MISSING"
        if pod_age_hours is not None and pod_age_hours >= settings.critical_threshold_hours:
            risk_bucket = "HIGH RISK"
            severity = "CRITICAL"
        elif overdue:
            risk_bucket = "HIGH RISK"
            severity = "HIGH"
        elif pod_age_hours is not None and pod_age_hours >= settings.warning_threshold_hours:
            risk_bucket = "WATCH"
            severity = "MEDIUM"
        else:
            risk_bucket = "WATCH"
            severity = "MEDIUM"
        suggested_action = "Follow up for missing POD document."

    if invoice_blocked and pod_gap_type in {"OK", "POD RECEIVED"}:
        pod_gap_type = "INVOICE BLOCKED"
        risk_bucket = "HIGH RISK"
        severity = "HIGH"
        suggested_action = "Resolve invoice blocker before billing can progress."

    evidence_parts = []
    if pod_age_hours is not None:
        evidence_parts.append(f"POD age {pod_age_hours:.0f} hours")
    if pod_status:
        evidence_parts.append(f"POD status {pod_status}")
    if invoice_status:
        evidence_parts.append(f"invoice status {invoice_status}")
    if pd.notna(row.rejection_reason):
        evidence_parts.append(f"rejection reason: {row.rejection_reason}")
    if pd.notna(row.blocked_reason):
        evidence_parts.append(f"blocked reason: {row.blocked_reason}")
    evidence = "; ".join(evidence_parts) if evidence_parts else "required evidence missing"

    return {
        "trip_id": row.trip_id,
        "vehicle_id": row.vehicle_id,
        "customer_name": row.customer_name,
        "carrier_name": row.carrier_name,
        "origin": row.origin,
        "destination": row.destination,
        "promised_arrival": row.promised_arrival,
        "delivered_time": delivered_time,
        "pod_status": pod_status,
        "pod_received_time": received_time,
        "pod_rejected_time": rejected_time,
        "rejection_reason": row.rejection_reason,
        "uploaded_by": row.uploaded_by,
        "invoice_status": invoice_status,
        "invoice_no": row.invoice_no,
        "blocked_reason": row.blocked_reason,
        "pod_age_hours": pod_age_hours,
        "pod_age_days": pod_age_days,
        "aging_bucket": aging_bucket,
        "pod_gap_type": pod_gap_type,
        "invoice_blocked": bool(invoice_blocked),
        "risk_bucket": risk_bucket,
        "severity": severity,
        "evidence": evidence,
        "suggested_action": suggested_action,
    }


def run_pod_pulse(
    deliveries_df: pd.DataFrame,
    pod_status_df: pd.DataFrame,
    invoice_status_df: pd.DataFrame | None = None,
    *,
    settings: PODPulseSettings | None = None,
    review_time: str | pd.Timestamp | None = None,
) -> PODPulseResult:
    """Run POD aging classification and return report dataframes."""
    active_settings = settings or PODPulseSettings()
    review_timestamp = pd.Timestamp(review_time or pd.Timestamp.now(tz="UTC"))
    if review_timestamp.tzinfo is None:
        review_timestamp = review_timestamp.tz_localize("UTC")
    else:
        review_timestamp = review_timestamp.tz_convert("UTC")

    deliveries = prepare_deliveries(deliveries_df)
    pod_status = prepare_pod_status(pod_status_df)
    invoice_status = prepare_invoice_status(invoice_status_df)
    merged = deliveries.merge(pod_status, on="trip_id", how="left")
    merged = merged.merge(invoice_status, on="trip_id", how="left")
    rows = [
        _classify_row(row, review_timestamp, active_settings)
        for row in merged.itertuples(index=False)
    ]
    report = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    if not report.empty:
        report = report.sort_values(
            ["severity", "pod_age_hours", "trip_id"],
            ascending=[True, False, True],
        )
    overdue = report[
        ~report["pod_gap_type"].isin({"OK", "POD NOT REQUIRED"})
        | report["invoice_blocked"]
    ].copy()
    if overdue.empty:
        overdue = pd.DataFrame(columns=OVERDUE_COLUMNS)
    else:
        overdue["exception_type"] = overdue["pod_gap_type"]
        overdue = overdue[OVERDUE_COLUMNS].reset_index(drop=True)

    total = float(len(report))
    missing = float((report["pod_gap_type"] == "POD MISSING").sum()) if total else 0.0
    overdue_count = float((report["pod_gap_type"] == "POD OVERDUE").sum()) if total else 0.0
    late = float((report["pod_gap_type"] == "POD LATE").sum()) if total else 0.0
    rejected = float((report["pod_gap_type"] == "POD REJECTED").sum()) if total else 0.0
    blockers = float(report["invoice_blocked"].sum()) if total else 0.0
    kpis = {
        "total_deliveries": total,
        "missing_pods": missing,
        "overdue_pods": overdue_count,
        "late_pods": late,
        "rejected_pods": rejected,
        "invoice_blockers": blockers,
        "critical_pod_gaps": float((report["severity"] == "CRITICAL").sum()) if total else 0.0,
    }
    return PODPulseResult(pod_aging_report=report.reset_index(drop=True), overdue_pods=overdue, kpis=kpis)


def write_outputs(result: PODPulseResult, output_dir: str | Path) -> tuple[Path, Path]:
    """Write PODPulse CSV outputs and return their paths."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    report_path = target / "pod_aging_report.csv"
    overdue_path = target / "overdue_pods.csv"
    result.pod_aging_report.to_csv(report_path, index=False)
    result.overdue_pods.to_csv(overdue_path, index=False)
    return report_path, overdue_path
