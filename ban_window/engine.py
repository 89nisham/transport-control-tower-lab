"""Deterministic restriction-window conflict engine for BanWindow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
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
RISK_BUCKETS = {
    "CLEAR",
    "WATCH",
    "BAN CONFLICT",
    "MISSING TIMING",
    "MISSING CITY",
    "VEHICLE CLASS UNKNOWN",
    "DATA MISSING",
}
CONFIDENCE_BUCKETS = {"HIGH", "MEDIUM", "LOW", "DATA MISSING"}
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
    "predicted_arrival",
    "movement_start",
    "movement_end",
    "matched_ban_id",
    "ban_city",
    "ban_location_name",
    "ban_vehicle_class",
    "ban_window_start",
    "ban_window_end",
    "overlap_minutes",
    "risk_bucket",
    "severity",
    "confidence_bucket",
    "evidence",
    "suggested_action",
]
BAN_CONFLICT_COLUMNS = [
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "city",
    "vehicle_class",
    "matched_ban_id",
    "ban_window_start",
    "ban_window_end",
    "overlap_minutes",
    "exception_type",
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
RISK_RANK = {
    "BAN CONFLICT": 6,
    "VEHICLE CLASS UNKNOWN": 5,
    "WATCH": 4,
    "DATA MISSING": 3,
    "MISSING TIMING": 2,
    "MISSING CITY": 1,
    "CLEAR": 0,
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


def _search_key(value: Any) -> str:
    text = _normalize_text(value) or ""
    return "".join(character for character in text.upper() if character.isalnum())


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
    if text is None:
        return None
    days: set[int] = set()
    for token in text.replace("|", ",").replace(";", ",").split(","):
        key = token.strip().upper()
        if not key:
            continue
        if key in DAY_NAME_ALIASES:
            days.add(DAY_NAME_ALIASES[key])
    return days or None


def interval_overlap_minutes(
    start_a: pd.Timestamp,
    end_a: pd.Timestamp,
    start_b: pd.Timestamp,
    end_b: pd.Timestamp,
) -> float:
    """Return positive overlap minutes between two datetime intervals."""
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
    source = source.dropna(subset=["trip_id"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=None if pd.isna(row.vehicle_id) else str(row.vehicle_id),
                origin=None if pd.isna(row.origin) else str(row.origin),
                destination=None if pd.isna(row.destination) else str(row.destination),
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


def _infer_city(trip: pd.Series, ban_windows: pd.DataFrame) -> tuple[str | None, bool]:
    if pd.notna(trip.city):
        return trip.city, False
    for field in ["destination", "origin"]:
        haystack = _search_key(trip.get(field))
        for city in ban_windows["city"].dropna().drop_duplicates():
            city_key = _search_key(city)
            if city_key and city_key in haystack:
                return city, True
    return None, False


def _movement_interval(
    trip: pd.Series,
    eta: pd.Series | None,
) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT, str]:
    predicted_arrival = pd.NaT
    if eta is not None and pd.notna(eta.get("predicted_arrival")):
        predicted_arrival = eta["predicted_arrival"]
    if pd.notna(trip.planned_city_entry) and pd.notna(trip.planned_city_exit):
        return trip.planned_city_entry, trip.planned_city_exit, predicted_arrival, "planned_city_window"
    if pd.notna(predicted_arrival) and pd.notna(trip.planned_departure):
        return trip.planned_departure, predicted_arrival, predicted_arrival, "eta_risk_board"
    return trip.planned_departure, trip.promised_arrival, predicted_arrival, "planned_trip_window"


def _base_date_for_trip(trip: pd.Series, movement_start: pd.Timestamp | pd.NaT) -> pd.Timestamp | pd.NaT:
    if pd.notna(trip.planned_departure):
        return trip.planned_departure.normalize()
    if pd.notna(movement_start):
        return movement_start.normalize()
    if pd.notna(trip.promised_arrival):
        return trip.promised_arrival.normalize()
    return pd.NaT


def _expanded_window_for_trip(
    ban: pd.Series,
    trip: pd.Series,
    movement_start: pd.Timestamp | pd.NaT,
) -> tuple[pd.Timestamp | pd.NaT, pd.Timestamp | pd.NaT] | None:
    start_is_time = _is_time_only(ban.start_time)
    end_is_time = _is_time_only(ban.end_time)
    if start_is_time and end_is_time:
        base_date = _base_date_for_trip(trip, movement_start)
        start_clock = _parse_time(ban.start_time)
        end_clock = _parse_time(ban.end_time)
        if pd.isna(base_date) or start_clock is None or end_clock is None:
            return None
        days = _parse_days(ban.days_of_week)
        if days is not None and base_date.weekday() not in days:
            return None
        effective_from = ban.effective_from if pd.notna(ban.effective_from) else pd.NaT
        effective_to = ban.effective_to if pd.notna(ban.effective_to) else pd.NaT
        if pd.notna(effective_from) and base_date < effective_from.normalize():
            return None
        if pd.notna(effective_to) and base_date > effective_to.normalize():
            return None
        interval_start = pd.Timestamp(
            datetime.combine(base_date.date(), start_clock),
            tz="UTC",
        )
        interval_end = pd.Timestamp(
            datetime.combine(base_date.date(), end_clock),
            tz="UTC",
        )
        if interval_end <= interval_start:
            interval_end += pd.Timedelta(days=1)
        return interval_start, interval_end

    interval_start = pd.to_datetime(ban.start_time, errors="coerce", utc=True)
    interval_end = pd.to_datetime(ban.end_time, errors="coerce", utc=True)
    if pd.isna(interval_start) or pd.isna(interval_end):
        return None
    if interval_end <= interval_start:
        interval_end += pd.Timedelta(days=1)
    return interval_start, interval_end


def expand_ban_windows_for_trips(
    ban_windows: pd.DataFrame,
    trips: pd.DataFrame,
) -> pd.DataFrame:
    """Expand user-supplied restriction windows against each trip's planned date."""
    rows: list[dict[str, Any]] = []
    for trip_tuple in trips.itertuples(index=False):
        trip = pd.Series(trip_tuple._asdict())
        movement_start, _, _, _ = _movement_interval(trip, None)
        for _, ban in ban_windows.iterrows():
            interval = _expanded_window_for_trip(ban, trip, movement_start)
            if interval is None:
                continue
            interval_start, interval_end = interval
            rows.append(
                {
                    "trip_id": trip.trip_id,
                    "ban_id": ban.ban_id,
                    "city": ban.city,
                    "location_name": ban.location_name,
                    "vehicle_class": ban.vehicle_class,
                    "ban_start": interval_start,
                    "ban_end": interval_end,
                    "rule_note": ban.rule_note,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "trip_id",
            "ban_id",
            "city",
            "location_name",
            "vehicle_class",
            "ban_start",
            "ban_end",
            "rule_note",
        ],
    )


