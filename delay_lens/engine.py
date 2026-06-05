"""Deterministic delay-cause classification engine for DelayLens."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from delay_lens.models import DelayLensSettings, LaneBaselineRecord, TripRecord, VisitEventRecord


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
REQUIRED_BASELINE_COLUMNS = {"baseline_minutes"}
ORIGIN_TYPES = {"ORIGIN", "HUB", "PICKUP"}
DESTINATION_TYPES = {"DESTINATION", "CUSTOMER", "DELIVERY"}
HUB_TYPES = {"HUB", "CROSSDOCK", "DEPOT", "WAREHOUSE", "PORT"}
REPORT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "lane_id",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
    "actual_origin_exit",
    "actual_destination_entry",
    "departure_delay_minutes",
    "arrival_delay_minutes",
    "origin_dwell_minutes",
    "hub_dwell_minutes",
    "destination_dwell_minutes",
    "travel_minutes",
    "baseline_minutes",
    "baseline_delta_minutes",
    "primary_delay_reason",
    "secondary_delay_flags",
    "risk_bucket",
    "severity",
    "evidence",
    "suggested_action",
]
CRITICAL_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "lane_id",
    "primary_delay_reason",
    "severity",
    "evidence",
    "suggested_action",
]


@dataclass(frozen=True)
class DelayLensResult:
    """Structured outputs from a DelayLens run."""

    delay_classification_report: pd.DataFrame
    critical_delays: pd.DataFrame
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


def _normalize_search(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return "".join(character for character in text.upper() if character.isalnum())


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
    """Normalize, timestamp-standardize, and validate uploaded trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["customer_name", "carrier_name", "lane_id"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["lane_id"] = source["lane_id"].map(_normalize_key)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(
        subset=[
            "trip_id",
            "vehicle_id",
            "origin",
            "destination",
            "planned_departure",
            "promised_arrival",
        ]
    ).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                lane_id=None if pd.isna(row.lane_id) else row.lane_id,
                origin=str(row.origin),
                destination=str(row.destination),
                planned_departure=row.planned_departure.to_pydatetime(),
                promised_arrival=row.promised_arrival.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"trips contains invalid rows: {errors[0]}")

    return source[
        [
            "trip_id",
            "vehicle_id",
            "customer_name",
            "carrier_name",
            "lane_id",
            "origin",
            "destination",
            "planned_departure",
            "promised_arrival",
        ]
    ].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_visit_events(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize GeoReplay visit events and standardize timestamps to UTC."""
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

    return source[
        [
            "trip_id",
            "vehicle_id",
            "geofence_id",
            "geofence_name",
            "geofence_type",
            "enter_time",
            "exit_time",
            "dwell_minutes",
        ]
    ].sort_values(["vehicle_id", "enter_time", "exit_time"]).reset_index(drop=True)


def prepare_lane_baselines(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional lane baseline rows."""
    columns = [
        "lane_id",
        "origin",
        "destination",
        "baseline_minutes",
        "p50_minutes",
        "p75_minutes",
        "p90_minutes",
        "sample_size",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns + ["origin_key", "destination_key"])

    source = _normalize_columns(df).dropna(how="all").copy()
    for column in columns:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_BASELINE_COLUMNS, "lane_baselines")

    source["lane_id"] = source["lane_id"].map(_normalize_key)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["origin_key"] = source["origin"].map(_normalize_search)
    source["destination_key"] = source["destination"].map(_normalize_search)
    for column in ["baseline_minutes", "p50_minutes", "p75_minutes", "p90_minutes", "sample_size"]:
        source[column] = pd.to_numeric(source[column], errors="coerce")
    source = source.dropna(subset=["baseline_minutes"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            LaneBaselineRecord(
                lane_id=row.lane_id,
                origin=row.origin,
                destination=row.destination,
                baseline_minutes=float(row.baseline_minutes),
                p50_minutes=None if pd.isna(row.p50_minutes) else float(row.p50_minutes),
                p75_minutes=None if pd.isna(row.p75_minutes) else float(row.p75_minutes),
                p90_minutes=None if pd.isna(row.p90_minutes) else float(row.p90_minutes),
                sample_size=None if pd.isna(row.sample_size) else int(row.sample_size),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"lane_baselines contains invalid rows: {errors[0]}")

    return source[columns + ["origin_key", "destination_key"]].reset_index(drop=True)


def _trip_visit_candidates(trip: pd.Series, visit_events: pd.DataFrame) -> pd.DataFrame:
    exact = visit_events[visit_events["trip_id"] == trip.trip_id].copy()
    if not exact.empty:
        return exact

    window_start = trip.planned_departure - pd.Timedelta(hours=6)
    window_end = trip.promised_arrival + pd.Timedelta(hours=24)
    candidates = visit_events[
        (visit_events["vehicle_id"] == trip.vehicle_id)
        & (
            visit_events["enter_time"].between(window_start, window_end, inclusive="both")
            | visit_events["exit_time"].between(window_start, window_end, inclusive="both")
        )
    ].copy()
    return candidates


def _name_matches(site_name: str | None, target_name: str | None) -> bool:
    site = _normalize_search(site_name)
    target = _normalize_search(target_name)
    return bool(site and target and (site in target or target in site))


def _pick_origin_event(trip: pd.Series, candidates: pd.DataFrame) -> pd.Series | None:
    name_matches = (
        candidates["geofence_name"]
        .map(lambda value: _name_matches(value, trip.origin))
        .fillna(False)
        .astype(bool)
    )
    matches = candidates[candidates["geofence_type"].isin(ORIGIN_TYPES) | name_matches].copy()
    if matches.empty:
        return None
    timed = matches[matches["exit_time"].notna()].sort_values(["exit_time", "enter_time"])
    return timed.iloc[0] if not timed.empty else matches.iloc[0]


def _pick_destination_event(
    trip: pd.Series,
    candidates: pd.DataFrame,
    origin_event: pd.Series | None,
) -> pd.Series | None:
    name_matches = candidates["geofence_name"].map(
        lambda value: _name_matches(value, trip.destination)
    ).fillna(False).astype(bool)
    matches = candidates[candidates["geofence_type"].isin(DESTINATION_TYPES) | name_matches].copy()
    if matches.empty:
        return None
    if origin_event is not None and pd.notna(origin_event.get("exit_time")):
        after_origin = matches[matches["enter_time"] >= origin_event["exit_time"]]
        if not after_origin.empty:
            matches = after_origin
    timed = matches[matches["enter_time"].notna()].sort_values(["enter_time", "exit_time"])
    return timed.iloc[0] if not timed.empty else matches.iloc[0]


def _hub_events(
    candidates: pd.DataFrame,
    origin_event: pd.Series | None,
    destination_event: pd.Series | None,
) -> pd.DataFrame:
    hubs = candidates[candidates["geofence_type"].isin(HUB_TYPES)].copy()
    excluded_ids = set()
    for event in [origin_event, destination_event]:
        if event is not None and event.name is not None:
            excluded_ids.add(event.name)
    return hubs.drop(index=[index for index in excluded_ids if index in hubs.index], errors="ignore")


def _matching_baseline(trip: pd.Series, lane_baselines: pd.DataFrame) -> pd.Series | None:
    if lane_baselines.empty:
        return None

    candidates = lane_baselines.copy()
    lane_id = _normalize_key(trip.lane_id)
    if lane_id:
        lane_matches = candidates[candidates["lane_id"] == lane_id]
        if not lane_matches.empty:
            candidates = lane_matches
        else:
            candidates = candidates[candidates["lane_id"].isna()]

    origin_key = _normalize_search(trip.origin)
    destination_key = _normalize_search(trip.destination)
    exact = candidates[
        (candidates["origin_key"].isna() | (candidates["origin_key"] == origin_key))
        & (candidates["destination_key"].isna() | (candidates["destination_key"] == destination_key))
    ]
    if not exact.empty:
        return exact.iloc[0]
    return candidates.iloc[0] if lane_id and not candidates.empty else None


def _reason_priority(reason: str) -> int:
    priority = {
        "MISSING SIGNAL": 1,
        "LATE DEPARTURE": 2,
        "ORIGIN DWELL": 3,
        "HUB DWELL": 4,
        "ENROUTE DELAY": 5,
        "DESTINATION DWELL": 6,
        "BASELINE MISMATCH": 7,
        "BASELINE MISSING": 8,
        "ON TRACK": 99,
    }
    return priority.get(reason, 50)


def _classify_row(
    trip: pd.Series,
    origin_event: pd.Series | None,
    destination_event: pd.Series | None,
    hubs: pd.DataFrame,
    baseline: pd.Series | None,
    settings: DelayLensSettings,
) -> dict[str, Any]:
    actual_origin_exit = origin_event["exit_time"] if origin_event is not None else pd.NaT
    actual_destination_entry = (
        destination_event["enter_time"] if destination_event is not None else pd.NaT
    )
    departure_delay = _minutes_between(actual_origin_exit, trip.planned_departure)
    arrival_delay = _minutes_between(actual_destination_entry, trip.promised_arrival)
    origin_dwell = float(origin_event["dwell_minutes"]) if origin_event is not None else None
    destination_dwell = (
        float(destination_event["dwell_minutes"]) if destination_event is not None else None
    )
    hub_dwell = round(float(hubs["dwell_minutes"].fillna(0).sum()), 2) if not hubs.empty else 0.0

    elapsed_minutes = _minutes_between(actual_destination_entry, actual_origin_exit)
    travel_minutes = None
    if elapsed_minutes is not None:
        travel_minutes = round(max(elapsed_minutes - hub_dwell, 0.0), 2)

    baseline_minutes = float(baseline["baseline_minutes"]) if baseline is not None else None
    baseline_delta = None
    if travel_minutes is not None and baseline_minutes is not None:
        baseline_delta = round(travel_minutes - baseline_minutes, 2)

    flags: list[str] = []
    if origin_event is None or destination_event is None:
        flags.append("MISSING SIGNAL")
    if departure_delay is not None and departure_delay > settings.late_departure_tolerance_minutes:
        flags.append("LATE DEPARTURE")
    if arrival_delay is not None and arrival_delay > settings.late_arrival_tolerance_minutes:
        flags.append("LATE ARRIVAL")
    if origin_dwell is not None and origin_dwell > settings.origin_dwell_threshold_minutes:
        flags.append("ORIGIN DWELL")
    if hub_dwell > settings.hub_dwell_threshold_minutes:
        flags.append("HUB DWELL")
    if destination_dwell is not None and destination_dwell > settings.destination_dwell_threshold_minutes:
        flags.append("DESTINATION DWELL")
    if baseline_minutes is None:
        flags.append("BASELINE MISSING")
    elif baseline_delta is not None and baseline_delta > settings.baseline_delta_threshold_minutes:
        flags.append("ENROUTE DELAY")

    delay_flags = [flag for flag in flags if flag not in {"LATE ARRIVAL"}]
    primary_delay_reason = min(delay_flags, key=_reason_priority) if delay_flags else "ON TRACK"
    if (
        primary_delay_reason == "BASELINE MISSING"
        and arrival_delay is not None
        and arrival_delay > settings.late_arrival_tolerance_minutes
    ):
        primary_delay_reason = "BASELINE MISMATCH"
    secondary_flags = [flag for flag in flags if flag != primary_delay_reason]

    if primary_delay_reason == "ON TRACK":
        risk_bucket = "OK"
        severity = "OK"
        suggested_action = "No delay review needed."
    elif primary_delay_reason == "MISSING SIGNAL":
        risk_bucket = "DATA MISSING"
        severity = "HIGH"
        suggested_action = "Check GeoReplay coverage or request missing visit evidence."
    elif primary_delay_reason in {"LATE DEPARTURE", "ENROUTE DELAY", "HUB DWELL"}:
        risk_bucket = "HIGH RISK"
        severity = "HIGH"
        suggested_action = "Review the trip timeline and confirm where recovery action is needed."
    elif primary_delay_reason in {"ORIGIN DWELL", "DESTINATION DWELL", "BASELINE MISMATCH"}:
        risk_bucket = "REVIEW"
        severity = "MEDIUM"
        suggested_action = "Review site dwell and baseline evidence before escalation."
    else:
        risk_bucket = "WATCH"
        severity = "LOW"
        suggested_action = "Maintain visibility and improve baseline coverage."

    evidence_parts = []
    if departure_delay is not None:
        evidence_parts.append(f"departure delay {departure_delay:.0f} min")
    if arrival_delay is not None:
        evidence_parts.append(f"arrival delay {arrival_delay:.0f} min")
    if origin_dwell is not None:
        evidence_parts.append(f"origin dwell {origin_dwell:.0f} min")
    evidence_parts.append(f"hub dwell {hub_dwell:.0f} min")
    if destination_dwell is not None:
        evidence_parts.append(f"destination dwell {destination_dwell:.0f} min")
    if baseline_delta is not None:
        evidence_parts.append(f"baseline delta {baseline_delta:.0f} min")
    elif baseline_minutes is None:
        evidence_parts.append("baseline missing")

    return {
        "trip_id": trip.trip_id,
        "vehicle_id": trip.vehicle_id,
        "customer_name": trip.customer_name,
        "carrier_name": trip.carrier_name,
        "lane_id": trip.lane_id,
        "origin": trip.origin,
        "destination": trip.destination,
        "planned_departure": trip.planned_departure,
        "promised_arrival": trip.promised_arrival,
        "actual_origin_exit": actual_origin_exit,
        "actual_destination_entry": actual_destination_entry,
        "departure_delay_minutes": departure_delay,
        "arrival_delay_minutes": arrival_delay,
        "origin_dwell_minutes": origin_dwell,
        "hub_dwell_minutes": hub_dwell,
        "destination_dwell_minutes": destination_dwell,
        "travel_minutes": travel_minutes,
        "baseline_minutes": baseline_minutes,
        "baseline_delta_minutes": baseline_delta,
        "primary_delay_reason": primary_delay_reason,
        "secondary_delay_flags": "; ".join(secondary_flags) if secondary_flags else "None",
        "risk_bucket": risk_bucket,
        "severity": severity,
        "evidence": "; ".join(evidence_parts),
        "suggested_action": suggested_action,
    }


def run_delay_lens(
    trips_df: pd.DataFrame,
    visit_events_df: pd.DataFrame,
    lane_baselines_df: pd.DataFrame | None = None,
    settings: DelayLensSettings | None = None,
) -> DelayLensResult:
    """Run DelayLens classification and return report, critical rows, and KPIs."""
    settings = settings or DelayLensSettings()
    trips = prepare_trips(trips_df)
    visits = prepare_visit_events(visit_events_df)
    baselines = prepare_lane_baselines(lane_baselines_df)

    rows: list[dict[str, Any]] = []
    for trip in trips.itertuples(index=False):
        trip_series = pd.Series(trip._asdict())
        candidates = _trip_visit_candidates(trip_series, visits)
        origin_event = _pick_origin_event(trip_series, candidates)
        destination_event = _pick_destination_event(trip_series, candidates, origin_event)
        hubs = _hub_events(candidates, origin_event, destination_event)
        baseline = _matching_baseline(trip_series, baselines)
        rows.append(
            _classify_row(
                trip_series,
                origin_event,
                destination_event,
                hubs,
                baseline,
                settings,
            )
        )

    report = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    critical = report[report["severity"].isin(["HIGH", "MEDIUM"])][CRITICAL_COLUMNS].reset_index(
        drop=True
    )
    kpis = {
        "total_trips": float(len(report)),
        "delayed_trips": float((report["primary_delay_reason"] != "ON TRACK").sum()),
        "critical_delays": float((report["severity"] == "HIGH").sum()),
        "missing_signal": float((report["primary_delay_reason"] == "MISSING SIGNAL").sum()),
        "baseline_missing": float(
            report["secondary_delay_flags"].str.contains("BASELINE MISSING", regex=False).sum()
            + (report["primary_delay_reason"] == "BASELINE MISSING").sum()
        ),
        "average_arrival_delay_minutes": float(
            report["arrival_delay_minutes"].dropna().clip(lower=0).mean()
            if report["arrival_delay_minutes"].notna().any()
            else 0
        ),
    }
    return DelayLensResult(
        delay_classification_report=report,
        critical_delays=critical,
        kpis=kpis,
    )


def write_outputs(result: DelayLensResult, output_dir: Path | str) -> tuple[Path, Path]:
    """Write DelayLens CSV outputs and return their paths."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / "delay_classification_report.csv"
    critical_path = output_path / "critical_delays.csv"
    result.delay_classification_report.to_csv(report_path, index=False)
    result.critical_delays.to_csv(critical_path, index=False)
    return report_path, critical_path
