"""Deterministic restriction-window conflict engine for BanWindow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from ban_window.models import BanWindowRecord, BanWindowSettings, TripRecord


REQUIRED_TRIP_COLUMNS = {
    "trip_id",
    "vehicle_id",
    "origin",
    "destination",
    "planned_departure",
    "promised_arrival",
}
REQUIRED_BAN_COLUMNS = {"ban_id", "city", "start_time", "end_time"}
RISK_STATUSES = {
    "CLEAR",
    "CONFLICT",
    "WATCH",
    "MISSING TIMING",
    "MISSING CITY",
    "VEHICLE CLASS UNKNOWN",
}
BAN_RISK_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "origin",
    "destination",
    "city",
    "vehicle_class",
    "planned_departure",
    "promised_arrival",
    "movement_start",
    "movement_end",
    "timing_source",
    "matched_window_count",
    "conflict_count",
    "watch_count",
    "risk_status",
    "severity",
    "evidence",
    "suggested_action",
]
BAN_CONFLICT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "city",
    "vehicle_class",
    "ban_id",
    "location_name",
    "ban_vehicle_class",
    "ban_start",
    "ban_end",
    "overlap_minutes",
    "match_type",
    "severity",
    "evidence",
    "suggested_action",
]
DAY_NAME_ALIASES = {
    "MON": 0,
    "MONDAY": 0,
    "TUE": 1,
    "TUESDAY": 1,
    "WED": 2,
    "WEDNESDAY": 2,
    "THU": 3,
    "THURSDAY": 3,
    "FRI": 4,
    "FRIDAY": 4,
    "SAT": 5,
    "SATURDAY": 5,
    "SUN": 6,
    "SUNDAY": 6,
}


@dataclass(frozen=True)
class BanWindowResult:
    """Structured outputs from a BanWindow run."""

    ban_risk_board: pd.DataFrame
    ban_conflicts: pd.DataFrame
    expanded_windows: pd.DataFrame
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
    return None if text is None else " ".join(text.upper().replace("_", " ").split())


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _parse_effective_date(value: Any) -> pd.Timestamp | pd.NaT:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return pd.NaT
    return parsed.normalize()


def _is_time_only(value: Any) -> bool:
    text = _normalize_text(value)
    if text is None:
        return False
    return "T" not in text and "-" not in text and "/" not in text


def _parse_time(value: Any) -> time | None:
    text = _normalize_text(value)
    if text is None:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.time()


def _parse_days(value: Any) -> set[int] | None:
    text = _normalize_text(value)
    if text is None or text.upper() in {"ALL", "DAILY", "EVERYDAY", "EVERY DAY"}:
        return None
    days: set[int] = set()
    for token in text.replace("|", ",").replace(";", ",").split(","):
        key = token.strip().upper()
        if not key:
            continue
        if key.isdigit():
            number = int(key)
            days.add(number if 0 <= number <= 6 else number - 1)
        elif key in DAY_NAME_ALIASES:
            days.add(DAY_NAME_ALIASES[key])
    return days or None


def _overlap_minutes(start_a: pd.Timestamp, end_a: pd.Timestamp, start_b: pd.Timestamp, end_b: pd.Timestamp) -> float:
    latest_start = max(start_a, start_b)
    earliest_end = min(end_a, end_b)
    if latest_start >= earliest_end:
        return 0.0
    return round((earliest_end - latest_start).total_seconds() / 60, 2)


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate planned trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in [
        "customer_name",
        "carrier_name",
        "city",
        "vehicle_class",
        "planned_city_entry",
        "planned_city_exit",
    ]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")

    for column in ["trip_id", "origin", "destination", "customer_name", "carrier_name", "city"]:
        source[column] = source[column].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["vehicle_class"] = source["vehicle_class"].map(_normalize_key)
    for column in ["planned_departure", "promised_arrival", "planned_city_entry", "planned_city_exit"]:
        source[column] = _to_utc(source[column])
    source = source.dropna(subset=["trip_id", "vehicle_id", "origin", "destination"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                origin=str(row.origin),
                destination=str(row.destination),
                planned_departure=None
                if pd.isna(row.planned_departure)
                else row.planned_departure.to_pydatetime(),
                promised_arrival=None
                if pd.isna(row.promised_arrival)
                else row.promised_arrival.to_pydatetime(),
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                city=None if pd.isna(row.city) else row.city,
                vehicle_class=None if pd.isna(row.vehicle_class) else row.vehicle_class,
                planned_city_entry=None
                if pd.isna(row.planned_city_entry)
                else row.planned_city_entry.to_pydatetime(),
                planned_city_exit=None
                if pd.isna(row.planned_city_exit)
                else row.planned_city_exit.to_pydatetime(),
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
            "origin",
            "destination",
            "city",
            "vehicle_class",
            "planned_departure",
            "promised_arrival",
            "planned_city_entry",
            "planned_city_exit",
        ]
    ].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_ban_windows(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate user-supplied restriction windows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["location_name", "vehicle_class", "days_of_week", "effective_from", "effective_to", "rule_note"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_BAN_COLUMNS, "ban_windows")

    for column in ["ban_id", "city", "location_name", "days_of_week", "rule_note"]:
        source[column] = source[column].map(_normalize_text)
    source["vehicle_class"] = source["vehicle_class"].map(_normalize_key)
    source["start_time"] = source["start_time"].map(_normalize_text)
    source["end_time"] = source["end_time"].map(_normalize_text)
    source["effective_from"] = source["effective_from"].map(_parse_effective_date)
    source["effective_to"] = source["effective_to"].map(_parse_effective_date)
    source = source.dropna(subset=["ban_id", "city", "start_time", "end_time"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            BanWindowRecord(
                ban_id=str(row.ban_id),
                city=str(row.city),
                start_time=str(row.start_time),
                end_time=str(row.end_time),
                location_name=None if pd.isna(row.location_name) else row.location_name,
                vehicle_class=None if pd.isna(row.vehicle_class) else row.vehicle_class,
                days_of_week=None if pd.isna(row.days_of_week) else row.days_of_week,
                effective_from=None
                if pd.isna(row.effective_from)
                else row.effective_from.to_pydatetime(),
                effective_to=None if pd.isna(row.effective_to) else row.effective_to.to_pydatetime(),
                rule_note=None if pd.isna(row.rule_note) else row.rule_note,
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"ban_windows contains invalid rows: {errors[0]}")

    return source[
        [
            "ban_id",
            "city",
            "location_name",
            "vehicle_class",
            "start_time",
            "end_time",
            "days_of_week",
            "effective_from",
            "effective_to",
            "rule_note",
        ]
    ].reset_index(drop=True)


def prepare_eta_risk_board(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional ETA risk board rows."""
    columns = ["trip_id", "predicted_arrival", "risk_status", "latest_event_time"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    source = _normalize_columns(df).dropna(how="all").copy()
    if "trip_id" not in source.columns:
        raise ValueError("eta_risk_board is missing required columns: trip_id")
    for column in ["predicted_arrival", "risk_status", "latest_event_time"]:
        if column not in source.columns:
            source[column] = pd.NA
    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["predicted_arrival"] = _to_utc(source["predicted_arrival"])
    source["latest_event_time"] = _to_utc(source["latest_event_time"])
    source["risk_status"] = source["risk_status"].map(_normalize_text)
    return source[columns].dropna(subset=["trip_id"]).drop_duplicates("trip_id", keep="last").reset_index(drop=True)


def prepare_visit_events(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional GeoReplay visit events for latest-evidence timing fallback."""
    columns = ["trip_id", "vehicle_id", "geofence_name", "geofence_type", "enter_time", "exit_time", "dwell_minutes"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in columns:
        if column not in source.columns:
            source[column] = pd.NA
    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["geofence_name"] = source["geofence_name"].map(_normalize_text)
    source["geofence_type"] = source["geofence_type"].map(_normalize_key)
    source["enter_time"] = _to_utc(source["enter_time"])
    source["exit_time"] = _to_utc(source["exit_time"])
    source["dwell_minutes"] = pd.to_numeric(source["dwell_minutes"], errors="coerce")
    return source[columns].dropna(subset=["trip_id", "vehicle_id"], how="all").reset_index(drop=True)


def _date_range_for_expansion(trips: pd.DataFrame, settings: BanWindowSettings) -> tuple[pd.Timestamp, pd.Timestamp]:
    times = pd.concat(
        [
            trips["planned_departure"],
            trips["promised_arrival"],
            trips["planned_city_entry"],
            trips["planned_city_exit"],
        ],
        ignore_index=True,
    ).dropna()
    if times.empty:
        today = pd.Timestamp.now(tz="UTC").normalize()
        return today, today
    start = times.min().normalize() - pd.Timedelta(days=settings.expansion_padding_days)
    end = times.max().normalize() + pd.Timedelta(days=settings.expansion_padding_days)
    return start, end


def expand_ban_windows(
    ban_windows: pd.DataFrame,
    trips: pd.DataFrame,
    *,
    settings: BanWindowSettings | None = None,
) -> pd.DataFrame:
    """Expand user-supplied restriction rows into concrete UTC datetime intervals."""
    active_settings = settings or BanWindowSettings()
    start_date, end_date = _date_range_for_expansion(trips, active_settings)
    rows: list[dict[str, Any]] = []

    for ban in ban_windows.itertuples(index=False):
        start_is_time = _is_time_only(ban.start_time)
        end_is_time = _is_time_only(ban.end_time)
        days = _parse_days(ban.days_of_week)
        effective_from = ban.effective_from if pd.notna(ban.effective_from) else start_date
        effective_to = ban.effective_to if pd.notna(ban.effective_to) else end_date
        effective_from = max(effective_from.normalize(), start_date)
        effective_to = min(effective_to.normalize(), end_date)

        if start_is_time and end_is_time:
            start_clock = _parse_time(ban.start_time)
            end_clock = _parse_time(ban.end_time)
            if start_clock is None or end_clock is None:
                continue
            current = effective_from
            while current <= effective_to:
                if days is None or current.weekday() in days:
                    interval_start = pd.Timestamp(
                        datetime.combine(date(current.year, current.month, current.day), start_clock),
                        tz="UTC",
                    )
                    interval_end = pd.Timestamp(
                        datetime.combine(date(current.year, current.month, current.day), end_clock),
                        tz="UTC",
                    )
                    if interval_end <= interval_start:
                        interval_end += pd.Timedelta(days=1)
                    rows.append(_expanded_row(ban, interval_start, interval_end))
                current += pd.Timedelta(days=1)
            continue

        interval_start = pd.to_datetime(ban.start_time, errors="coerce", utc=True)
        interval_end = pd.to_datetime(ban.end_time, errors="coerce", utc=True)
        if pd.isna(interval_start) or pd.isna(interval_end):
            continue
        if interval_end <= interval_start:
            interval_end += pd.Timedelta(days=1)
        rows.append(_expanded_row(ban, interval_start, interval_end))

    return pd.DataFrame(rows, columns=[
        "ban_id",
        "city",
        "location_name",
        "vehicle_class",
        "ban_start",
        "ban_end",
        "rule_note",
    ])


def _expanded_row(ban: Any, interval_start: pd.Timestamp, interval_end: pd.Timestamp) -> dict[str, Any]:
    return {
        "ban_id": ban.ban_id,
        "city": ban.city,
        "location_name": ban.location_name,
        "vehicle_class": ban.vehicle_class,
        "ban_start": interval_start,
        "ban_end": interval_end,
        "rule_note": ban.rule_note,
    }


def _movement_interval(trip: pd.Series, eta: pd.Series | None, visits: pd.DataFrame) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT, str]:
    if pd.notna(trip.planned_city_entry) and pd.notna(trip.planned_city_exit):
        return trip.planned_city_entry, trip.planned_city_exit, "planned_city_window"

    if eta is not None and pd.notna(eta.get("predicted_arrival")) and pd.notna(trip.planned_departure):
        return trip.planned_departure, eta["predicted_arrival"], "eta_risk_board"

    visit_matches = visits[visits["trip_id"] == trip.trip_id]
    if visit_matches.empty:
        visit_matches = visits[visits["vehicle_id"] == trip.vehicle_id]
    visit_times = pd.concat([visit_matches["enter_time"], visit_matches["exit_time"]], ignore_index=True).dropna()
    if not visit_times.empty and pd.notna(trip.promised_arrival):
        return visit_times.min(), trip.promised_arrival, "visit_events_to_promised_arrival"

    return trip.planned_departure, trip.promised_arrival, "planned_trip_window"


def _window_matches_trip(trip: pd.Series, window: pd.Series) -> tuple[bool, str]:
    if _normalize_key(trip.city) != _normalize_key(window.city):
        return False, "city"
    if pd.isna(window.vehicle_class):
        return True, "city"
    if pd.isna(trip.vehicle_class):
        return True, "vehicle_class_unknown"
    if _normalize_key(trip.vehicle_class) == _normalize_key(window.vehicle_class):
        return True, "city_vehicle_class"
    return False, "vehicle_class"


def _classify_trip(
    trip: pd.Series,
    movement_start: pd.Timestamp | pd.NaT,
    movement_end: pd.Timestamp | pd.NaT,
    windows: pd.DataFrame,
    settings: BanWindowSettings,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base = {
        "trip_id": trip.trip_id,
        "vehicle_id": trip.vehicle_id,
        "customer_name": trip.customer_name,
        "carrier_name": trip.carrier_name,
        "origin": trip.origin,
        "destination": trip.destination,
        "city": trip.city,
        "vehicle_class": trip.vehicle_class,
        "planned_departure": trip.planned_departure,
        "promised_arrival": trip.promised_arrival,
        "movement_start": movement_start,
        "movement_end": movement_end,
    }
    if pd.isna(trip.city):
        return {
            **base,
            "matched_window_count": 0,
            "conflict_count": 0,
            "watch_count": 0,
            "risk_status": "MISSING CITY",
            "severity": "MEDIUM",
            "evidence": "Trip has no city value for matching user-supplied restriction windows.",
            "suggested_action": "Add the planning city before dispatch review.",
        }, []
    if pd.isna(movement_start) or pd.isna(movement_end) or movement_end <= movement_start:
        return {
            **base,
            "matched_window_count": 0,
            "conflict_count": 0,
            "watch_count": 0,
            "risk_status": "MISSING TIMING",
            "severity": "MEDIUM",
            "evidence": "Trip movement interval is missing or not usable.",
            "suggested_action": "Add planned city entry and exit, ETA, or valid departure and arrival times.",
        }, []

    matched: list[pd.Series] = []
    conflict_rows: list[dict[str, Any]] = []
    watch_count = 0
    unknown_class = False
    for _, window in windows.iterrows():
        is_match, match_type = _window_matches_trip(trip, window)
        if not is_match:
            continue
        matched.append(window)
        overlap = _overlap_minutes(movement_start, movement_end, window.ban_start, window.ban_end)
        buffer_start = movement_start - pd.Timedelta(minutes=settings.watch_buffer_minutes)
        buffer_end = movement_end + pd.Timedelta(minutes=settings.watch_buffer_minutes)
        buffered_overlap = _overlap_minutes(buffer_start, buffer_end, window.ban_start, window.ban_end)
        if match_type == "vehicle_class_unknown":
            unknown_class = True
        if overlap > 0:
            severity = "HIGH" if match_type != "vehicle_class_unknown" else "MEDIUM"
            conflict_rows.append(
                {
                    "trip_id": trip.trip_id,
                    "vehicle_id": trip.vehicle_id,
                    "city": trip.city,
                    "vehicle_class": trip.vehicle_class,
                    "ban_id": window.ban_id,
                    "location_name": window.location_name,
                    "ban_vehicle_class": window.vehicle_class,
                    "ban_start": window.ban_start,
                    "ban_end": window.ban_end,
                    "overlap_minutes": overlap,
                    "match_type": match_type,
                    "severity": severity,
                    "evidence": f"Movement overlaps user-supplied restriction window by {overlap:.0f} minutes.",
                    "suggested_action": "Review dispatch or arrival plan against the uploaded restriction window.",
                }
            )
        elif buffered_overlap > 0:
            watch_count += 1

    if conflict_rows:
        return {
            **base,
            "matched_window_count": len(matched),
            "conflict_count": len(conflict_rows),
            "watch_count": watch_count,
            "risk_status": "CONFLICT" if not unknown_class else "VEHICLE CLASS UNKNOWN",
            "severity": "HIGH" if not unknown_class else "MEDIUM",
            "evidence": f"{len(conflict_rows)} overlapping uploaded restriction windows found.",
            "suggested_action": "Needs planning review before dispatch or arrival commitment.",
        }, conflict_rows
    if unknown_class:
        return {
            **base,
            "matched_window_count": len(matched),
            "conflict_count": 0,
            "watch_count": watch_count,
            "risk_status": "VEHICLE CLASS UNKNOWN",
            "severity": "MEDIUM",
            "evidence": "A city restriction exists for a vehicle class, but the trip vehicle class is missing.",
            "suggested_action": "Confirm vehicle class before using this plan.",
        }, []
    if watch_count:
        return {
            **base,
            "matched_window_count": len(matched),
            "conflict_count": 0,
            "watch_count": watch_count,
            "risk_status": "WATCH",
            "severity": "LOW",
            "evidence": f"Trip is within {settings.watch_buffer_minutes} minutes of an uploaded restriction window.",
            "suggested_action": "Monitor timing and keep a planning buffer.",
        }, []
    return {
        **base,
        "matched_window_count": len(matched),
        "conflict_count": 0,
        "watch_count": 0,
        "risk_status": "CLEAR",
        "severity": "LOW",
        "evidence": "No overlap with matching user-supplied restriction windows.",
        "suggested_action": "No restriction-window action needed from this file check.",
    }, []


def run_ban_window(
    trips_df: pd.DataFrame,
    ban_windows_df: pd.DataFrame,
    eta_risk_board_df: pd.DataFrame | None = None,
    visit_events_df: pd.DataFrame | None = None,
    *,
    settings: BanWindowSettings | None = None,
) -> BanWindowResult:
    """Build BanWindow risk board and conflict exports."""
    active_settings = settings or BanWindowSettings()
    trips = prepare_trips(trips_df)
    ban_windows = prepare_ban_windows(ban_windows_df)
    eta = prepare_eta_risk_board(eta_risk_board_df)
    visits = prepare_visit_events(visit_events_df)
    expanded = expand_ban_windows(ban_windows, trips, settings=active_settings)
    eta_by_trip = eta.set_index("trip_id") if not eta.empty else pd.DataFrame()

    risk_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for trip_tuple in trips.itertuples(index=False):
        trip = pd.Series(trip_tuple._asdict())
        eta_row = eta_by_trip.loc[trip.trip_id] if trip.trip_id in eta_by_trip.index else None
        movement_start, movement_end, timing_source = _movement_interval(trip, eta_row, visits)
        risk_row, trip_conflicts = _classify_trip(
            trip,
            movement_start,
            movement_end,
            expanded,
            active_settings,
        )
        risk_row["timing_source"] = timing_source
        risk_rows.append(risk_row)
        conflict_rows.extend(trip_conflicts)

    risk_board = pd.DataFrame(risk_rows, columns=BAN_RISK_COLUMNS)
    conflicts = pd.DataFrame(conflict_rows, columns=BAN_CONFLICT_COLUMNS)
    kpis = {
        "total_trips": float(len(risk_board)),
        "conflict_trips": float((risk_board["risk_status"] == "CONFLICT").sum()) if not risk_board.empty else 0.0,
        "watch_trips": float((risk_board["risk_status"] == "WATCH").sum()) if not risk_board.empty else 0.0,
        "missing_data_trips": float(risk_board["risk_status"].isin(["MISSING TIMING", "MISSING CITY", "VEHICLE CLASS UNKNOWN"]).sum())
        if not risk_board.empty
        else 0.0,
        "conflict_rows": float(len(conflicts)),
        "expanded_windows": float(len(expanded)),
    }
    return BanWindowResult(
        ban_risk_board=risk_board.reset_index(drop=True),
        ban_conflicts=conflicts.reset_index(drop=True),
        expanded_windows=expanded.reset_index(drop=True),
        kpis=kpis,
    )


def write_outputs(result: BanWindowResult, output_dir: str | Path) -> tuple[Path, Path]:
    """Write BanWindow CSV outputs and return their paths."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    risk_path = target / "ban_risk_board.csv"
    conflict_path = target / "ban_conflicts.csv"
    result.ban_risk_board.to_csv(risk_path, index=False)
    result.ban_conflicts.to_csv(conflict_path, index=False)
    return risk_path, conflict_path

