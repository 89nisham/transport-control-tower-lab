"""Deterministic ETA risk engine for ETA Watch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from eta_watch.models import LaneBaselineRecord, TripRecord, VisitEventRecord


REQUIRED_TRIP_COLUMNS = {"trip_id", "vehicle_id", "destination", "promised_arrival"}
REQUIRED_VISIT_COLUMNS = {"vehicle_id", "exit_time"}
RISK_ORDER = ["ON TRACK", "WATCH", "AT RISK", "LATE", "NO SIGNAL"]
DEFAULT_REMAINING_MINUTES = 180.0


@dataclass(frozen=True)
class EtaWatchResult:
    """Structured outputs from an ETA Watch run."""

    risk_board: pd.DataFrame
    late_trips: pd.DataFrame
    kpis: dict[str, int]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize uploaded CSV column names to matching-friendly snake_case."""
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return normalized


def _normalize_text(value: Any) -> str | None:
    """Normalize text values while preserving operational missing values."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return " ".join(text.split())


def _normalize_key(value: Any) -> str | None:
    """Normalize identifiers used for joins and baseline lookups."""
    text = _normalize_text(value)
    return None if text is None else text.upper().replace(" ", "")


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Raise a readable error when an input dataframe is missing required columns."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    """Parse a timestamp series and standardize it to timezone-aware UTC."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timezone-standardize, and validate uploaded trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")
    if "origin" not in source.columns:
        source["origin"] = pd.NA
    if "lane_id" not in source.columns:
        source["lane_id"] = pd.NA
    if "planned_departure" not in source.columns:
        source["planned_departure"] = pd.NaT

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["lane_id"] = source["lane_id"].map(_normalize_key)
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(subset=["trip_id", "vehicle_id", "destination", "promised_arrival"])

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                origin=row.origin,
                destination=str(row.destination),
                lane_id=row.lane_id,
                planned_departure=None
                if pd.isna(row.planned_departure)
                else row.planned_departure.to_pydatetime(),
                promised_arrival=row.promised_arrival.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"trips contains invalid rows: {errors[0]}")

    columns = [
        "trip_id",
        "vehicle_id",
        "origin",
        "destination",
        "lane_id",
        "planned_departure",
        "promised_arrival",
    ]
    return source[columns].sort_values(["promised_arrival", "trip_id"]).reset_index(drop=True)


