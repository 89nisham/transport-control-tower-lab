"""Deterministic update-discipline engine for UpdatePulse."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from update_pulse.models import TripRecord, UpdatePulseSettings, UpdateRecord, VisitEventRecord


EXPECTED_STATUSES = [
    "ASSIGNED",
    "ARRIVED_ORIGIN",
    "DEPARTED_ORIGIN",
    "ARRIVED_DESTINATION",
    "DELIVERED",
]
OPTIONAL_STATUSES = ["POD_COLLECTED"]
STATUS_RANK = {
    "ASSIGNED": 1,
    "ARRIVED_ORIGIN": 2,
    "DEPARTED_ORIGIN": 3,
    "ARRIVED_DESTINATION": 4,
    "DELIVERED": 5,
    "POD_COLLECTED": 6,
}
ORIGIN_TYPES = {"ORIGIN", "HUB", "PICKUP"}
DESTINATION_TYPES = {"DESTINATION", "CUSTOMER", "DELIVERY"}
REQUIRED_TRIP_COLUMNS = {
    "trip_id",
    "vehicle_id",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
}
REQUIRED_UPDATE_COLUMNS = {"trip_id", "update_time", "status"}
REQUIRED_VISIT_COLUMNS = {
    "vehicle_id",
    "geofence_name",
    "geofence_type",
    "enter_time",
    "exit_time",
}
REPORT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "driver_name",
    "carrier_name",
    "customer_name",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
    "expected_status",
    "expected_time",
    "actual_update_time",
    "actual_status",
    "source",
    "updated_by",
    "update_delay_minutes",
    "update_gap_type",
    "sequence_status",
    "evidence_status",
    "risk_bucket",
    "severity",
    "evidence",
    "suggested_action",
]
EXCEPTION_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "driver_name",
    "carrier_name",
    "customer_name",
    "expected_status",
    "actual_status",
    "exception_type",
    "severity",
    "evidence",
    "suggested_action",
]


@dataclass(frozen=True)
class UpdatePulseResult:
    """Structured outputs from an UpdatePulse run."""

    update_discipline_report: pd.DataFrame
    update_exceptions: pd.DataFrame
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


def _normalize_status(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return "_".join(text.upper().replace("-", " ").split())


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _minutes_between(actual: pd.Timestamp | pd.NaT, target: pd.Timestamp | pd.NaT) -> float | None:
    if pd.isna(actual) or pd.isna(target):
        return None
    return round((actual - target).total_seconds() / 60, 2)


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timestamp-standardize, and validate UpdatePulse trips."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["driver_name", "carrier_name", "customer_name"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["driver_name"] = source["driver_name"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(
        subset=["trip_id", "vehicle_id", "origin", "destination", "planned_departure", "promised_arrival"]
    ).copy()

    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                driver_name=None if pd.isna(row.driver_name) else row.driver_name,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                origin=str(row.origin),
                destination=str(row.destination),
                planned_departure=row.planned_departure.to_pydatetime(),
                promised_arrival=row.promised_arrival.to_pydatetime(),
            )
        except ValidationError as exc:
            raise ValueError(f"trips contains invalid rows: {exc}") from exc

    return source[
        [
            "trip_id",
            "vehicle_id",
            "driver_name",
            "carrier_name",
            "customer_name",
            "origin",
            "destination",
            "planned_departure",
            "promised_arrival",
        ]
    ].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_updates(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timestamp-standardize, and validate TMS or driver update rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    if "driver_update_time" in source.columns and "update_time" not in source.columns:
        source["update_time"] = source["driver_update_time"]
    if "tms_update_time" in source.columns and "update_time" not in source.columns:
        source["update_time"] = source["tms_update_time"]
    if "update_status" in source.columns and "status" not in source.columns:
        source["status"] = source["update_status"]
    for column in ["vehicle_id", "updated_by", "source"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_UPDATE_COLUMNS, "updates")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["update_time"] = _to_utc(source["update_time"])
    source["status"] = source["status"].map(_normalize_status)
    source["updated_by"] = source["updated_by"].map(_normalize_text)
    source["source"] = source["source"].map(_normalize_text)
    source = source.dropna(subset=["trip_id", "update_time", "status"]).copy()

    for row in source.itertuples(index=False):
        try:
            UpdateRecord(
                trip_id=str(row.trip_id),
                vehicle_id=None if pd.isna(row.vehicle_id) else row.vehicle_id,
                update_time=row.update_time.to_pydatetime(),
                status=str(row.status),
                updated_by=None if pd.isna(row.updated_by) else row.updated_by,
                source=None if pd.isna(row.source) else row.source,
            )
        except ValidationError as exc:
            raise ValueError(f"updates contains invalid rows: {exc}") from exc

    return source[["trip_id", "vehicle_id", "update_time", "status", "updated_by", "source"]].reset_index(
        drop=True
    )


def prepare_visit_events(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional GeoReplay visit events used as actual event evidence."""
    columns = [
        "trip_id",
        "vehicle_id",
        "geofence_id",
        "geofence_name",
        "geofence_type",
        "enter_time",
        "exit_time",
        "dwell_minutes",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    if "entry_time" in source.columns and "enter_time" not in source.columns:
        source["enter_time"] = source["entry_time"]
    for column in ["trip_id", "geofence_id", "dwell_minutes"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_VISIT_COLUMNS, "visit_events")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["geofence_id"] = source["geofence_id"].map(_normalize_key)
    source["geofence_name"] = source["geofence_name"].map(_normalize_text)
    source["geofence_type"] = source["geofence_type"].map(_normalize_key)
    source["enter_time"] = _to_utc(source["enter_time"])
    source["exit_time"] = _to_utc(source["exit_time"])
    source["dwell_minutes"] = pd.to_numeric(source["dwell_minutes"], errors="coerce")
    source = source.dropna(subset=["vehicle_id"]).copy()

    for row in source.itertuples(index=False):
        try:
            VisitEventRecord(
                trip_id=None if pd.isna(row.trip_id) else row.trip_id,
                vehicle_id=str(row.vehicle_id),
                geofence_id=None if pd.isna(row.geofence_id) else row.geofence_id,
                geofence_name=None if pd.isna(row.geofence_name) else row.geofence_name,
                geofence_type=None if pd.isna(row.geofence_type) else row.geofence_type,
                enter_time=None if pd.isna(row.enter_time) else row.enter_time.to_pydatetime(),
                exit_time=None if pd.isna(row.exit_time) else row.exit_time.to_pydatetime(),
                dwell_minutes=None if pd.isna(row.dwell_minutes) else float(row.dwell_minutes),
            )
        except ValidationError as exc:
            raise ValueError(f"visit_events contains invalid rows: {exc}") from exc

    return source[columns].reset_index(drop=True)


def build_expected_milestones(
    trips: pd.DataFrame,
    settings: UpdatePulseSettings | None = None,
) -> pd.DataFrame:
    """Create one expected status milestone per trip."""
    settings = settings or UpdatePulseSettings()
    prepared = prepare_trips(trips)
    rows: list[dict[str, Any]] = []

    for trip in prepared.itertuples(index=False):
        milestones = [
            ("ASSIGNED", trip.planned_departure - pd.Timedelta(minutes=settings.assigned_lead_minutes)),
            ("ARRIVED_ORIGIN", trip.planned_departure),
            ("DEPARTED_ORIGIN", trip.planned_departure),
            ("ARRIVED_DESTINATION", trip.promised_arrival),
            ("DELIVERED", trip.promised_arrival),
        ]
        if settings.include_pod_collected:
            milestones.append(("POD_COLLECTED", trip.promised_arrival + pd.Timedelta(minutes=30)))
        for status, expected_time in milestones:
            rows.append({**trip._asdict(), "expected_status": status, "expected_time": expected_time})

    return pd.DataFrame(rows)


def _name_matches(candidate: Any, target: Any) -> bool:
    candidate_text = _normalize_key(candidate)
    target_text = _normalize_key(target)
    if candidate_text is None or target_text is None:
        return False
    return candidate_text in target_text or target_text in candidate_text


def _visit_candidates(
    trip: pd.Series,
    visits: pd.DataFrame,
    expected_status: str,
) -> tuple[pd.DataFrame, str | None]:
    if expected_status in {"ASSIGNED", "POD_COLLECTED"}:
        return pd.DataFrame(), None

    is_origin = expected_status in {"ARRIVED_ORIGIN", "DEPARTED_ORIGIN"}
    type_set = ORIGIN_TYPES if is_origin else DESTINATION_TYPES
    location_name = trip.origin if is_origin else trip.destination
    time_column = "enter_time" if expected_status in {"ARRIVED_ORIGIN", "ARRIVED_DESTINATION"} else "exit_time"
    window_start = trip.planned_departure - pd.Timedelta(hours=12)
    window_end = trip.promised_arrival + pd.Timedelta(hours=24)

    exact = visits[(visits["trip_id"] == trip.trip_id) & (visits["vehicle_id"] == trip.vehicle_id)].copy()
    fallback = visits[
        (visits["trip_id"].isna())
        & (visits["vehicle_id"] == trip.vehicle_id)
        & (
            (visits["enter_time"].between(window_start, window_end))
            | (visits["exit_time"].between(window_start, window_end))
        )
    ].copy()
    candidates = exact if not exact.empty else fallback
    if candidates.empty:
        return candidates, time_column

    typed = candidates[
        candidates["geofence_type"].isin(type_set)
        | candidates["geofence_name"].map(lambda value: _name_matches(value, location_name))
    ].copy()
    typed = typed[typed[time_column].notna()].copy()
    return typed, time_column


def _event_evidence(
    trip: pd.Series,
    visits: pd.DataFrame,
    expected_status: str,
) -> tuple[pd.Timestamp | pd.NaT, str, str]:
    if expected_status == "ASSIGNED":
        return pd.NaT, "NOT REQUIRED", "Assignment milestone does not need geofence evidence"
    if expected_status == "POD_COLLECTED":
        return pd.NaT, "NOT REQUIRED", "POD collection is document evidence, not geofence evidence"
    if visits.empty:
        return pd.NaT, "NO VISIT EVENTS PROVIDED", "No visit_events.csv was provided"

    candidates, time_column = _visit_candidates(trip, visits, expected_status)
    if time_column is None:
        return pd.NaT, "NOT REQUIRED", "No geofence evidence required"
    if candidates.empty:
        return pd.NaT, "NO ACTUAL EVENT EVIDENCE", "No matching actual visit event found"
    if len(candidates) > 1:
        names = ", ".join(candidates["geofence_name"].dropna().astype(str).head(3))
        return pd.NaT, "AMBIGUOUS EVENT EVIDENCE", f"Multiple possible visit events: {names}"

    event = candidates.iloc[0]
    evidence = f"{event.geofence_name} {time_column} at {event[time_column]}"
    return event[time_column], "SUPPORTED BY ACTUAL EVENT", evidence


def _matching_update(milestone: pd.Series, updates: pd.DataFrame) -> pd.Series | None:
    candidates = updates[
        (updates["trip_id"] == milestone.trip_id) & (updates["status"] == milestone.expected_status)
    ].copy()
    if milestone.vehicle_id and "vehicle_id" in candidates.columns:
        candidates = candidates[candidates["vehicle_id"].isna() | (candidates["vehicle_id"] == milestone.vehicle_id)]
    if candidates.empty:
        return None
    candidates["minutes_from_expected"] = (
        (candidates["update_time"] - milestone.expected_time).dt.total_seconds().abs().div(60)
    )
    return candidates.sort_values(["minutes_from_expected", "update_time"]).iloc[0]


def _duplicate_statuses(updates: pd.DataFrame, settings: UpdatePulseSettings) -> set[tuple[str, str]]:
    duplicates: set[tuple[str, str]] = set()
    for (trip_id, status), group in updates.dropna(subset=["trip_id", "status"]).groupby(["trip_id", "status"]):
        ordered = group.sort_values("update_time")
        times = ordered["update_time"].tolist()
        if len(times) > 1:
            duplicates.add((trip_id, status))
        for previous, current in zip(times, times[1:]):
            if (current - previous).total_seconds() / 60 <= settings.duplicate_update_window_minutes:
                duplicates.add((trip_id, status))
    return duplicates


def _sequence_issues(updates: pd.DataFrame) -> set[tuple[str, str]]:
    issues: set[tuple[str, str]] = set()
    for trip_id, group in updates.groupby("trip_id"):
        highest_rank = 0
        previous_status: str | None = None
        for row in group.sort_values("update_time").itertuples(index=False):
            rank = STATUS_RANK.get(row.status)
            if rank is None:
                continue
            if rank < highest_rank:
                issues.add((trip_id, row.status))
                if previous_status is not None:
                    issues.add((trip_id, previous_status))
            highest_rank = max(highest_rank, rank)
            previous_status = row.status
    return issues


def _classify_gap(
    actual_update_time: pd.Timestamp | pd.NaT,
    expected_time: pd.Timestamp,
    evidence_time: pd.Timestamp | pd.NaT,
    flags: list[str],
    settings: UpdatePulseSettings,
) -> str:
    if pd.isna(actual_update_time):
        return "MISSING UPDATE"
    if "OUT OF SEQUENCE" in flags:
        return "OUT OF SEQUENCE"
    comparison_time = evidence_time if pd.notna(evidence_time) else expected_time
    delay = _minutes_between(actual_update_time, comparison_time)
    if delay is not None and delay < -settings.early_tolerance_minutes:
        return "EARLY UPDATE"
    if delay is not None and delay > settings.late_tolerance_minutes:
        return "LATE UPDATE"
    if "DUPLICATE UPDATE" in flags:
        return "DUPLICATE UPDATE"
    if "NO ACTUAL EVENT EVIDENCE" in flags:
        return "NO ACTUAL EVENT EVIDENCE"
    return "OK"


def _severity(exception_type: str, early_against_actual: bool = False) -> str:
    if exception_type in {"MISSING UPDATE", "OUT OF SEQUENCE"} or early_against_actual:
        return "HIGH"
    if exception_type in {"EARLY UPDATE", "LATE UPDATE", "DUPLICATE UPDATE", "NO ACTUAL EVENT EVIDENCE"}:
        return "MEDIUM"
    return "OK"


def _risk_bucket(severity: str, gap_type: str, evidence_status: str) -> str:
    if gap_type == "OK" and severity == "OK":
        return "OK"
    if gap_type == "MISSING UPDATE":
        return "DATA MISSING"
    if severity == "HIGH":
        return "HIGH RISK"
    if evidence_status in {"NO ACTUAL EVENT EVIDENCE", "AMBIGUOUS EVENT EVIDENCE"}:
        return "REVIEW"
    return "WATCH"


def _action_for(gap_type: str, evidence_status: str) -> str:
    if gap_type == "OK":
        return "No action needed"
    if gap_type == "MISSING UPDATE":
        return "Ask dispatch to close the update gap and confirm the operational event"
    if gap_type == "OUT OF SEQUENCE":
        return "Review the status timeline and correct the sequence before using the update operationally"
    if gap_type == "EARLY UPDATE":
        return "Validate whether the update was posted before the physical event occurred"
    if gap_type == "LATE UPDATE":
        return "Coach the control-tower process on timely status capture"
    if gap_type == "DUPLICATE UPDATE":
        return "Reduce repeated status noise and keep the latest operationally useful update"
    if evidence_status == "NO ACTUAL EVENT EVIDENCE":
        return "Check whether GeoReplay evidence is missing or the geofence match needs correction"
    return "Review update timing with dispatch"


def build_update_discipline_report(
    trips: pd.DataFrame,
    updates: pd.DataFrame,
    visit_events: pd.DataFrame | None = None,
    settings: UpdatePulseSettings | None = None,
) -> pd.DataFrame:
    """Build the requested UpdatePulse milestone-level report."""
    settings = settings or UpdatePulseSettings()
    milestones = build_expected_milestones(trips, settings)
    prepared_updates = prepare_updates(updates)
    prepared_visits = prepare_visit_events(visit_events)
    duplicates = _duplicate_statuses(prepared_updates, settings)
    sequence_issues = _sequence_issues(prepared_updates)
    rows: list[dict[str, Any]] = []

    for milestone in milestones.itertuples(index=False):
        milestone_series = pd.Series(milestone._asdict())
        update = _matching_update(milestone_series, prepared_updates)
        actual_update_time = pd.NaT if update is None else update.update_time
        actual_status = None if update is None else update.status
        source = None if update is None else update.source
        updated_by = None if update is None else update.updated_by
        event_time, evidence_status, evidence_detail = _event_evidence(
            milestone_series,
            prepared_visits,
            milestone.expected_status,
        )
        comparison_time = event_time if pd.notna(event_time) else milestone.expected_time
        delay = _minutes_between(actual_update_time, comparison_time)

        flags: list[str] = []
        if update is None:
            flags.append("MISSING UPDATE")
        if (milestone.trip_id, milestone.expected_status) in sequence_issues:
            flags.append("OUT OF SEQUENCE")
        early_against_actual = (
            pd.notna(actual_update_time)
            and pd.notna(event_time)
            and _minutes_between(actual_update_time, event_time) < -settings.early_tolerance_minutes
        )
        if pd.notna(actual_update_time) and delay is not None:
            if delay < -settings.early_tolerance_minutes:
                flags.append("EARLY UPDATE")
            elif delay > settings.late_tolerance_minutes:
                flags.append("LATE UPDATE")
        if (milestone.trip_id, milestone.expected_status) in duplicates:
            flags.append("DUPLICATE UPDATE")
        if pd.notna(actual_update_time) and evidence_status == "NO ACTUAL EVENT EVIDENCE":
            flags.append("NO ACTUAL EVENT EVIDENCE")

        gap_type = _classify_gap(
            actual_update_time,
            milestone.expected_time,
            event_time,
            flags,
            settings,
        )
        severity = _severity(gap_type, early_against_actual)
        evidence_parts = [
            f"Expected {milestone.expected_status} at {milestone.expected_time}",
            "No matching update found" if update is None else f"Matched update at {actual_update_time}",
            evidence_detail,
        ]
        if delay is not None:
            evidence_parts.append(f"{delay:+.0f} minutes vs comparison time")
        if len(flags) > 1:
            evidence_parts.append(f"Also flagged: {', '.join(flag for flag in flags if flag != gap_type)}")

        rows.append(
            {
                "trip_id": milestone.trip_id,
                "vehicle_id": milestone.vehicle_id,
                "driver_name": milestone.driver_name,
                "carrier_name": milestone.carrier_name,
                "customer_name": milestone.customer_name,
                "origin": milestone.origin,
                "destination": milestone.destination,
                "planned_departure": milestone.planned_departure,
                "promised_arrival": milestone.promised_arrival,
                "expected_status": milestone.expected_status,
                "expected_time": milestone.expected_time,
                "actual_update_time": actual_update_time,
                "actual_status": actual_status,
                "source": source,
                "updated_by": updated_by,
                "update_delay_minutes": delay,
                "update_gap_type": gap_type,
                "sequence_status": "OUT OF SEQUENCE"
                if (milestone.trip_id, milestone.expected_status) in sequence_issues
                else "OK",
                "evidence_status": evidence_status,
                "risk_bucket": _risk_bucket(severity, gap_type, evidence_status),
                "severity": severity,
                "evidence": "; ".join(evidence_parts),
                "suggested_action": _action_for(gap_type, evidence_status),
            }
        )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS).sort_values(
        ["risk_bucket", "trip_id", "expected_time"],
        key=lambda series: series.map({"HIGH RISK": 0, "DATA MISSING": 1, "REVIEW": 2, "WATCH": 3, "OK": 4})
        if series.name == "risk_bucket"
        else series,
    )


