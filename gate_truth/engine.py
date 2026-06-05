"""Deterministic trip gate verification engine for GateTruth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from gate_truth.models import PlannedStopRecord, TripRecord, VisitEventRecord


REQUIRED_TRIP_COLUMNS = {
    "trip_id",
    "vehicle_id",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
}
REQUIRED_VISIT_COLUMNS = {
    "vehicle_id",
    "geofence_id",
    "geofence_name",
    "geofence_type",
    "enter_time",
    "exit_time",
    "dwell_minutes",
}
REQUIRED_STOP_COLUMNS = {"trip_id", "vehicle_id", "geofence_id", "stop_sequence", "stop_type"}
STATUS_ORDER = ["EXCEPTION", "AMBIGUOUS MATCH", "INCOMPLETE", "OK"]
ORIGIN_TYPES = {"ORIGIN", "HUB", "PICKUP"}
DESTINATION_TYPES = {"DESTINATION", "CUSTOMER", "DELIVERY"}
REPORT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
    "actual_origin_entry",
    "actual_origin_exit",
    "actual_destination_entry",
    "actual_destination_exit",
    "start_delay_minutes",
    "arrival_delay_minutes",
    "gate_truth_status",
    "exception_type",
    "evidence",
    "confidence_bucket",
    "origin_geofence_id",
    "origin_geofence_name",
    "destination_geofence_id",
    "destination_geofence_name",
    "origin_candidate_count",
    "destination_candidate_count",
    "suggested_action",
]
EXCEPTION_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "exception_type",
    "severity",
    "evidence",
    "suggested_action",
]


@dataclass(frozen=True)
class GateTruthResult:
    """Structured outputs from a GateTruth run."""

    gate_truth_report: pd.DataFrame
    gate_exceptions: pd.DataFrame
    kpis: dict[str, float]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize uploaded CSV column names to matching-friendly snake_case."""
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return normalized


