"""Deterministic TMS and driver update discipline engine for UpdatePulse."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from update_pulse.models import TripRecord, UpdateRecord, VisitEventRecord


REQUIRED_TRIP_COLUMNS = {
    "trip_id",
    "vehicle_id",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
}
REQUIRED_UPDATE_COLUMNS = {"vehicle_id", "update_time", "status"}
REQUIRED_VISIT_COLUMNS = {
    "vehicle_id",
    "geofence_name",
    "geofence_type",
    "enter_time",
    "exit_time",
}
STATUS_ORDER = ["NEEDS REVIEW", "UPDATE GAP", "OK"]
MILESTONE_STATUS = {
    "ORIGIN DEPARTURE": {"DEPARTED", "STARTED", "LOADED", "PICKED UP", "PICKUP COMPLETE"},
    "DESTINATION ARRIVAL": {"ARRIVED", "DELIVERED", "DELIVERY COMPLETE", "UNLOADED"},
}
STATUS_ALIASES = {
    "DEPART": "DEPARTED",
    "DEPARTED ORIGIN": "DEPARTED",
    "START TRIP": "DEPARTED",
    "STARTED": "DEPARTED",
    "PICKEDUP": "PICKED UP",
    "PICKUP": "PICKED UP",
    "PICKUP COMPLETE": "PICKUP COMPLETE",
    "INTRANSIT": "IN TRANSIT",
    "IN TRANSIT": "IN TRANSIT",
    "ARRIVE": "ARRIVED",
    "ARRIVED DESTINATION": "ARRIVED",
    "DELIVER": "DELIVERED",
    "DELIVERED": "DELIVERED",
    "DELIVERY COMPLETE": "DELIVERY COMPLETE",
}
REPORT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "driver_name",
    "carrier_name",
    "customer_name",
    "origin",
    "destination",
    "milestone",
    "expected_status",
    "planned_time",
    "actual_update_time",
    "update_delay_minutes",
    "event_evidence_time",
    "event_evidence_type",
    "update_count",
    "update_status",
    "exception_type",
    "severity",
    "evidence",
    "suggested_action",
]
EXCEPTION_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "driver_name",
    "carrier_name",
    "milestone",
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
    status = " ".join(text.upper().replace("_", " ").replace("-", " ").split())
    compact = status.replace(" ", "")
    return STATUS_ALIASES.get(status) or STATUS_ALIASES.get(compact) or status


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _minutes_between(actual: pd.Timestamp | pd.NaT, planned: pd.Timestamp) -> float | None:
    if pd.isna(actual) or pd.isna(planned):
        return None
    return round((actual - planned).total_seconds() / 60, 2)


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

    errors: list[str] = []
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
            errors.append(str(exc))
    if errors:
        raise ValueError(f"trips contains invalid rows: {errors[0]}")

    columns = [
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
    return source[columns].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_updates(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timestamp-standardize, and validate uploaded update rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    if "driver_update_time" in source.columns and "update_time" not in source.columns:
        source["update_time"] = source["driver_update_time"]
    if "tms_update_time" in source.columns and "update_time" not in source.columns:
        source["update_time"] = source["tms_update_time"]
    if "update_status" in source.columns and "status" not in source.columns:
        source["status"] = source["update_status"]
    for column in ["update_id", "trip_id", "source", "note"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_UPDATE_COLUMNS, "updates")

    source["update_id"] = source["update_id"].map(_normalize_text)
    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["update_time"] = _to_utc(source["update_time"])
    source["status"] = source["status"].map(_normalize_status)
    source["source"] = source["source"].map(_normalize_text)
    source["note"] = source["note"].map(_normalize_text)
    source = source.dropna(subset=["vehicle_id", "update_time", "status"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            UpdateRecord(
                update_id=row.update_id,
                trip_id=None if pd.isna(row.trip_id) else row.trip_id,
                vehicle_id=str(row.vehicle_id),
                update_time=row.update_time.to_pydatetime(),
                status=str(row.status),
                source=None if pd.isna(row.source) else row.source,
                note=None if pd.isna(row.note) else row.note,
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"updates contains invalid rows: {errors[0]}")

    return source[["update_id", "trip_id", "vehicle_id", "update_time", "status", "source", "note"]].reset_index(drop=True)


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

    errors: list[str] = []
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
            errors.append(str(exc))
    if errors:
        raise ValueError(f"visit_events contains invalid rows: {errors[0]}")

    return source[columns].reset_index(drop=True)


def _candidate_updates(
    trip: pd.Series,
    updates: pd.DataFrame,
    accepted_statuses: set[str],
    planned_time: pd.Timestamp,
    window_hours: float,
) -> pd.DataFrame:
    trip_updates = updates[
        ((updates["trip_id"] == trip.trip_id) | updates["trip_id"].isna())
        & (updates["vehicle_id"] == trip.vehicle_id)
        & updates["status"].isin(accepted_statuses)
    ].copy()
    if trip_updates.empty:
        return trip_updates
    trip_updates["minutes_from_plan"] = (
        (trip_updates["update_time"] - planned_time).dt.total_seconds().div(60).abs()
    )
    return trip_updates[trip_updates["minutes_from_plan"] <= window_hours * 60].sort_values(
        ["minutes_from_plan", "update_time"]
    )


def _trip_updates(trip: pd.Series, updates: pd.DataFrame) -> pd.DataFrame:
    return updates[
        ((updates["trip_id"] == trip.trip_id) | updates["trip_id"].isna())
        & (updates["vehicle_id"] == trip.vehicle_id)
        & (updates["update_time"] >= trip.planned_departure - pd.Timedelta(hours=6))
        & (updates["update_time"] <= trip.promised_arrival + pd.Timedelta(hours=12))
    ].sort_values("update_time")


def _sequence_issue(trip_updates: pd.DataFrame) -> bool:
    rank = {"DEPARTED": 1, "PICKED UP": 1, "PICKUP COMPLETE": 1, "IN TRANSIT": 2, "ARRIVED": 3, "DELIVERED": 3, "DELIVERY COMPLETE": 3}
    ranks = [rank[status] for status in trip_updates["status"] if status in rank]
    return any(current < previous for previous, current in zip(ranks, ranks[1:]))


def _event_evidence(
    trip: pd.Series,
    visits: pd.DataFrame,
    milestone: str,
    planned_time: pd.Timestamp,
    event_window_hours: float,
) -> tuple[pd.Timestamp | pd.NaT, str]:
    if visits.empty:
        return pd.NaT, "not provided"
    type_set = {"ORIGIN", "HUB", "PICKUP"} if milestone == "ORIGIN DEPARTURE" else {"DESTINATION", "CUSTOMER", "DELIVERY"}
    time_column = "exit_time" if milestone == "ORIGIN DEPARTURE" else "enter_time"
    trip_visits = visits[
        ((visits["trip_id"] == trip.trip_id) | visits["trip_id"].isna())
        & (visits["vehicle_id"] == trip.vehicle_id)
        & visits["geofence_type"].isin(type_set)
    ].copy()
    trip_visits = trip_visits[trip_visits[time_column].notna()].copy()
    if trip_visits.empty:
        return pd.NaT, "no actual event evidence"
    trip_visits["minutes_from_plan"] = (
        (trip_visits[time_column] - planned_time).dt.total_seconds().div(60).abs()
    )
    trip_visits = trip_visits[trip_visits["minutes_from_plan"] <= event_window_hours * 60]
    if trip_visits.empty:
        return pd.NaT, "no actual event evidence"
    best = trip_visits.sort_values(["minutes_from_plan", time_column]).iloc[0]
    return best[time_column], f"{best.geofence_type} visit"


def _status_from_flags(flags: list[str]) -> str:
    if not flags:
        return "OK"
    if "missing update" in flags:
        return "UPDATE GAP"
    return "NEEDS REVIEW"


def _severity(flags: list[str]) -> str:
    high = {"missing update", "sequence issue", "late update"}
    return "HIGH" if any(flag in high for flag in flags) else "MEDIUM"


def build_update_discipline_report(
    trips: pd.DataFrame,
    updates: pd.DataFrame,
    visit_events: pd.DataFrame | None = None,
    grace_minutes: float = 15,
    early_threshold_minutes: float = 30,
    match_window_hours: float = 8,
    event_window_hours: float = 8,
) -> pd.DataFrame:
    """Build one update discipline row per expected trip milestone."""
    prepared_trips = prepare_trips(trips)
    prepared_updates = prepare_updates(updates)
    prepared_visits = prepare_visit_events(visit_events)
    rows: list[dict[str, Any]] = []

    for trip in prepared_trips.itertuples(index=False):
        trip_series = pd.Series(trip._asdict())
        all_trip_updates = _trip_updates(trip_series, prepared_updates)
        has_sequence_issue = _sequence_issue(all_trip_updates)
        milestones = [
            ("ORIGIN DEPARTURE", "DEPARTED", trip.planned_departure),
            ("DESTINATION ARRIVAL", "ARRIVED", trip.promised_arrival),
        ]

        for milestone, expected_status, planned_time in milestones:
            candidates = _candidate_updates(
                trip_series,
                prepared_updates,
                MILESTONE_STATUS[milestone],
                planned_time,
                match_window_hours,
            )
            actual_update_time = pd.NaT if candidates.empty else candidates.iloc[0]["update_time"]
            update_count = int(len(candidates))
            delay = _minutes_between(actual_update_time, planned_time)
            event_time, event_type = _event_evidence(
                trip_series,
                prepared_visits,
                milestone,
                planned_time,
                event_window_hours,
            )

            flags: list[str] = []
            if pd.isna(actual_update_time):
                flags.append("missing update")
            elif delay is not None and delay > grace_minutes:
                flags.append("late update")
            elif delay is not None and delay < -early_threshold_minutes:
                flags.append("early update")
            if update_count > 1:
                flags.append("duplicate update")
            if has_sequence_issue:
                flags.append("sequence issue")
            if not prepared_visits.empty and pd.isna(event_time):
                flags.append("no actual event evidence")

            exception_type = "; ".join(flags) if flags else "none"
            update_status = _status_from_flags(flags)
            evidence_parts = [
                f"Expected {expected_status} around {planned_time}",
                "no matching update found"
                if pd.isna(actual_update_time)
                else f"matched update at {actual_update_time}",
            ]
            if delay is not None:
                evidence_parts.append(f"{delay:+.0f} minutes vs plan")
            evidence_parts.append(
                f"event evidence: {event_time} ({event_type})"
                if pd.notna(event_time)
                else f"event evidence: {event_type}"
            )

            rows.append(
                {
                    "trip_id": trip.trip_id,
                    "vehicle_id": trip.vehicle_id,
                    "driver_name": trip.driver_name,
                    "carrier_name": trip.carrier_name,
                    "customer_name": trip.customer_name,
                    "origin": trip.origin,
                    "destination": trip.destination,
                    "milestone": milestone,
                    "expected_status": expected_status,
                    "planned_time": planned_time,
                    "actual_update_time": actual_update_time,
                    "update_delay_minutes": delay,
                    "event_evidence_time": event_time,
                    "event_evidence_type": event_type,
                    "update_count": update_count,
                    "update_status": update_status,
                    "exception_type": exception_type,
                    "severity": "LOW" if not flags else _severity(flags),
                    "evidence": "; ".join(evidence_parts),
                    "suggested_action": "No action needed"
                    if not flags
                    else "Review update timing with dispatch and compare against event evidence",
                }
            )

    return pd.DataFrame(rows, columns=REPORT_COLUMNS).sort_values(
        ["update_status", "trip_id", "planned_time"],
        key=lambda series: series.map({status: index for index, status in enumerate(STATUS_ORDER)})
        if series.name == "update_status"
        else series,
    )


def run_update_pulse(
    trips: pd.DataFrame,
    updates: pd.DataFrame,
    visit_events: pd.DataFrame | None = None,
    grace_minutes: float = 15,
    early_threshold_minutes: float = 30,
    match_window_hours: float = 8,
    event_window_hours: float = 8,
) -> UpdatePulseResult:
    """Run UpdatePulse and return report, exception rows, and KPIs."""
    report = build_update_discipline_report(
        trips,
        updates,
        visit_events,
        grace_minutes=grace_minutes,
        early_threshold_minutes=early_threshold_minutes,
        match_window_hours=match_window_hours,
        event_window_hours=event_window_hours,
    )
    exceptions = report[report["exception_type"] != "none"].copy()[EXCEPTION_COLUMNS]
    kpis = {
        "total_milestones": int(len(report)),
        "ok_milestones": int((report["update_status"] == "OK").sum()),
        "update_gaps": int(report["exception_type"].str.contains("missing update").sum()),
        "late_updates": int(report["exception_type"].str.contains("late update").sum()),
        "early_updates": int(report["exception_type"].str.contains("early update").sum()),
        "duplicate_updates": int(report["exception_type"].str.contains("duplicate update").sum()),
        "sequence_issues": int(report["exception_type"].str.contains("sequence issue").sum()),
        "no_event_evidence": int(
            report["exception_type"].str.contains("no actual event evidence").sum()
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