def _matching_windows(
    trip: pd.Series,
    city: str | None,
    ban_windows: pd.DataFrame,
    movement_start: pd.Timestamp | pd.NaT,
) -> tuple[list[dict[str, Any]], bool]:
    matches: list[dict[str, Any]] = []
    unknown_class = False
    for _, ban in ban_windows.iterrows():
        if _normalize_key(city) != _normalize_key(ban.city):
            continue
        interval = _expanded_window_for_trip(ban, trip, movement_start)
        if interval is None:
            continue
        if pd.notna(ban.vehicle_class):
            if pd.isna(trip.vehicle_class):
                unknown_class = True
                matches.append({"ban": ban, "match_type": "vehicle_class_unknown", "interval": interval})
            elif _normalize_key(trip.vehicle_class) == _normalize_key(ban.vehicle_class):
                matches.append({"ban": ban, "match_type": "vehicle_class_exact", "interval": interval})
        else:
            matches.append({"ban": ban, "match_type": "generic_vehicle_class", "interval": interval})
    return matches, unknown_class


def _severity(risk_bucket: str, overlap_minutes: float = 0.0) -> str:
    if risk_bucket == "BAN CONFLICT" and overlap_minutes >= 120:
        return "CRITICAL"
    if risk_bucket == "BAN CONFLICT":
        return "HIGH"
    if risk_bucket in {"WATCH", "VEHICLE CLASS UNKNOWN"}:
        return "MEDIUM"
    if risk_bucket in {"MISSING CITY", "MISSING TIMING", "DATA MISSING"}:
        return "LOW"
    return "OK"


def _confidence(
    risk_bucket: str,
    *,
    city_inferred: bool,
    timing_source: str,
    matched_vehicle_class_required: bool,
    generic_vehicle_rule: bool,
) -> str:
    if risk_bucket in {"DATA MISSING", "MISSING CITY", "MISSING TIMING"}:
        return "DATA MISSING"
    if city_inferred or timing_source == "eta_risk_board":
        return "LOW"
    if generic_vehicle_rule or not matched_vehicle_class_required:
        return "MEDIUM"
    return "HIGH"