def _build_exceptions(report: pd.DataFrame) -> pd.DataFrame:
    exception_rows: list[dict[str, Any]] = []
    for row in report.itertuples(index=False):
        types = [row.update_gap_type] if row.update_gap_type != "OK" else []
        if row.evidence_status == "NO ACTUAL EVENT EVIDENCE" and "NO ACTUAL EVENT EVIDENCE" not in types:
            types.append("NO ACTUAL EVENT EVIDENCE")
        if row.sequence_status == "OUT OF SEQUENCE" and "OUT OF SEQUENCE" not in types:
            types.append("OUT OF SEQUENCE")
        for exception_type in types:
            exception_rows.append(
                {
                    "trip_id": row.trip_id,
                    "vehicle_id": row.vehicle_id,
                    "driver_name": row.driver_name,
                    "carrier_name": row.carrier_name,
                    "customer_name": row.customer_name,
                    "expected_status": row.expected_status,
                    "actual_status": row.actual_status,
                    "exception_type": exception_type,
                    "severity": _severity(exception_type, exception_type == "EARLY UPDATE"),
                    "evidence": row.evidence,
                    "suggested_action": _action_for(exception_type, row.evidence_status),
                }
            )
    return pd.DataFrame(exception_rows, columns=EXCEPTION_COLUMNS)