def _normalize_text(value: Any) -> str | None:
    """Normalize user-facing text while preserving missing operational values."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return " ".join(text.split())


def _normalize_key(value: Any) -> str | None:
    """Normalize identifiers used for joins and deterministic matching."""
    text = _normalize_text(value)
    return None if text is None else text.upper().replace(" ", "")


def _normalize_search(value: Any) -> str | None:
    """Normalize place names for fallback site-name matching."""
    text = _normalize_text(value)
    if text is None:
        return None
    return "".join(character for character in text.upper() if character.isalnum())


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Raise a readable error when an input dataframe is missing required columns."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    """Parse a timestamp series and standardize it to timezone-aware UTC."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timestamp-standardize, and validate GateTruth trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["customer_name", "carrier_name", "origin_geofence_id", "destination_geofence_id"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["origin_geofence_id"] = source["origin_geofence_id"].map(_normalize_key)
    source["destination_geofence_id"] = source["destination_geofence_id"].map(_normalize_key)
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(subset=["trip_id", "vehicle_id", "origin", "destination"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                customer_name=row.customer_name,
                carrier_name=row.carrier_name,
                origin=str(row.origin),
                destination=str(row.destination),
                origin_geofence_id=None
                if pd.isna(row.origin_geofence_id)
                else row.origin_geofence_id,
                destination_geofence_id=None
                if pd.isna(row.destination_geofence_id)
                else row.destination_geofence_id,
                planned_departure=None
                if pd.isna(row.planned_departure)
                else row.planned_departure.to_pydatetime(),
                promised_arrival=None
                if pd.isna(row.promised_arrival)
                else row.promised_arrival.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"trips contains invalid rows: {errors[0]}")

    columns = [
        "trip_id",
        "vehicle_id",
        "customer_name",
        "carrier_name",
        "origin",
        "destination",
        "origin_geofence_id",
        "destination_geofence_id",
        "planned_departure",
        "promised_arrival",
    ]
    return source[columns].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_visit_events(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timestamp-standardize, and validate GeoReplay visit events."""
    source = _normalize_columns(df).dropna(how="all").copy()
    if "trip_id" not in source.columns:
        source["trip_id"] = pd.NA
    if "entry_time" in source.columns and "enter_time" not in source.columns:
        source["enter_time"] = source["entry_time"]
    _require_columns(source, REQUIRED_VISIT_COLUMNS, "visit_events")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["geofence_id"] = source["geofence_id"].map(_normalize_key)
    source["geofence_name"] = source["geofence_name"].map(_normalize_text)
    source["geofence_type"] = source["geofence_type"].map(_normalize_key)
    source["enter_time"] = _to_utc(source["enter_time"])
    source["exit_time"] = _to_utc(source["exit_time"])
    source["dwell_minutes"] = pd.to_numeric(source["dwell_minutes"], errors="coerce")

    has_times = source["enter_time"].notna() & source["exit_time"].notna()
    missing_dwell = source["dwell_minutes"].isna() & has_times
    source.loc[missing_dwell, "dwell_minutes"] = (
        (source.loc[missing_dwell, "exit_time"] - source.loc[missing_dwell, "enter_time"])
        .dt.total_seconds()
        .div(60)
        .round(2)
    )
    source = source.dropna(subset=["vehicle_id"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            VisitEventRecord(
                trip_id=row.trip_id,
                vehicle_id=str(row.vehicle_id),
                geofence_id=row.geofence_id,
                geofence_name=row.geofence_name,
                geofence_type=row.geofence_type,
                enter_time=None if pd.isna(row.enter_time) else row.enter_time.to_pydatetime(),
                exit_time=None if pd.isna(row.exit_time) else row.exit_time.to_pydatetime(),
                dwell_minutes=None if pd.isna(row.dwell_minutes) else float(row.dwell_minutes),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"visit_events contains invalid rows: {errors[0]}")

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
    return source[columns].reset_index(drop=True)


def prepare_planned_stops(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional planned stops used for origin/destination geofence hints."""
    columns = [
        "trip_id",
        "vehicle_id",
        "geofence_id",
        "stop_sequence",
        "stop_type",
        "planned_arrival",
        "planned_departure",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["planned_arrival", "planned_departure"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_STOP_COLUMNS, "planned_stops")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["geofence_id"] = source["geofence_id"].map(_normalize_key)
    source["stop_sequence"] = pd.to_numeric(source["stop_sequence"], errors="coerce")
    source["stop_type"] = source["stop_type"].map(_normalize_key)
    source["planned_arrival"] = _to_utc(source["planned_arrival"])
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source = source.dropna(subset=["trip_id", "vehicle_id", "geofence_id"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            PlannedStopRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                geofence_id=str(row.geofence_id),
                stop_sequence=None if pd.isna(row.stop_sequence) else int(row.stop_sequence),
                stop_type=None if pd.isna(row.stop_type) else row.stop_type,
                planned_arrival=None
                if pd.isna(row.planned_arrival)
                else row.planned_arrival.to_pydatetime(),
                planned_departure=None
                if pd.isna(row.planned_departure)
                else row.planned_departure.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"planned_stops contains invalid rows: {errors[0]}")

    return source[columns].reset_index(drop=True)


def _planned_stop_geofence(planned_stops: pd.DataFrame, trip_id: str, role: str) -> str | None:
    """Find the planned stop geofence for a trip role when supplied."""
    if planned_stops.empty:
        return None

    trip_stops = planned_stops[planned_stops["trip_id"] == trip_id].copy()
    if trip_stops.empty:
        return None

    role_stops = trip_stops[trip_stops["stop_type"] == role]
    if not role_stops.empty:
        return str(role_stops.sort_values("stop_sequence").iloc[0]["geofence_id"])

    ordered = trip_stops.sort_values("stop_sequence")
    if role == "ORIGIN":
        return str(ordered.iloc[0]["geofence_id"])
    if role == "DESTINATION":
        return str(ordered.iloc[-1]["geofence_id"])
    return None


def _candidate_visits(
    trip: pd.Series,
    visits: pd.DataFrame,
    planned_stops: pd.DataFrame,
    role: str,
) -> pd.DataFrame:
    """Return visit candidates for one trip and gate role."""
    candidates = visits[visits["vehicle_id"] == trip["vehicle_id"]].copy()
    if candidates.empty:
        return candidates

    exact_trip_candidates = candidates[candidates["trip_id"] == trip["trip_id"]].copy()
    if not exact_trip_candidates.empty:
        candidates = exact_trip_candidates
    else:
        candidates = candidates[candidates["trip_id"].isna()].copy()
        planned_time = trip.get("planned_departure" if role == "ORIGIN" else "promised_arrival")
        timestamp_column = "exit_time" if role == "ORIGIN" else "enter_time"
        if pd.notna(planned_time):
            window_start = planned_time - pd.Timedelta(hours=12)
            window_end = planned_time + pd.Timedelta(hours=36)
            fallback_time = candidates[timestamp_column].fillna(candidates["enter_time"])
            candidates = candidates[(fallback_time >= window_start) & (fallback_time <= window_end)].copy()
    if candidates.empty:
        return candidates

    trip_geofence = trip.get("origin_geofence_id" if role == "ORIGIN" else "destination_geofence_id")
    trip_geofence = None if pd.isna(trip_geofence) else trip_geofence
    stop_geofence = _planned_stop_geofence(planned_stops, str(trip["trip_id"]), role)
    target_geofence = trip_geofence or stop_geofence
    if target_geofence:
        return candidates[candidates["geofence_id"] == target_geofence].copy()

    allowed_types = ORIGIN_TYPES if role == "ORIGIN" else DESTINATION_TYPES
    role_matches = candidates["geofence_type"].isin(allowed_types)
    place_value = trip.get("origin" if role == "ORIGIN" else "destination")
    place_key = _normalize_search(place_value)
    name_matches = pd.Series(False, index=candidates.index)
    if place_key:
        name_matches = candidates["geofence_name"].map(_normalize_search).fillna("").str.contains(
            place_key,
            regex=False,
        )

    return candidates[role_matches | name_matches].copy()


def _select_visit(
    candidates: pd.DataFrame,
    planned_time: pd.Timestamp | pd.NaT,
    role: str,
) -> tuple[pd.Series | None, bool]:
    """Select the most useful candidate and report whether the match is ambiguous."""
    if candidates.empty:
        return None, False

    timestamp_column = "exit_time" if role == "ORIGIN" else "enter_time"
    scored = candidates.copy()
    if pd.notna(planned_time):
        scored["_distance_minutes"] = (
            (scored[timestamp_column] - planned_time).dt.total_seconds().abs().div(60)
        )
    else:
        scored["_distance_minutes"] = pd.NA
    scored["_missing_score_time"] = scored[timestamp_column].isna().astype(int)
    scored["_sort_time"] = scored[timestamp_column].fillna(scored["enter_time"])
    selected = scored.sort_values(
        ["_missing_score_time", "_distance_minutes", "_sort_time"],
        na_position="last",
    ).iloc[0]
    return selected, len(candidates) > 1


def _late_minutes(actual: pd.Timestamp | pd.NaT, planned: pd.Timestamp | pd.NaT) -> float:
    """Return positive minutes late, or zero when either timestamp is missing."""
    if pd.isna(actual) or pd.isna(planned):
        return 0.0
    return max(0.0, round((actual - planned).total_seconds() / 60, 2))


def _early_minutes(actual: pd.Timestamp | pd.NaT, planned: pd.Timestamp | pd.NaT) -> float:
    """Return positive minutes early, or zero when either timestamp is missing."""
    if pd.isna(actual) or pd.isna(planned):
        return 0.0
    return max(0.0, round((planned - actual).total_seconds() / 60, 2))


def _suggested_action(flags: list[str], status: str) -> str:
    """Return a manager-friendly next action for the row."""
    if "AMBIGUOUS MATCH" in flags:
        return "Review candidate visits before confirming gate evidence."
    if "MISSING ORIGIN EXIT" in flags:
        return "Confirm whether the vehicle exited the origin hub."
    if "MISSING DESTINATION ENTRY" in flags:
        return "Check GPS/site evidence for destination arrival."
    if "NO VISIT EVIDENCE" in flags:
        return "Load GeoReplay visit evidence or confirm the trip used the expected vehicle ID."
    if "LATE START" in flags:
        return "Escalate late origin departure with dispatcher or carrier."
    if "LATE ARRIVAL" in flags:
        return "Prepare customer-facing arrival delay explanation."
    if "EARLY ARRIVAL" in flags:
        return "Confirm whether customer receiving accepted the early arrival."
    if status == "INCOMPLETE":
        return "Add planned and visit evidence before closing review."
    return "Gate evidence verified; no exception action needed."


def _status_from_flags(flags: list[str]) -> str:
    """Convert exception flags into the manager-facing gate truth status."""
    if "NO VISIT EVIDENCE" in flags:
        return "INCOMPLETE"
    if "MISSING ORIGIN EXIT" in flags or "MISSING DESTINATION ENTRY" in flags:
        return "INCOMPLETE"
    if "AMBIGUOUS MATCH" in flags:
        return "AMBIGUOUS MATCH"
    if flags:
        return "EXCEPTION"
    return "OK"


def _confidence_bucket(flags: list[str], origin_count: int, destination_count: int) -> str:
    """Classify how reviewable the evidence is without hiding the raw timestamps."""
    if "NO VISIT EVIDENCE" in flags:
        return "NO EVIDENCE"
    if "AMBIGUOUS MATCH" in flags:
        return "REVIEW"
    if "MISSING ORIGIN EXIT" in flags or "MISSING DESTINATION ENTRY" in flags:
        return "LOW"
    if origin_count == 1 and destination_count == 1:
        return "HIGH"
    return "MEDIUM"


def _severity(flags: list[str]) -> str:
    """Return a simple control-tower severity for exception exports."""
    high_flags = {"NO VISIT EVIDENCE", "MISSING DESTINATION ENTRY", "MISSING ORIGIN EXIT"}
    if any(flag in high_flags for flag in flags):
        return "HIGH"
    if "AMBIGUOUS MATCH" in flags or "LATE ARRIVAL" in flags:
        return "MEDIUM"
    return "LOW"


def _evidence_text(
    origin_visit: pd.Series | None,
    destination_visit: pd.Series | None,
    origin_count: int,
    destination_count: int,
) -> str:
    """Build readable evidence text for an analyst reviewing the CSV."""
    if origin_count == 0 and destination_count == 0:
        return "No matching GeoReplay visit evidence found for the vehicle, trip, and time window."

    pieces: list[str] = [
        f"Origin candidates: {origin_count}",
        f"Destination candidates: {destination_count}",
    ]
    if origin_visit is not None:
        pieces.append(
            "origin "
            f"{origin_visit['geofence_name']} entered {origin_visit['enter_time']} "
            f"and exited {origin_visit['exit_time']}"
        )
    if destination_visit is not None:
        pieces.append(
            "destination "
            f"{destination_visit['geofence_name']} entered {destination_visit['enter_time']} "
            f"and exited {destination_visit['exit_time']}"
        )
    return "; ".join(pieces)


def build_gate_truth_report(
    trips: pd.DataFrame,
    visit_events: pd.DataFrame,
    planned_stops: pd.DataFrame | None = None,
    start_grace_minutes: float = 15,
    arrival_grace_minutes: float = 15,
    early_arrival_threshold_minutes: float = 60,
) -> pd.DataFrame:
    """Build the manager-ready GateTruth report from trips and visit events."""
    trip_rows = prepare_trips(trips)
    visits = prepare_visit_events(visit_events)
    stops = prepare_planned_stops(planned_stops)

    rows: list[dict[str, Any]] = []
    for trip in trip_rows.itertuples(index=False):
        trip_series = pd.Series(trip._asdict())
        origin_candidates = _candidate_visits(trip_series, visits, stops, "ORIGIN")
        destination_candidates = _candidate_visits(trip_series, visits, stops, "DESTINATION")
        origin_visit, origin_ambiguous = _select_visit(
            origin_candidates,
            trip_series["planned_departure"],
            "ORIGIN",
        )
        destination_visit, destination_ambiguous = _select_visit(
            destination_candidates,
            trip_series["promised_arrival"],
            "DESTINATION",
        )

        actual_origin_entry = pd.NaT if origin_visit is None else origin_visit["enter_time"]
        actual_origin_exit = pd.NaT if origin_visit is None else origin_visit["exit_time"]
        actual_destination_entry = (
            pd.NaT if destination_visit is None else destination_visit["enter_time"]
        )
        actual_destination_exit = (
            pd.NaT if destination_visit is None else destination_visit["exit_time"]
        )

        start_delay_minutes = _late_minutes(actual_origin_exit, trip_series["planned_departure"])
        arrival_delay_minutes = _late_minutes(
            actual_destination_entry,
            trip_series["promised_arrival"],
        )
        early_arrival_minutes = _early_minutes(
            actual_destination_entry,
            trip_series["promised_arrival"],
        )
        flags: list[str] = []
        if origin_visit is None and destination_visit is None:
            flags.append("NO VISIT EVIDENCE")
        if pd.isna(actual_origin_exit):
            flags.append("MISSING ORIGIN EXIT")
        if pd.isna(actual_destination_entry):
            flags.append("MISSING DESTINATION ENTRY")
        if start_delay_minutes > start_grace_minutes:
            flags.append("LATE START")
        if arrival_delay_minutes > arrival_grace_minutes:
            flags.append("LATE ARRIVAL")
        if early_arrival_minutes > early_arrival_threshold_minutes:
            flags.append("EARLY ARRIVAL")
        if origin_ambiguous or destination_ambiguous:
            flags.append("AMBIGUOUS MATCH")

        status = _status_from_flags(flags)
        origin_count = int(len(origin_candidates))
        destination_count = int(len(destination_candidates))
        exception_type = "; ".join(flags) if flags else "NONE"
        evidence = _evidence_text(origin_visit, destination_visit, origin_count, destination_count)

        rows.append(
            {
                "trip_id": trip_series["trip_id"],
                "vehicle_id": trip_series["vehicle_id"],
                "customer_name": trip_series["customer_name"],
                "carrier_name": trip_series["carrier_name"],
                "origin": trip_series["origin"],
                "destination": trip_series["destination"],
                "planned_departure": trip_series["planned_departure"],
                "promised_arrival": trip_series["promised_arrival"],
                "actual_origin_entry": actual_origin_entry,
                "actual_origin_exit": actual_origin_exit,
                "actual_destination_entry": actual_destination_entry,
                "actual_destination_exit": actual_destination_exit,
                "origin_geofence_id": None if origin_visit is None else origin_visit["geofence_id"],
                "origin_geofence_name": None
                if origin_visit is None
                else origin_visit["geofence_name"],
                "destination_geofence_id": None
                if destination_visit is None
                else destination_visit["geofence_id"],
                "destination_geofence_name": None
                if destination_visit is None
                else destination_visit["geofence_name"],
                "origin_candidate_count": origin_count,
                "destination_candidate_count": destination_count,
                "start_delay_minutes": round(start_delay_minutes, 2),
                "arrival_delay_minutes": round(arrival_delay_minutes, 2),
                "gate_truth_status": status,
                "exception_type": exception_type,
                "evidence": evidence,
                "confidence_bucket": _confidence_bucket(flags, origin_count, destination_count),
                "severity": _severity(flags) if flags else "NONE",
                "suggested_action": _suggested_action(flags, status),
            }
        )

    output = pd.DataFrame(rows)
    order_map = {status: index for index, status in enumerate(STATUS_ORDER)}
    sorted_output = output.sort_values(
        by=["gate_truth_status", "arrival_delay_minutes", "start_delay_minutes"],
        key=lambda series: series.map(order_map) if series.name == "gate_truth_status" else series,
        ascending=[True, False, False],
    ).reset_index(drop=True)
    return sorted_output[REPORT_COLUMNS + ["severity"]]


def run_gate_truth(
    trips: pd.DataFrame,
    visit_events: pd.DataFrame,
    planned_stops: pd.DataFrame | None = None,
    start_grace_minutes: float = 15,
    arrival_grace_minutes: float = 15,
    early_arrival_threshold_minutes: float = 60,
) -> GateTruthResult:
    """Run GateTruth and return report, exception rows, and KPIs."""
    report = build_gate_truth_report(
        trips,
        visit_events,
        planned_stops,
        start_grace_minutes=start_grace_minutes,
        arrival_grace_minutes=arrival_grace_minutes,
        early_arrival_threshold_minutes=early_arrival_threshold_minutes,
    )
    exceptions = report[report["exception_type"] != "NONE"].copy()
    exceptions = exceptions[EXCEPTION_COLUMNS]
    kpis = {
        "total_trips": int(len(report)),
        "confirmed_starts": int(report["actual_origin_exit"].notna().sum()),
        "confirmed_arrivals": int(report["actual_destination_entry"].notna().sum()),
        "verified_trips": int((report["gate_truth_status"] == "OK").sum()),
        "exception_trips": int(len(exceptions)),
        "missing_origin_exits": int(report["exception_type"].str.contains("MISSING ORIGIN EXIT").sum()),
        "missing_destination_entries": int(
            report["exception_type"].str.contains("MISSING DESTINATION ENTRY").sum()
        ),
        "late_starts": int(report["exception_type"].str.contains("LATE START").sum()),
        "late_arrivals": int(report["exception_type"].str.contains("LATE ARRIVAL").sum()),
        "ambiguous_matches": int(report["exception_type"].str.contains("AMBIGUOUS MATCH").sum()),
    }
    return GateTruthResult(gate_truth_report=report, gate_exceptions=exceptions, kpis=kpis)


def write_outputs(result: GateTruthResult, output_dir: Path) -> tuple[Path, Path]:
    """Write GateTruth CSV exports and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "gate_truth_report.csv"
    exceptions_path = output_dir / "gate_exceptions.csv"
    result.gate_truth_report.to_csv(report_path, index=False)
    result.gate_exceptions.to_csv(exceptions_path, index=False)
    return report_path, exceptions_path