def prepare_visit_events(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize GeoReplay visit events and standardize event timestamps to UTC."""
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, REQUIRED_VISIT_COLUMNS, "visit_events")
    if "geofence_id" not in source.columns:
        source["geofence_id"] = pd.NA
    if "geofence_name" not in source.columns:
        source["geofence_name"] = pd.NA
    if "entry_time" not in source.columns:
        source["entry_time"] = pd.NaT
    if "dwell_minutes" not in source.columns:
        source["dwell_minutes"] = pd.NA

    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["geofence_id"] = source["geofence_id"].map(_normalize_key)
    source["geofence_name"] = source["geofence_name"].map(_normalize_text)
    source["entry_time"] = _to_utc(source["entry_time"])
    source["exit_time"] = _to_utc(source["exit_time"])
    source["dwell_minutes"] = pd.to_numeric(source["dwell_minutes"], errors="coerce")
    source = source.dropna(subset=["vehicle_id", "exit_time"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            VisitEventRecord(
                vehicle_id=str(row.vehicle_id),
                geofence_id=row.geofence_id,
                geofence_name=row.geofence_name,
                entry_time=None if pd.isna(row.entry_time) else row.entry_time.to_pydatetime(),
                exit_time=row.exit_time.to_pydatetime(),
                dwell_minutes=None if pd.isna(row.dwell_minutes) else float(row.dwell_minutes),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"visit_events contains invalid rows: {errors[0]}")

    columns = [
        "vehicle_id",
        "geofence_id",
        "geofence_name",
        "entry_time",
        "exit_time",
        "dwell_minutes",
    ]
    return source[columns].sort_values(["vehicle_id", "exit_time"]).reset_index(drop=True)


def prepare_lane_baselines(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional lane baseline rows for remaining-time estimates."""
    columns = [
        "lane_id",
        "from_geofence_id",
        "to_destination",
        "remaining_minutes_after_geofence",
        "default_remaining_minutes",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    for column in columns:
        if column not in source.columns:
            source[column] = pd.NA

    source["lane_id"] = source["lane_id"].map(_normalize_key)
    source["from_geofence_id"] = source["from_geofence_id"].map(_normalize_key)
    source["to_destination"] = source["to_destination"].map(_normalize_text)
    source["destination_key"] = source["to_destination"].map(_normalize_key)
    source["remaining_minutes_after_geofence"] = pd.to_numeric(
        source["remaining_minutes_after_geofence"],
        errors="coerce",
    )
    source["default_remaining_minutes"] = pd.to_numeric(
        source["default_remaining_minutes"],
        errors="coerce",
    )

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            LaneBaselineRecord(
                lane_id=row.lane_id,
                from_geofence_id=row.from_geofence_id,
                to_destination=row.to_destination,
                remaining_minutes_after_geofence=None
                if pd.isna(row.remaining_minutes_after_geofence)
                else float(row.remaining_minutes_after_geofence),
                default_remaining_minutes=None
                if pd.isna(row.default_remaining_minutes)
                else float(row.default_remaining_minutes),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"lane_baselines contains invalid rows: {errors[0]}")

    return source[columns + ["destination_key"]].reset_index(drop=True)


def latest_progress_by_vehicle(visit_events: pd.DataFrame) -> pd.DataFrame:
    """Return the latest known GeoReplay visit event per vehicle."""
    columns = [
        "vehicle_id",
        "latest_event_time",
        "last_geofence_id",
        "last_geofence_name",
        "current_progress_status",
    ]
    if visit_events.empty:
        return pd.DataFrame(columns=columns)

    latest = (
        visit_events.sort_values(["vehicle_id", "exit_time"])
        .groupby("vehicle_id", as_index=False)
        .tail(1)
        .copy()
    )
    latest["latest_event_time"] = latest["exit_time"]
    latest["last_geofence_id"] = latest["geofence_id"]
    latest["last_geofence_name"] = latest["geofence_name"].fillna(latest["geofence_id"])
    latest["current_progress_status"] = latest["last_geofence_name"].fillna("Latest site visited")
    return latest[columns].reset_index(drop=True)


def _matching_baseline(
    lane_baselines: pd.DataFrame,
    lane_id: str | None,
    last_geofence_id: str | None,
    destination: str | None,
) -> pd.Series | None:
    """Find the best baseline row for a trip and latest geofence."""
    if lane_baselines.empty:
        return None
    candidates = lane_baselines.copy()
    if lane_id:
        candidates = candidates[
            candidates["lane_id"].isna() | (candidates["lane_id"] == lane_id)
        ].copy()
    if last_geofence_id:
        exact = candidates[candidates["from_geofence_id"] == last_geofence_id]
        if not exact.empty:
            dest_key = _normalize_key(destination)
            dest_exact = exact[exact["destination_key"].isna() | (exact["destination_key"] == dest_key)]
            return dest_exact.iloc[0] if not dest_exact.empty else exact.iloc[0]
    lane_default = candidates[candidates["lane_id"] == lane_id] if lane_id else candidates
    if not lane_default.empty:
        return lane_default.iloc[0]
    return None


def estimate_remaining_minutes(
    trip: pd.Series,
    lane_baselines: pd.DataFrame,
) -> tuple[float, str]:
    """Estimate remaining minutes using lane baselines before fallback rules."""
    baseline = _matching_baseline(
        lane_baselines,
        trip.get("lane_id"),
        trip.get("last_geofence_id"),
        trip.get("destination"),
    )
    if baseline is not None:
        remaining = baseline.get("remaining_minutes_after_geofence")
        if pd.notna(remaining):
            return float(remaining), "lane_geofence_baseline"
        default = baseline.get("default_remaining_minutes")
        if pd.notna(default):
            return float(default), "lane_default_baseline"
    return DEFAULT_REMAINING_MINUTES, "fallback_default_minutes"


def classify_risk(
    planned_arrival: pd.Timestamp,
    predicted_eta: pd.Timestamp | pd.NaT,
    latest_event_time: pd.Timestamp | pd.NaT,
    current_time: pd.Timestamp,
) -> str:
    """Classify one trip into ETA Watch risk buckets."""
    if pd.isna(latest_event_time):
        return "NO SIGNAL"
    if current_time > planned_arrival:
        return "LATE"
    if pd.isna(predicted_eta):
        return "NO SIGNAL"

    eta_delta_minutes = (predicted_eta - planned_arrival).total_seconds() / 60
    if eta_delta_minutes > 60:
        return "AT RISK"
    if eta_delta_minutes > 15:
        return "WATCH"
    return "ON TRACK"


def build_eta_risk_board(
    trips: pd.DataFrame,
    visit_events: pd.DataFrame,
    lane_baselines: pd.DataFrame | None = None,
    current_time: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Build the manager-ready ETA risk board from trip and visit-event data."""
    prepared_trips = prepare_trips(trips)
    prepared_events = prepare_visit_events(visit_events)
    prepared_baselines = prepare_lane_baselines(lane_baselines)
    now = pd.Timestamp.now(tz="UTC") if current_time is None else pd.Timestamp(current_time)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")

    latest_progress = latest_progress_by_vehicle(prepared_events)
    board = prepared_trips.merge(latest_progress, on="vehicle_id", how="left")
    board["estimated_remaining_minutes"] = pd.NA
    board["estimate_source"] = pd.NA

    for index, row in board.iterrows():
        if pd.isna(row.get("latest_event_time")):
            continue
        remaining, source = estimate_remaining_minutes(row, prepared_baselines)
        board.at[index, "estimated_remaining_minutes"] = remaining
        board.at[index, "estimate_source"] = source

    board["predicted_eta"] = pd.Series(pd.NaT, index=board.index, dtype="datetime64[ns, UTC]")
    has_signal = board["latest_event_time"].notna()
    board.loc[has_signal, "predicted_eta"] = board.loc[has_signal, "latest_event_time"] + pd.to_timedelta(
        board.loc[has_signal, "estimated_remaining_minutes"].astype(float),
        unit="m",
    )
    board["eta_delta_minutes"] = pd.NA
    board.loc[has_signal, "eta_delta_minutes"] = (
        (board.loc[has_signal, "predicted_eta"] - board.loc[has_signal, "promised_arrival"])
        .dt.total_seconds()
        .div(60)
        .round(1)
    )
    board["risk_bucket"] = board.apply(
        lambda row: classify_risk(
            row["promised_arrival"],
            row["predicted_eta"],
            row["latest_event_time"],
            now,
        ),
        axis=1,
    )
    board["minutes_until_promised"] = (
        (board["promised_arrival"] - now).dt.total_seconds().div(60).round(1)
    )
    board["review_status"] = "open"
    board["suggested_action"] = board["risk_bucket"].map(
        {
            "ON TRACK": "Monitor in next control-tower cycle.",
            "WATCH": "Check progress again soon and confirm next milestone.",
            "AT RISK": "Escalate to dispatcher and validate remaining route time.",
            "LATE": "Open late-trip escalation and prepare customer update.",
            "NO SIGNAL": "Check GPS/feed status before making ETA promise.",
        }
    )

    output_columns = [
        "trip_id",
        "vehicle_id",
        "origin",
        "destination",
        "lane_id",
        "promised_arrival",
        "latest_event_time",
        "current_progress_status",
        "last_geofence_id",
        "last_geofence_name",
        "estimated_remaining_minutes",
        "estimate_source",
        "predicted_eta",
        "eta_delta_minutes",
        "minutes_until_promised",
        "risk_bucket",
        "suggested_action",
        "review_status",
    ]
    return board[output_columns].sort_values(
        by=["risk_bucket", "promised_arrival"],
        key=lambda series: series.map({bucket: index for index, bucket in enumerate(RISK_ORDER)})
        if series.name == "risk_bucket"
        else series,
    )


def run_eta_watch(
    trips: pd.DataFrame,
    visit_events: pd.DataFrame,
    lane_baselines: pd.DataFrame | None = None,
    current_time: pd.Timestamp | str | None = None,
) -> EtaWatchResult:
    """Run ETA Watch and return risk-board, late-trip, and KPI outputs."""
    risk_board = build_eta_risk_board(trips, visit_events, lane_baselines, current_time)
    late_trips = risk_board[risk_board["risk_bucket"].isin({"LATE", "AT RISK"})].copy()
    kpis = {"total_trips": int(len(risk_board))}
    for bucket in RISK_ORDER:
        kpis[bucket.lower().replace(" ", "_")] = int((risk_board["risk_bucket"] == bucket).sum())
    return EtaWatchResult(risk_board=risk_board, late_trips=late_trips, kpis=kpis)


def write_outputs(result: EtaWatchResult, output_dir: Path) -> tuple[Path, Path]:
    """Write ETA Watch CSV exports and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    risk_path = output_dir / "eta_risk_board.csv"
    late_path = output_dir / "late_trips.csv"
    result.risk_board.to_csv(risk_path, index=False)
    result.late_trips.to_csv(late_path, index=False)
    return risk_path, late_path