def run_update_pulse(
    trips: pd.DataFrame,
    updates: pd.DataFrame,
    visit_events: pd.DataFrame | None = None,
    settings: UpdatePulseSettings | None = None,
) -> UpdatePulseResult:
    """Run UpdatePulse and return report, exception rows, and KPIs."""
    report = build_update_discipline_report(trips, updates, visit_events, settings=settings)
    exceptions = _build_exceptions(report)
    kpis = {
        "total_trips": int(report["trip_id"].nunique()),
        "total_expected_updates": int(len(report)),
        "update_exceptions": int(len(exceptions)),
        "missing_updates": int((exceptions["exception_type"] == "MISSING UPDATE").sum())
        if not exceptions.empty
        else 0,
        "late_updates": int((exceptions["exception_type"] == "LATE UPDATE").sum()) if not exceptions.empty else 0,
        "out_of_sequence_cases": int((exceptions["exception_type"] == "OUT OF SEQUENCE").sum())
        if not exceptions.empty
        else 0,
        "average_update_delay_minutes": float(
            round(report["update_delay_minutes"].dropna().mean(), 2)
            if not report["update_delay_minutes"].dropna().empty
            else 0
        ),
    }
    return UpdatePulseResult(
        update_discipline_report=report.reset_index(drop=True),
        update_exceptions=exceptions.reset_index(drop=True),
        kpis=kpis,
    )


def write_outputs(result: UpdatePulseResult, output_dir: Path) -> tuple[Path, Path]:
    """Write UpdatePulse CSV exports and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "update_discipline_report.csv"
    exceptions_path = output_dir / "update_exceptions.csv"
    result.update_discipline_report.to_csv(report_path, index=False)
    result.update_exceptions.to_csv(exceptions_path, index=False)
    return report_path, exceptions_path
