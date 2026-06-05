"""Deterministic fuel-vs-GPS reconciliation engine for FuelGuard."""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from fuel_guard.models import FuelEventRecord, FuelSiteRecord, GpsPointRecord, TripRecord, VisitEventRecord


REQUIRED_FUEL_COLUMNS = {"fuel_event_id", "vehicle_id", "fuel_time", "liters"}
REQUIRED_VISIT_COLUMNS = {
    "vehicle_id",
    "geofence_id",
    "geofence_name",
    "geofence_type",
    "enter_time",
    "exit_time",
    "dwell_minutes",
}
REQUIRED_GPS_COLUMNS = {"vehicle_id", "timestamp", "lat", "lon"}
REQUIRED_SITE_COLUMNS = {"station_name", "lat", "lon"}
REQUIRED_TRIP_COLUMNS = {"trip_id", "vehicle_id", "planned_departure", "promised_arrival"}
FUEL_GEOFENCE_TYPES = {"FUEL", "FUELSTATION", "PETROL", "DIESEL", "STATION"}
RISK_ORDER = ["HIGH RISK", "DATA MISSING", "REVIEW", "OK"]
STATUS_ORDER = RISK_ORDER
REPORT_COLUMNS = [
    "fuel_event_id",
    "vehicle_id",
    "fuel_time",
    "station_id",
    "station_name",
    "liters",
    "amount",
    "odometer",
    "receipt_no",
    "trip_id",
    "carrier_name",
    "matched_evidence_type",
    "matched_event_time",
    "matched_geofence_name",
    "matched_gps_lat",
    "matched_gps_lon",
    "distance_to_station_m",
    "stop_evidence",
    "in_trip_window",
    "exception_flags",
    "risk_bucket",
    "severity",
    "evidence",
    "suggested_action",
]
EXCEPTION_COLUMNS = [
    "fuel_event_id",
    "vehicle_id",
    "fuel_time",
    "station_name",
    "liters",
    "receipt_no",
    "exception_type",
    "severity",
    "evidence",
    "suggested_action",
]