def _empty_board_row(
    trip: pd.Series,
    city: str | None,
    predicted_arrival: pd.Timestamp | pd.NaT,
    movement_start: pd.Timestamp | pd.NaT,
    movement_end: pd.Timestamp | pd.NaT,
    risk_bucket: str,
    confidence_bucket: str,
    evidence: str,
    suggested_action: str,
) -> dict[str, Any]:
    return {
        "trip_id": trip.trip_id,
        "vehicle_id": trip.vehicle_id,
        "customer_name": trip.customer_name,
        "carrier_name": trip.carrier_name,
        "origin": trip.origin,
        "destination": trip.destination,
        "city": city,
        "vehicle_class": trip.vehicle_class,
        "planned_departure": trip.planned_departure,
        "promised_arrival": trip.promised_arrival,
        "predicted_arrival": predicted_arrival,
        "movement_start": movement_start,
        "movement_end": movement_end,
        "matched_ban_id": None,
        "ban_city": None,
        "ban_location_name": None,
        "ban_vehicle_class": None,
        "ban_window_start": pd.NaT,
        "ban_window_end": pd.NaT,
        "overlap_minutes": 0.0,
        "risk_bucket": risk_bucket,
        "severity": _severity(risk_bucket),
        "confidence_bucket": confidence_bucket,
        "evidence": evidence,
        "suggested_action": suggested_action,
    }


def _row_for_match(
    trip: pd.Series,
    city: str,
    predicted_arrival: pd.Timestamp | pd.NaT,
    movement_start: pd.Timestamp,
    movement_end: pd.Timestamp,
    match: dict[str, Any],
    risk_bucket: str,
    overlap_minutes: float,
    confidence_bucket: str,
    evidence: str,
    suggested_action: str,
) -> dict[str, Any]:
    ban = match["ban"]
    ban_start, ban_end = match["interval"]
    return {
        "trip_id": trip.trip_id,
        "vehicle_id": trip.vehicle_id,
        "customer_name": trip.customer_name,
        "carrier_name": trip.carrier_name,
        "origin": trip.origin,
        "destination": trip.destination,
        "city": city,
        "vehicle_class": trip.vehicle_class,
        "planned_departure": trip.planned_departure,
        "promised_arrival": trip.promised_arrival,
        "predicted_arrival": predicted_arrival,
        "movement_start": movement_start,
        "movement_end": movement_end,
        "matched_ban_id": ban.ban_id,
        "ban_city": ban.city,
        "ban_location_name": ban.location_name,
        "ban_vehicle_class": ban.vehicle_class,
        "ban_window_start": ban_start,
        "ban_window_end": ban_end,
        "overlap_minutes": overlap_minutes,
        "risk_bucket": risk_bucket,
        "severity": _severity(risk_bucket, overlap_minutes),
        "confidence_bucket": confidence_bucket,
        "evidence": evidence,
        "suggested_action": suggested_action,
    }


