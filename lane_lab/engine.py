"""Deterministic lane travel-time baseline engine for LaneLab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from lane_lab.models import HistoricalTripRecord, LaneLabSettings, VisitEventRecord


REQUIRED_TRIP_COLUMNS = {"trip_id", "vehicle_id", "origin", "destination"}
REQUIRED_VISIT_COLUMNS = {
    "vehicle_id",
    "geofence_id",
    "geofence_name",
    "geofence_type",
    "enter_time",
    "exit_time",
    "dwell_minutes",
}
ORIGIN_TYPES = {"ORIGIN", "HUB", "PICKUP"}
DESTINATION_TYPES = {"DESTINATION", "CUSTOMER", "DELIVERY"}
BASELINE_COLUMNS = [
    "lane_id",
    "origin",
    "destination",
    "customer_name",
    "carrier_name",
    "sample_size",
    "usable_trip_count",
    "invalid_trip_count",
    "p50_minutes",
    "p75_minutes",
    "p90_minutes",
    "avg_minutes",
    "min_minutes",
    "max_minutes",
    "std_minutes",
    "outlier_count",
    "confidence_bucket",
    "evidence",
    "suggested_action",
]
OUTLIER_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "lane_id",
    "origin",
    "destination",
    "customer_name",
    "carrier_name",
    "actual_origin_exit",
    "actual_destination_entry",
    "duration_minutes",
    "outlier_type",
    "severity",
    "evidence",
    "suggested_action",
]


@dataclass(frozen=True)
class LaneLabResult:
    """Structured outputs from a LaneLab run."""

    lane_baselines: pd.DataFrame
    lane_outliers: pd.DataFrame
    trip_durations: pd.DataFrame
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


def _minutes_between(later: pd.Timestamp | pd.NaT, earlier: pd.Timestamp | pd.NaT) -> float | None:
    if pd.isna(later) or pd.isna(earlier):
        return None
    return round((later - earlier).total_seconds() / 60, 2)


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate historical trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["lane_id", "customer_name", "carrier_name", "planned_departure", "promised_arrival"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "historical_trips")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["lane_id"] = source["lane_id"].map(_normalize_key)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(subset=["trip_id", "vehicle_id", "origin", "destination"]).copy()
    missing_lane = source["lane_id"].isna()
    source.loc[missing_lane, "lane_id"] = (
        source.loc[missing_lane, "origin"].map(_normalize_key)
        + "-"
        + source.loc[missing_lane, "destination"].map(_normalize_key)
    )

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            HistoricalTripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                lane_id=None if pd.isna(row.lane_id) else row.lane_id,
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                origin=str(row.origin),
                destination=str(row.destination),
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
        raise ValueError(f"historical_trips contains invalid rows: {errors[0]}")

    return source[
        [
            "trip_id",
            "vehicle_id",
            "lane_id",
            "customer_name",
            "carrier_name",
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
    _require_columns(source, REQUIRED_VISIT_COLUMNS, "historical_visit_events")

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
        raise ValueError(f"historical_visit_events contains invalid rows: {errors[0]}")

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


def _trip_visit_candidates(trip: pd.Series, visit_events: pd.DataFrame) -> pd.DataFrame:
    exact = visit_events[visit_events["trip_id"] == trip.trip_id].copy()
    if not exact.empty:
        return exact

    if pd.notna(trip.planned_departure) and pd.notna(trip.promised_arrival):
        window_start = trip.planned_departure - pd.Timedelta(hours=6)
        window_end = trip.promised_arrival + pd.Timedelta(hours=24)
        return visit_events[
            (visit_events["vehicle_id"] == trip.vehicle_id)
            & (
                visit_events["enter_time"].between(window_start, window_end, inclusive="both")
                | visit_events["exit_time"].between(window_start, window_end, inclusive="both")
            )
        ].copy()

    return visit_events[visit_events["vehicle_id"] == trip.vehicle_id].copy()


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
    name_matches = (
        candidates["geofence_name"]
        .map(lambda value: _name_matches(value, trip.destination))
        .fillna(False)
        .astype(bool)
    )
    matches = candidates[candidates["geofence_type"].isin(DESTINATION_TYPES) | name_matches].copy()
    if matches.empty:
        return None
    if origin_event is not None and pd.notna(origin_event.get("exit_time")):
        after_origin = matches[matches["enter_time"] >= origin_event["exit_time"]]
        if not after_origin.empty:
            matches = after_origin
    timed = matches[matches["enter_time"].notna()].sort_values(["enter_time", "exit_time"])
    return timed.iloc[0] if not timed.empty else matches.iloc[0]


def _extract_trip_duration(trip: pd.Series, visits: pd.DataFrame) -> dict[str, Any]:
    candidates = _trip_visit_candidates(trip, visits)
    origin_event = _pick_origin_event(trip, candidates)
    destination_event = _pick_destination_event(trip, candidates, origin_event)
    actual_origin_exit = origin_event["exit_time"] if origin_event is not None else pd.NaT
    actual_destination_entry = (
        destination_event["enter_time"] if destination_event is not None else pd.NaT
    )
    duration = _minutes_between(actual_destination_entry, actual_origin_exit)
    invalid_reason = None
    if origin_event is None:
        invalid_reason = "missing origin event"
    elif destination_event is None:
        invalid_reason = "missing destination event"
    elif duration is None:
        invalid_reason = "missing event timestamp"
    elif duration <= 0:
        invalid_reason = "zero or negative duration"

    return {
        "trip_id": trip.trip_id,
        "vehicle_id": trip.vehicle_id,
        "lane_id": trip.lane_id,
        "origin": trip.origin,
        "destination": trip.destination,
        "customer_name": trip.customer_name,
        "carrier_name": trip.carrier_name,
        "actual_origin_exit": actual_origin_exit,
        "actual_destination_entry": actual_destination_entry,
        "duration_minutes": None if duration is None else duration,
        "is_usable": invalid_reason is None,
        "invalid_reason": invalid_reason,
    }


def _confidence_bucket(
    usable_count: int,
    invalid_count: int,
    outlier_count: int,
    std_minutes: float,
    spread_minutes: float,
    settings: LaneLabSettings,
) -> tuple[str, str]:
    if usable_count == 0:
        return "DATA MISSING", "Add usable origin and destination visit events before using this lane."
    if usable_count < settings.low_sample_threshold:
        return "LOW SAMPLE", "Use as a temporary reference and add more completed trips."
    if (
        std_minutes >= settings.unstable_std_threshold_minutes
        or spread_minutes >= settings.unstable_spread_threshold_minutes
        or outlier_count >= max(2, usable_count // 3)
    ):
        return "UNSTABLE", "Check data quality and split the lane if operating patterns differ."
    if invalid_count > 0 or usable_count < settings.strong_sample_threshold:
        return "MEDIUM", "Review missing or invalid trips and refresh the baseline after more samples."
    return "STRONG", "Use this lane baseline for ETA and SLA review."


def _outlier_bounds(durations: pd.Series, settings: LaneLabSettings) -> tuple[float, float]:
    q1 = float(durations.quantile(0.25))
    q3 = float(durations.quantile(0.75))
    iqr = q3 - q1
    if iqr == 0:
        return q1, q3
    return q1 - settings.outlier_iqr_multiplier * iqr, q3 + settings.outlier_iqr_multiplier * iqr


def _build_lane_rows(
    durations: pd.DataFrame,
    settings: LaneLabSettings,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    baseline_rows: list[dict[str, Any]] = []
    outlier_rows: list[dict[str, Any]] = []
    group_columns = ["lane_id", "origin", "destination", "customer_name", "carrier_name"]

    for group_key, group in durations.groupby(group_columns, dropna=False, sort=True):
        lane_id, origin, destination, customer_name, carrier_name = group_key
        usable = group[group["is_usable"]].copy()
        invalid_count = int((~group["is_usable"]).sum())
        sample_size = int(len(group))
        if usable.empty:
            confidence, action = _confidence_bucket(0, invalid_count, 0, 0.0, 0.0, settings)
            evidence = f"0 usable trips from {sample_size} samples; {invalid_count} invalid trips"
            baseline_rows.append(
                {
                    "lane_id": lane_id,
                    "origin": origin,
                    "destination": destination,
                    "customer_name": customer_name,
                    "carrier_name": carrier_name,
                    "sample_size": sample_size,
                    "usable_trip_count": 0,
                    "invalid_trip_count": invalid_count,
                    "p50_minutes": None,
                    "p75_minutes": None,
                    "p90_minutes": None,
                    "avg_minutes": None,
                    "min_minutes": None,
                    "max_minutes": None,
                    "std_minutes": None,
                    "outlier_count": 0,
                    "confidence_bucket": confidence,
                    "evidence": evidence,
                    "suggested_action": action,
                }
            )
            continue

        duration_series = usable["duration_minutes"].astype(float)
        lower_bound, upper_bound = _outlier_bounds(duration_series, settings)
        outlier_mask = (duration_series < lower_bound) | (duration_series > upper_bound)
        outliers = usable[outlier_mask].copy()
        outlier_count = int(len(outliers))
        std_minutes = round(float(duration_series.std(ddof=0)), 2)
        spread_minutes = round(float(duration_series.max() - duration_series.min()), 2)
        confidence, action = _confidence_bucket(
            len(usable),
            invalid_count,
            outlier_count,
            std_minutes,
            spread_minutes,
            settings,
        )
        evidence = (
            f"{len(usable)} usable trips from {sample_size} samples; "
            f"range {duration_series.min():.0f}-{duration_series.max():.0f} min; "
            f"{invalid_count} invalid trips; {outlier_count} outliers"
        )
        baseline_rows.append(
            {
                "lane_id": lane_id,
                "origin": origin,
                "destination": destination,
                "customer_name": customer_name,
                "carrier_name": carrier_name,
                "sample_size": sample_size,
                "usable_trip_count": int(len(usable)),
                "invalid_trip_count": invalid_count,
                "p50_minutes": round(float(duration_series.quantile(0.50)), 2),
                "p75_minutes": round(float(duration_series.quantile(0.75)), 2),
                "p90_minutes": round(float(duration_series.quantile(0.90)), 2),
                "avg_minutes": round(float(duration_series.mean()), 2),
                "min_minutes": round(float(duration_series.min()), 2),
                "max_minutes": round(float(duration_series.max()), 2),
                "std_minutes": std_minutes,
                "outlier_count": outlier_count,
                "confidence_bucket": confidence,
                "evidence": evidence,
                "suggested_action": action,
            }
        )
        for row in outliers.itertuples(index=False):
            outlier_type = "LONG DURATION" if row.duration_minutes > upper_bound else "SHORT DURATION"
            severity = "HIGH" if confidence == "UNSTABLE" else "MEDIUM"
            outlier_rows.append(
                {
                    "trip_id": row.trip_id,
                    "vehicle_id": row.vehicle_id,
                    "lane_id": row.lane_id,
                    "origin": row.origin,
                    "destination": row.destination,
                    "customer_name": row.customer_name,
                    "carrier_name": row.carrier_name,
                    "actual_origin_exit": row.actual_origin_exit,
                    "actual_destination_entry": row.actual_destination_entry,
                    "duration_minutes": row.duration_minutes,
                    "outlier_type": outlier_type,
                    "severity": severity,
                    "evidence": (
                        f"duration {row.duration_minutes:.0f} min outside "
                        f"{lower_bound:.0f}-{upper_bound:.0f} min lane range"
                    ),
                    "suggested_action": "Check data quality before using this trip in the lane baseline.",
                }
            )

    return (
        pd.DataFrame(baseline_rows, columns=BASELINE_COLUMNS),
        pd.DataFrame(outlier_rows, columns=OUTLIER_COLUMNS),
    )


def run_lane_lab(
    historical_trips_df: pd.DataFrame,
    historical_visit_events_df: pd.DataFrame,
    *,
    settings: LaneLabSettings | None = None,
) -> LaneLabResult:
    """Build lane travel-time baselines and outlier exports."""
    active_settings = settings or LaneLabSettings()
    trips = prepare_trips(historical_trips_df)
    visits = prepare_visit_events(historical_visit_events_df)
    duration_rows = [
        _extract_trip_duration(pd.Series(trip._asdict()), visits)
        for trip in trips.itertuples(index=False)
    ]
    trip_durations = pd.DataFrame(duration_rows)
    baselines, outliers = _build_lane_rows(trip_durations, active_settings)
    kpis = {
        "total_lanes": float(len(baselines)),
        "total_trips": float(len(trip_durations)),
        "usable_trips": float(trip_durations["is_usable"].sum()) if not trip_durations.empty else 0.0,
        "invalid_trips": float((~trip_durations["is_usable"]).sum()) if not trip_durations.empty else 0.0,
        "outlier_trips": float(len(outliers)),
        "low_confidence_lanes": float(
            baselines["confidence_bucket"].isin(["LOW SAMPLE", "UNSTABLE", "DATA MISSING"]).sum()
        )
        if not baselines.empty
        else 0.0,
    }
    return LaneLabResult(
        lane_baselines=baselines.reset_index(drop=True),
        lane_outliers=outliers.reset_index(drop=True),
        trip_durations=trip_durations.reset_index(drop=True),
        kpis=kpis,
    )


def write_outputs(result: LaneLabResult, output_dir: str | Path) -> tuple[Path, Path]:
    """Write LaneLab CSV outputs and return their paths."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    baseline_path = target / "lane_baselines.csv"
    outlier_path = target / "lane_outliers.csv"
    result.lane_baselines.to_csv(baseline_path, index=False)
    result.lane_outliers.to_csv(outlier_path, index=False)
    return baseline_path, outlier_path