@dataclass(frozen=True)
class FuelGuardResult:
    """Structured outputs from a FuelGuard run."""

    fuel_reconciliation_report: pd.DataFrame
    fuel_exceptions: pd.DataFrame
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


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return haversine distance in meters."""
    radius_m = 6_371_000
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    value = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return round(2 * radius_m * asin(sqrt(value)), 2)


def prepare_fuel_events(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate uploaded fuel events."""
    source = _normalize_columns(df).dropna(how="all").copy()
    optional_columns = [
        "station_name",
        "station_id",
        "lat",
        "lon",
        "amount",
        "odometer",
        "receipt_no",
        "currency",
        "driver_name",
        "carrier_name",
        "trip_id",
    ]
    for column in optional_columns:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_FUEL_COLUMNS, "fuel_events")

    source["fuel_event_id"] = source["fuel_event_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["fuel_time"] = _to_utc(source["fuel_time"])
    source["liters"] = pd.to_numeric(source["liters"], errors="coerce")
    source["station_name"] = source["station_name"].map(_normalize_text)
    source["station_id"] = source["station_id"].map(_normalize_key)
    source["lat"] = pd.to_numeric(source["lat"], errors="coerce")
    source["lon"] = pd.to_numeric(source["lon"], errors="coerce")
    source["amount"] = pd.to_numeric(source["amount"], errors="coerce")
    source["odometer"] = pd.to_numeric(source["odometer"], errors="coerce")
    source["receipt_no"] = source["receipt_no"].map(_normalize_text)
    source["receipt_key"] = source["receipt_no"].map(_normalize_key)
    source["currency"] = source["currency"].map(_normalize_text)
    source["driver_name"] = source["driver_name"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source = source.dropna(subset=["fuel_event_id", "vehicle_id", "fuel_time", "liters"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            FuelEventRecord(
                fuel_event_id=str(row.fuel_event_id),
                vehicle_id=str(row.vehicle_id),
                fuel_time=row.fuel_time.to_pydatetime(),
                liters=float(row.liters),
                station_name=None if pd.isna(row.station_name) else row.station_name,
                station_id=None if pd.isna(row.station_id) else row.station_id,
                lat=None if pd.isna(row.lat) else float(row.lat),
                lon=None if pd.isna(row.lon) else float(row.lon),
                amount=None if pd.isna(row.amount) else float(row.amount),
                odometer=None if pd.isna(row.odometer) else float(row.odometer),
                receipt_no=None if pd.isna(row.receipt_no) else row.receipt_no,
                currency=None if pd.isna(row.currency) else row.currency,
                driver_name=None if pd.isna(row.driver_name) else row.driver_name,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                trip_id=None if pd.isna(row.trip_id) else row.trip_id,
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"fuel_events contains invalid rows: {errors[0]}")

    columns = [
        "fuel_event_id",
        "vehicle_id",
        "fuel_time",
        "liters",
        "station_name",
        "station_id",
        "lat",
        "lon",
        "amount",
        "odometer",
        "receipt_no",
        "receipt_key",
        "currency",
        "driver_name",
        "carrier_name",
        "trip_id",
    ]
    return source[columns].reset_index(drop=True)


def prepare_visit_events(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional GeoReplay visit events used as stop evidence."""
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


def prepare_gps_points(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional GPS point evidence."""
    columns = ["vehicle_id", "timestamp", "lat", "lon", "speed_kph"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    if "speed_kph" not in source.columns:
        source["speed_kph"] = pd.NA
    _require_columns(source, REQUIRED_GPS_COLUMNS, "gps_points")
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["timestamp"] = _to_utc(source["timestamp"])
    source["lat"] = pd.to_numeric(source["lat"], errors="coerce")
    source["lon"] = pd.to_numeric(source["lon"], errors="coerce")
    source["speed_kph"] = pd.to_numeric(source["speed_kph"], errors="coerce")
    source = source.dropna(subset=["vehicle_id", "timestamp", "lat", "lon"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            GpsPointRecord(
                vehicle_id=str(row.vehicle_id),
                timestamp=row.timestamp.to_pydatetime(),
                lat=float(row.lat),
                lon=float(row.lon),
                speed_kph=None if pd.isna(row.speed_kph) else float(row.speed_kph),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"gps_points contains invalid rows: {errors[0]}")

    return source[columns].reset_index(drop=True)


def prepare_fuel_sites(df: pd.DataFrame | None, default_radius_m: float = 500) -> pd.DataFrame:
    """Normalize optional fuel-site master data."""
    columns = ["station_id", "station_name", "station_key", "lat", "lon", "radius_m"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    if "station_id" not in source.columns:
        source["station_id"] = pd.NA
    if "radius_m" not in source.columns:
        source["radius_m"] = default_radius_m
    _require_columns(source, REQUIRED_SITE_COLUMNS, "fuel_sites")
    source["station_id"] = source["station_id"].map(_normalize_key)
    source["station_name"] = source["station_name"].map(_normalize_text)
    source["station_key"] = source["station_name"].map(_normalize_search)
    source["lat"] = pd.to_numeric(source["lat"], errors="coerce")
    source["lon"] = pd.to_numeric(source["lon"], errors="coerce")
    source["radius_m"] = pd.to_numeric(source["radius_m"], errors="coerce").fillna(
        default_radius_m
    )
    source = source.dropna(subset=["station_name", "lat", "lon"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            FuelSiteRecord(
                station_id=None if pd.isna(row.station_id) else row.station_id,
                station_name=str(row.station_name),
                lat=float(row.lat),
                lon=float(row.lon),
                radius_m=float(row.radius_m),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"fuel_sites contains invalid rows: {errors[0]}")

    return source[columns].reset_index(drop=True)


def prepare_trips(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional trip context rows for trip-window checks."""
    columns = [
        "trip_id",
        "vehicle_id",
        "customer_name",
        "carrier_name",
        "origin",
        "destination",
        "planned_departure",
        "promised_arrival",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    for column in ["customer_name", "carrier_name", "origin", "destination"]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")
    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source["promised_arrival"] = _to_utc(source["promised_arrival"])
    source = source.dropna(subset=["trip_id", "vehicle_id"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                vehicle_id=str(row.vehicle_id),
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                carrier_name=None if pd.isna(row.carrier_name) else row.carrier_name,
                origin=None if pd.isna(row.origin) else row.origin,
                destination=None if pd.isna(row.destination) else row.destination,
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

    return source[columns].drop_duplicates("trip_id").reset_index(drop=True)


def _match_site(fuel: pd.Series, sites: pd.DataFrame) -> pd.Series | None:
    """Find the most relevant known fuel site for one event."""
    if sites.empty:
        return None
    if fuel.get("station_id"):
        by_id = sites[sites["station_id"] == fuel["station_id"]]
        if not by_id.empty:
            return by_id.iloc[0]
    station_key = _normalize_search(fuel.get("station_name"))
    if station_key:
        name_matches = sites["station_key"].fillna("").map(
            lambda key: bool(key) and (station_key in key or key in station_key)
        )
        by_name = sites[name_matches]
        if not by_name.empty:
            return by_name.iloc[0]
    if pd.notna(fuel.get("lat")) and pd.notna(fuel.get("lon")):
        scored = sites.copy()
        scored["_distance_m"] = scored.apply(
            lambda row: _distance_m(float(fuel["lat"]), float(fuel["lon"]), row["lat"], row["lon"]),
            axis=1,
        )
        nearest = scored.sort_values("_distance_m").iloc[0]
        if nearest["_distance_m"] <= max(float(nearest["radius_m"]), 250):
            return nearest
    return None


def _target_location(fuel: pd.Series, site: pd.Series | None) -> tuple[float | None, float | None]:
    if pd.notna(fuel.get("lat")) and pd.notna(fuel.get("lon")):
        return float(fuel["lat"]), float(fuel["lon"])
    if site is not None:
        return float(site["lat"]), float(site["lon"])
    return None, None


def _nearest_gps(
    fuel: pd.Series,
    gps_points: pd.DataFrame,
    target_lat: float | None,
    target_lon: float | None,
    time_window_minutes: float,
) -> pd.Series | None:
    """Return the nearest GPS point by fuel time and site distance."""
    if gps_points.empty or target_lat is None or target_lon is None:
        return None
    window = pd.Timedelta(minutes=time_window_minutes)
    candidates = gps_points[
        (gps_points["vehicle_id"] == fuel["vehicle_id"])
        & (gps_points["timestamp"] >= fuel["fuel_time"] - window)
        & (gps_points["timestamp"] <= fuel["fuel_time"] + window)
    ].copy()
    if candidates.empty:
        return None
    candidates["_distance_m"] = candidates.apply(
        lambda row: _distance_m(target_lat, target_lon, row["lat"], row["lon"]),
        axis=1,
    )
    candidates["_time_distance_minutes"] = (
        (candidates["timestamp"] - fuel["fuel_time"]).dt.total_seconds().abs().div(60)
    )
    return candidates.sort_values(["_distance_m", "_time_distance_minutes"]).iloc[0]


def _select_visit(
    fuel: pd.Series,
    visits: pd.DataFrame,
    time_window_minutes: float,
) -> pd.Series | None:
    """Return the best visit evidence for one fuel event."""
    if visits.empty:
        return None
    open_visit_window = pd.Timedelta(minutes=max(time_window_minutes, 120))
    candidates = visits[
        (visits["vehicle_id"] == fuel["vehicle_id"])
        & (visits["enter_time"] <= fuel["fuel_time"])
        & (
            (visits["exit_time"] >= fuel["fuel_time"])
            | (visits["exit_time"].isna() & (fuel["fuel_time"] <= visits["enter_time"] + open_visit_window))
        )
    ].copy()
    if candidates.empty:
        return None

    station_key = _normalize_search(fuel.get("station_name"))
    type_match = candidates["geofence_type"].isin(FUEL_GEOFENCE_TYPES)
    name_match = pd.Series(False, index=candidates.index)
    if station_key:
        name_match = candidates["geofence_name"].map(_normalize_search).fillna("").str.contains(
            station_key,
            regex=False,
        )

    if type_match.any() or name_match.any():
        candidates = candidates[type_match | name_match].copy()
    if candidates.empty:
        return None

    candidates["_time_distance_minutes"] = (
        (candidates["enter_time"].fillna(candidates["exit_time"]) - fuel["fuel_time"])
        .dt.total_seconds()
        .abs()
        .div(60)
    )
    return candidates.sort_values(["_time_distance_minutes"]).iloc[0]


def _match_trip(fuel: pd.Series, trips: pd.DataFrame) -> tuple[pd.Series | None, str]:
    """Match trip context by exact trip ID, then vehicle/time window."""
    if trips.empty:
        return None, "NOT PROVIDED"
    if fuel.get("trip_id"):
        exact = trips[trips["trip_id"] == fuel["trip_id"]]
        if exact.empty:
            return None, "OUTSIDE TRIP WINDOW"
        trip = exact.iloc[0]
        if (
            pd.notna(trip["planned_departure"])
            and pd.notna(trip["promised_arrival"])
            and trip["planned_departure"] <= fuel["fuel_time"] <= trip["promised_arrival"]
        ):
            return trip, "INSIDE TRIP WINDOW"
        return trip, "OUTSIDE TRIP WINDOW"

    vehicle_trips = trips[trips["vehicle_id"] == fuel["vehicle_id"]].copy()
    if vehicle_trips.empty:
        return None, "OUTSIDE TRIP WINDOW"
    inside = vehicle_trips[
        (vehicle_trips["planned_departure"] <= fuel["fuel_time"])
        & (vehicle_trips["promised_arrival"] >= fuel["fuel_time"])
    ]
    if inside.empty:
        return None, "OUTSIDE TRIP WINDOW"
    return inside.sort_values("planned_departure").iloc[0], "INSIDE TRIP WINDOW"


def _receipt_duplicate_mask(fuels: pd.DataFrame) -> pd.Series:
    has_receipt = fuels["receipt_key"].notna()
    return has_receipt & fuels.duplicated(["receipt_key"], keep=False)


def _odometer_anomaly_mask(fuels: pd.DataFrame) -> pd.Series:
    mask = pd.Series(False, index=fuels.index)
    for _, vehicle_rows in fuels.sort_values("fuel_time").groupby("vehicle_id"):
        previous_odometer: float | None = None
        for index, row in vehicle_rows.iterrows():
            if pd.isna(row["odometer"]):
                continue
            odometer = float(row["odometer"])
            if previous_odometer is not None and odometer <= previous_odometer:
                mask.loc[index] = True
            previous_odometer = odometer
    return mask


def _high_liter_mask(fuels: pd.DataFrame, high_liter_threshold: float) -> pd.Series:
    mask = fuels["liters"] > high_liter_threshold
    medians = fuels.groupby("vehicle_id")["liters"].transform("median")
    return mask | ((medians > 0) & (fuels["liters"] > medians * 1.8) & (fuels["liters"] >= 250))


def _risk_bucket(flags: list[str]) -> str:
    if not flags:
        return "OK"
    if "NO GPS EVIDENCE" in flags:
        return "DATA MISSING"
    high_flags = {"DUPLICATE RECEIPT", "ODOMETER DROP", "OUTSIDE TRIP WINDOW"}
    if any(flag in high_flags for flag in flags):
        return "HIGH RISK"
    return "REVIEW"


def _severity(flags: list[str]) -> str:
    high = {"DUPLICATE RECEIPT", "ODOMETER DROP", "NO GPS EVIDENCE", "OUTSIDE TRIP WINDOW"}
    medium = {"NO STOP NEAR FUEL", "HIGH LITERS", "UNKNOWN STATION"}
    if any(flag in high for flag in flags):
        return "HIGH"
    if any(flag in medium for flag in flags):
        return "MEDIUM"
    return "LOW"


def _suggested_action(flags: list[str]) -> str:
    if "NO GPS EVIDENCE" in flags:
        return "Review GPS or GeoReplay evidence before accepting this fuel event."
    if "OUTSIDE TRIP WINDOW" in flags:
        return "Confirm whether the fuel event belongs to the assigned trip or another movement."
    if "NO STOP NEAR FUEL" in flags:
        return "Check whether the vehicle actually stopped long enough near the fuel site."
    if "DUPLICATE RECEIPT" in flags:
        return "Review receipt number and transaction source for duplicate entry."
    if "ODOMETER DROP" in flags:
        return "Review odometer sequence for the vehicle before closing the case."
    if "HIGH LITERS" in flags:
        return "Check tank capacity, receipt liters, and prior fills."
    if "UNKNOWN STATION" in flags:
        return "Confirm station master data or transaction station details."
    return "Fuel event has supporting location and stop evidence; no review action needed."


def _evidence_text(
    nearest_gps: pd.Series | None,
    visit: pd.Series | None,
    site: pd.Series | None,
    gps_distance_threshold_m: float,
) -> str:
    pieces: list[str] = []
    if site is not None:
        pieces.append(f"matched site {site['station_name']}")
    if nearest_gps is not None:
        pieces.append(
            f"nearest GPS at {nearest_gps['timestamp']} was {nearest_gps['_distance_m']:.0f}m from fuel site"
        )
    if visit is not None:
        pieces.append(
            f"stop visit {visit['geofence_name']} from {visit['enter_time']} to {visit['exit_time']} "
            f"with dwell {visit['dwell_minutes']} minutes"
        )
    if nearest_gps is not None and nearest_gps["_distance_m"] > gps_distance_threshold_m:
        pieces.append("nearest GPS was outside the configured distance threshold")
    if not pieces:
        return "No supporting GPS or GeoReplay stop evidence found for this fuel event."
    return "; ".join(pieces)


def build_fuel_reconciliation_report(
    fuel_events: pd.DataFrame,
    visit_events: pd.DataFrame | None = None,
    gps_points: pd.DataFrame | None = None,
    fuel_sites: pd.DataFrame | None = None,
    trips: pd.DataFrame | None = None,
    gps_time_window_minutes: float = 30,
    gps_distance_threshold_m: float = 500,
    minimum_stop_minutes: float = 10,
    high_liter_threshold: float = 450,
    stop_speed_threshold_kph: float = 5,
) -> pd.DataFrame:
    """Build the manager-ready FuelGuard reconciliation report."""
    fuels = prepare_fuel_events(fuel_events)
    visits = prepare_visit_events(visit_events)
    gps = prepare_gps_points(gps_points)
    sites = prepare_fuel_sites(fuel_sites, default_radius_m=gps_distance_threshold_m)
    trip_rows = prepare_trips(trips)
    duplicate_mask = _receipt_duplicate_mask(fuels)
    odometer_mask = _odometer_anomaly_mask(fuels)
    high_liter_mask = _high_liter_mask(fuels, high_liter_threshold)

    rows: list[dict[str, Any]] = []
    for fuel in fuels.itertuples(index=True):
        fuel_series = pd.Series(fuel._asdict())
        original_index = int(fuel_series["Index"])
        site = _match_site(fuel_series, sites)
        target_lat, target_lon = _target_location(fuel_series, site)
        nearest_gps = _nearest_gps(
            fuel_series,
            gps,
            target_lat,
            target_lon,
            gps_time_window_minutes,
        )
        visit = _select_visit(fuel_series, visits, gps_time_window_minutes)
        trip, trip_window_status = _match_trip(fuel_series, trip_rows)

        site_radius = gps_distance_threshold_m if site is None else float(site["radius_m"])
        gps_supported = nearest_gps is not None and nearest_gps["_distance_m"] <= site_radius
        gps_stop_supported = (
            nearest_gps is not None
            and pd.notna(nearest_gps.get("speed_kph"))
            and float(nearest_gps["speed_kph"]) <= stop_speed_threshold_kph
            and gps_supported
        )
        stop_supported = (
            visit is not None
            and pd.notna(visit.get("dwell_minutes"))
            and float(visit["dwell_minutes"]) >= minimum_stop_minutes
        ) or gps_stop_supported
        has_stop_inputs = (
            visit is not None and pd.notna(visit.get("dwell_minutes"))
        ) or (nearest_gps is not None and pd.notna(nearest_gps.get("speed_kph")))
        stop_evidence = "TRUE" if stop_supported else "FALSE" if has_stop_inputs else "UNKNOWN"
        has_station_identity = bool(fuel_series.get("station_id")) or bool(fuel_series.get("station_name"))

        flags: list[str] = []
        if not gps_supported and visit is None:
            flags.append("NO GPS EVIDENCE")
        if (gps_supported or visit is not None) and stop_evidence == "FALSE":
            flags.append("NO STOP NEAR FUEL")
        if not has_station_identity or (not sites.empty and site is None):
            flags.append("UNKNOWN STATION")
        if bool(duplicate_mask.loc[original_index]):
            flags.append("DUPLICATE RECEIPT")
        if bool(odometer_mask.loc[original_index]):
            flags.append("ODOMETER DROP")
        if bool(high_liter_mask.loc[original_index]):
            flags.append("HIGH LITERS")
        if trip_window_status == "OUTSIDE TRIP WINDOW":
            flags.append("OUTSIDE TRIP WINDOW")

        if trip is not None:
            trip_id = trip["trip_id"]
            carrier_name = fuel_series.get("carrier_name") or trip.get("carrier_name")
        else:
            trip_id = fuel_series.get("trip_id")
            carrier_name = fuel_series.get("carrier_name")

        matched_evidence_type = "NONE"
        matched_event_time = pd.NaT
        matched_geofence_name = None
        if visit is not None:
            matched_evidence_type = "VISIT"
            matched_event_time = fuel_series["fuel_time"]
            matched_geofence_name = visit["geofence_name"]
        elif nearest_gps is not None:
            matched_evidence_type = "GPS"
            matched_event_time = nearest_gps["timestamp"]
        elif target_lat is not None and target_lon is not None:
            matched_evidence_type = "FUEL EVENT LOCATION"
            matched_event_time = fuel_series["fuel_time"]

        in_trip_window = (
            "TRUE"
            if trip_window_status == "INSIDE TRIP WINDOW"
            else "FALSE"
            if trip_window_status == "OUTSIDE TRIP WINDOW"
            else "UNKNOWN"
        )
        risk_bucket = _risk_bucket(flags)
        rows.append(
            {
                "fuel_event_id": fuel_series["fuel_event_id"],
                "vehicle_id": fuel_series["vehicle_id"],
                "fuel_time": fuel_series["fuel_time"],
                "station_id": fuel_series["station_id"],
                "station_name": fuel_series["station_name"],
                "liters": fuel_series["liters"],
                "amount": fuel_series["amount"],
                "odometer": fuel_series["odometer"],
                "receipt_no": fuel_series["receipt_no"],
                "trip_id": trip_id,
                "carrier_name": carrier_name,
                "matched_evidence_type": matched_evidence_type,
                "matched_event_time": matched_event_time,
                "matched_geofence_name": matched_geofence_name,
                "matched_gps_lat": None if nearest_gps is None else nearest_gps["lat"],
                "matched_gps_lon": None if nearest_gps is None else nearest_gps["lon"],
                "distance_to_station_m": None if nearest_gps is None else nearest_gps["_distance_m"],
                "stop_evidence": stop_evidence,
                "in_trip_window": in_trip_window,
                "exception_flags": "; ".join(flags) if flags else "OK",
                "risk_bucket": risk_bucket,
                "severity": _severity(flags) if flags else "OK",
                "evidence": _evidence_text(nearest_gps, visit, site, gps_distance_threshold_m),
                "suggested_action": _suggested_action(flags),
            }
        )

    output = pd.DataFrame(rows)
    order_map = {status: index for index, status in enumerate(RISK_ORDER)}
    sorted_output = output.sort_values(
        by=["risk_bucket", "fuel_time"],
        key=lambda series: series.map(order_map) if series.name == "risk_bucket" else series,
    ).reset_index(drop=True)
    return sorted_output[REPORT_COLUMNS]


def run_fuel_guard(
    fuel_events: pd.DataFrame,
    visit_events: pd.DataFrame | None = None,
    gps_points: pd.DataFrame | None = None,
    fuel_sites: pd.DataFrame | None = None,
    trips: pd.DataFrame | None = None,
    gps_time_window_minutes: float = 30,
    gps_distance_threshold_m: float = 500,
    minimum_stop_minutes: float = 10,
    high_liter_threshold: float = 450,
    stop_speed_threshold_kph: float = 5,
) -> FuelGuardResult:
    """Run FuelGuard and return report, exception rows, and KPIs."""
    report = build_fuel_reconciliation_report(
        fuel_events,
        visit_events,
        gps_points,
        fuel_sites,
        trips,
        gps_time_window_minutes=gps_time_window_minutes,
        gps_distance_threshold_m=gps_distance_threshold_m,
        minimum_stop_minutes=minimum_stop_minutes,
        high_liter_threshold=high_liter_threshold,
        stop_speed_threshold_kph=stop_speed_threshold_kph,
    )
    exceptions = report[report["exception_flags"] != "OK"].copy()
    exceptions["exception_type"] = exceptions["exception_flags"]
    exceptions = exceptions[EXCEPTION_COLUMNS]
    kpis = {
        "total_fuel_events": int(len(report)),
        "matched_events": int((report["risk_bucket"] == "OK").sum()),
        "exception_events": int((report["exception_flags"] != "OK").sum()),
        "duplicate_receipts": int(report["exception_flags"].str.contains("DUPLICATE RECEIPT").sum()),
        "high_liter_events": int(report["exception_flags"].str.contains("HIGH LITERS").sum()),
        "total_liters_under_review": float(
            report.loc[report["exception_flags"] != "OK", "liters"].sum()
        ),
        "no_gps_evidence": int(report["exception_flags"].str.contains("NO GPS EVIDENCE").sum()),
        "no_stop_near_fuel": int(
            report["exception_flags"].str.contains("NO STOP NEAR FUEL").sum()
        ),
        "outside_trip_window": int(
            report["exception_flags"].str.contains("OUTSIDE TRIP WINDOW").sum()
        ),
        "unknown_station": int(report["exception_flags"].str.contains("UNKNOWN STATION").sum()),
    }
    return FuelGuardResult(
        fuel_reconciliation_report=report,
        fuel_exceptions=exceptions,
        kpis=kpis,
    )


def write_outputs(result: FuelGuardResult, output_dir: Path) -> tuple[Path, Path]:
    """Write FuelGuard CSV exports and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "fuel_reconciliation_report.csv"
    exceptions_path = output_dir / "fuel_exceptions.csv"
    result.fuel_reconciliation_report.to_csv(report_path, index=False)
    result.fuel_exceptions.to_csv(exceptions_path, index=False)
    return report_path, exceptions_path