def _classify_trip(
    trip: pd.Series,
    ban_windows: pd.DataFrame,
    eta: pd.Series | None,
    settings: BanWindowSettings,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    city, city_inferred = _infer_city(trip, ban_windows)
    movement_start, movement_end, predicted_arrival, timing_source = _movement_interval(trip, eta)

    if pd.isna(trip.trip_id) or pd.isna(trip.vehicle_id) or pd.isna(trip.origin) or pd.isna(trip.destination):
        return _empty_board_row(
            trip,
            city,
            predicted_arrival,
            movement_start,
            movement_end,
            "DATA MISSING",
            "DATA MISSING",
            "A required trip field is missing or invalid.",
            "Fix required trip fields before restriction-window review.",
        ), []
    if city is None:
        return _empty_board_row(
            trip,
            city,
            predicted_arrival,
            movement_start,
            movement_end,
            "MISSING CITY",
            "DATA MISSING",
            "Trip has no city and no simple city inference from origin or destination text.",
            "Add the planning city before dispatch review.",
        ), []
    if pd.isna(movement_start) or pd.isna(movement_end) or movement_end <= movement_start:
        return _empty_board_row(
            trip,
            city,
            predicted_arrival,
            movement_start,
            movement_end,
            "MISSING TIMING",
            "DATA MISSING",
            "Trip has no usable planned, predicted, or city-entry movement interval.",
            "Add planned departure and arrival, city entry and exit, or predicted arrival timing.",
        ), []

    matches, unknown_class = _matching_windows(trip, city, ban_windows, movement_start)
    if unknown_class:
        unknown_match = next(match for match in matches if match["match_type"] == "vehicle_class_unknown")
        return _row_for_match(
            trip,
            city,
            predicted_arrival,
            movement_start,
            movement_end,
            unknown_match,
            "VEHICLE CLASS UNKNOWN",
            0.0,
            "MEDIUM",
            "An uploaded restriction window requires vehicle class, but this trip has no vehicle class.",
            "Confirm vehicle class before relying on this plan.",
        ), []

    candidate_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for match in matches:
        ban_start, ban_end = match["interval"]
        overlap = interval_overlap_minutes(movement_start, movement_end, ban_start, ban_end)
        buffer_start = movement_start - pd.Timedelta(minutes=settings.watch_buffer_before_minutes)
        buffer_end = movement_end + pd.Timedelta(minutes=settings.watch_buffer_after_minutes)
        buffered_overlap = interval_overlap_minutes(buffer_start, buffer_end, ban_start, ban_end)
        required_class = pd.notna(match["ban"].vehicle_class)
        generic_rule = match["match_type"] == "generic_vehicle_class"
        confidence_bucket = _confidence(
            "CLEAR",
            city_inferred=city_inferred,
            timing_source=timing_source,
            matched_vehicle_class_required=required_class,
            generic_vehicle_rule=generic_rule,
        )
        if overlap >= settings.minimum_conflict_overlap_minutes:
            evidence = f"Movement overlaps uploaded restriction window by {overlap:.0f} minutes."
            row = _row_for_match(
                trip,
                city,
                predicted_arrival,
                movement_start,
                movement_end,
                match,
                "BAN CONFLICT",
                overlap,
                confidence_bucket,
                evidence,
                "Needs planning review before dispatch or arrival commitment.",
            )
            candidate_rows.append(row)
            conflict_rows.append(
                {
                    "trip_id": trip.trip_id,
                    "vehicle_id": trip.vehicle_id,
                    "customer_name": trip.customer_name,
                    "carrier_name": trip.carrier_name,
                    "city": city,
                    "vehicle_class": trip.vehicle_class,
                    "matched_ban_id": match["ban"].ban_id,
                    "ban_window_start": ban_start,
                    "ban_window_end": ban_end,
                    "overlap_minutes": overlap,
                    "exception_type": "BAN CONFLICT",
                    "severity": _severity("BAN CONFLICT", overlap),
                    "evidence": evidence,
                    "suggested_action": "Review dispatch or arrival plan against the uploaded restriction window.",
                }
            )
        elif buffered_overlap > 0:
            candidate_rows.append(
                _row_for_match(
                    trip,
                    city,
                    predicted_arrival,
                    movement_start,
                    movement_end,
                    match,
                    "WATCH",
                    0.0,
                    confidence_bucket,
                    "Movement is within the configured buffer around an uploaded restriction window.",
                    "Monitor timing and keep a planning buffer.",
                )
            )

    if candidate_rows:
        strongest = sorted(
            candidate_rows,
            key=lambda row: (RISK_RANK[row["risk_bucket"]], row["overlap_minutes"]),
            reverse=True,
        )[0]
        return strongest, conflict_rows

    confidence_bucket = _confidence(
        "CLEAR",
        city_inferred=city_inferred,
        timing_source=timing_source,
        matched_vehicle_class_required=False,
        generic_vehicle_rule=True,
    )
    return _empty_board_row(
        trip,
        city,
        predicted_arrival,
        movement_start,
        movement_end,
        "CLEAR",
        confidence_bucket,
        "No overlap or watch condition found against applicable uploaded restriction windows.",
        "No restriction-window action needed from this file check.",
    ), []


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
    prepare_visit_events(visit_events_df)
    expanded = expand_ban_windows_for_trips(ban_windows, trips)
    eta_by_trip = eta.set_index("trip_id") if not eta.empty else pd.DataFrame()

    risk_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for trip_tuple in trips.itertuples(index=False):
        trip = pd.Series(trip_tuple._asdict())
        eta_row = eta_by_trip.loc[trip.trip_id] if trip.trip_id in eta_by_trip.index else None
        risk_row, trip_conflicts = _classify_trip(trip, ban_windows, eta_row, active_settings)
        risk_rows.append(risk_row)
        conflict_rows.extend(trip_conflicts)

    risk_board = pd.DataFrame(risk_rows, columns=BAN_RISK_COLUMNS)
    conflicts = pd.DataFrame(conflict_rows, columns=BAN_CONFLICT_COLUMNS)
    kpis = {
        "total_trips": float(len(risk_board)),
        "conflict_trips": float((risk_board["risk_bucket"] == "BAN CONFLICT").sum()) if not risk_board.empty else 0.0,
        "watch_trips": float((risk_board["risk_bucket"] == "WATCH").sum()) if not risk_board.empty else 0.0,
        "missing_data_trips": float(
            risk_board["risk_bucket"].isin(
                ["MISSING TIMING", "MISSING CITY", "VEHICLE CLASS UNKNOWN", "DATA MISSING"]
            ).sum()
        )
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
