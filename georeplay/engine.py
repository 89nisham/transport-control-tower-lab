from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import pandas as pd
from geopy.geocoders import Nominatim
from pydantic import ValidationError

from georeplay.models import Geofence, GpsPoint, PlannedStop


WGS84 = "EPSG:4326"
METRIC_CRS = "EPSG:3857"
REQUIRED_GPS_COLUMNS = {"vehicle_id", "timestamp", "lat", "lon"}
REQUIRED_GEOFENCE_COLUMNS = {"geofence_id", "lat", "lon", "radius_m"}
REQUIRED_PLANNED_STOP_COLUMNS = {"vehicle_id", "geofence_id"}


@dataclass(frozen=True)
class GeoReplayResult:
    visit_events: pd.DataFrame
    exceptions: pd.DataFrame
    gps_points: gpd.GeoDataFrame
    geofences: gpd.GeoDataFrame
    inside_points: pd.DataFrame


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return normalized


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"{label} is missing required columns: {joined}")


def prepare_gps_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, REQUIRED_GPS_COLUMNS, "gps_points")
    source["timestamp"] = pd.to_datetime(source["timestamp"], errors="coerce")
    source["lat"] = pd.to_numeric(source["lat"], errors="coerce")
    source["lon"] = pd.to_numeric(source["lon"], errors="coerce")
    if "speed_kph" in source.columns:
        source["speed_kph"] = pd.to_numeric(source["speed_kph"], errors="coerce")
    else:
        source["speed_kph"] = pd.NA

    source = source.dropna(subset=["vehicle_id", "timestamp", "lat", "lon"]).copy()
    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            GpsPoint(
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

    geometry = gpd.points_from_xy(source["lon"], source["lat"], crs=WGS84)
    gps = gpd.GeoDataFrame(source, geometry=geometry, crs=WGS84)
    return gps.sort_values(["vehicle_id", "timestamp"]).reset_index(drop=True)


def prepare_geofences(df: pd.DataFrame) -> gpd.GeoDataFrame:
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, REQUIRED_GEOFENCE_COLUMNS, "geofences")
    if "name" not in source.columns:
        source["name"] = source["geofence_id"]
    if "geofence_type" not in source.columns:
        source["geofence_type"] = "site"

    source["lat"] = pd.to_numeric(source["lat"], errors="coerce")
    source["lon"] = pd.to_numeric(source["lon"], errors="coerce")
    source["radius_m"] = pd.to_numeric(source["radius_m"], errors="coerce")
    source = source.dropna(subset=["geofence_id", "lat", "lon", "radius_m"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            Geofence(
                geofence_id=str(row.geofence_id),
                name=None if pd.isna(row.name) else str(row.name),
                lat=float(row.lat),
                lon=float(row.lon),
                radius_m=float(row.radius_m),
                geofence_type=None if pd.isna(row.geofence_type) else str(row.geofence_type),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"geofences contains invalid rows: {errors[0]}")

    centers = gpd.GeoDataFrame(
        source,
        geometry=gpd.points_from_xy(source["lon"], source["lat"], crs=WGS84),
        crs=WGS84,
    )
    metric = centers.to_crs(METRIC_CRS)
    metric["geometry"] = metric.geometry.buffer(metric["radius_m"])
    polygons = metric.to_crs(WGS84)
    polygons["center_lat"] = centers["lat"].to_numpy()
    polygons["center_lon"] = centers["lon"].to_numpy()
    return polygons.reset_index(drop=True)


def prepare_planned_stops(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["vehicle_id", "geofence_id", "planned_arrival", "stop_sequence"])
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, REQUIRED_PLANNED_STOP_COLUMNS, "planned_stops")
    if "planned_arrival" not in source.columns:
        source["planned_arrival"] = pd.NaT
    if "stop_sequence" not in source.columns:
        source["stop_sequence"] = pd.NA
    source["planned_arrival"] = pd.to_datetime(source["planned_arrival"], errors="coerce")

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            PlannedStop(
                vehicle_id=str(row.vehicle_id),
                geofence_id=str(row.geofence_id),
                planned_arrival=None
                if pd.isna(row.planned_arrival)
                else row.planned_arrival.to_pydatetime(),
                stop_sequence=None if pd.isna(row.stop_sequence) else int(row.stop_sequence),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"planned_stops contains invalid rows: {errors[0]}")

    return source[["vehicle_id", "geofence_id", "planned_arrival", "stop_sequence"]].reset_index(
        drop=True
    )


def detect_inside_points(gps_points: gpd.GeoDataFrame, geofences: gpd.GeoDataFrame) -> pd.DataFrame:
    gps_metric = gps_points.to_crs(METRIC_CRS)
    geofences_metric = geofences.to_crs(METRIC_CRS)
    rows: list[dict[str, Any]] = []

    for gps_row in gps_metric.itertuples():
        for fence_row in geofences_metric.itertuples():
            if gps_row.geometry.within(fence_row.geometry):
                rows.append(
                    {
                        "vehicle_id": gps_row.vehicle_id,
                        "timestamp": gps_row.timestamp,
                        "lat": gps_row.lat,
                        "lon": gps_row.lon,
                        "speed_kph": gps_row.speed_kph,
                        "geofence_id": fence_row.geofence_id,
                        "geofence_name": fence_row.name,
                        "geofence_type": fence_row.geofence_type,
                    }
                )
    return pd.DataFrame(rows)


def reconstruct_visit_events(inside_points: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "event_id",
        "vehicle_id",
        "geofence_id",
        "geofence_name",
        "geofence_type",
        "entry_time",
        "exit_time",
        "dwell_minutes",
        "ping_count",
        "event_lat",
        "event_lon",
    ]
    if inside_points.empty:
        return pd.DataFrame(columns=columns)

    visits: list[dict[str, Any]] = []
    for (vehicle_id, geofence_id), group in inside_points.groupby(["vehicle_id", "geofence_id"]):
        group = group.sort_values("timestamp").reset_index(drop=True)
        time_diffs = group["timestamp"].diff().dt.total_seconds().fillna(0)
        segment_ids = (time_diffs > 3600).cumsum()
        for segment_number, segment in group.groupby(segment_ids):
            entry_time = segment["timestamp"].min()
            exit_time = segment["timestamp"].max()
            dwell_minutes = round((exit_time - entry_time).total_seconds() / 60, 2)
            event_id = f"{vehicle_id}-{geofence_id}-{entry_time:%Y%m%d%H%M%S}-{segment_number}"
            visits.append(
                {
                    "event_id": event_id,
                    "vehicle_id": vehicle_id,
                    "geofence_id": geofence_id,
                    "geofence_name": segment["geofence_name"].iloc[0],
                    "geofence_type": segment["geofence_type"].iloc[0],
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "dwell_minutes": dwell_minutes,
                    "ping_count": int(len(segment)),
                    "event_lat": round(float(segment["lat"].mean()), 6),
                    "event_lon": round(float(segment["lon"].mean()), 6),
                }
            )
    return pd.DataFrame(visits, columns=columns).sort_values(["vehicle_id", "entry_time"])


def detect_exceptions(
    visit_events: pd.DataFrame,
    planned_stops: pd.DataFrame,
    long_dwell_minutes: float = 45,
) -> pd.DataFrame:
    columns = [
        "exception_id",
        "vehicle_id",
        "geofence_id",
        "geofence_name",
        "exception_type",
        "severity",
        "confidence",
        "evidence",
        "suggested_action",
        "event_id",
        "event_lat",
        "event_lon",
        "review_status",
    ]
    exceptions: list[dict[str, Any]] = []

    for row in visit_events.itertuples(index=False):
        if row.dwell_minutes >= long_dwell_minutes:
            exceptions.append(
                {
                    "exception_id": f"LONG_DWELL-{row.event_id}",
                    "vehicle_id": row.vehicle_id,
                    "geofence_id": row.geofence_id,
                    "geofence_name": row.geofence_name,
                    "exception_type": "long_dwell",
                    "severity": "high" if row.dwell_minutes >= 60 else "medium",
                    "confidence": "HIGH",
                    "evidence": f"Dwell was {row.dwell_minutes} minutes.",
                    "suggested_action": "Check loading, unloading, queue, breakdown, or driver delay reason.",
                    "event_id": row.event_id,
                    "event_lat": row.event_lat,
                    "event_lon": row.event_lon,
                    "review_status": "open",
                }
            )

    if not planned_stops.empty:
        visited_pairs = set(zip(visit_events["vehicle_id"], visit_events["geofence_id"], strict=False))
        planned_pairs = set(zip(planned_stops["vehicle_id"], planned_stops["geofence_id"], strict=False))

        for planned in planned_stops.itertuples(index=False):
            if (planned.vehicle_id, planned.geofence_id) not in visited_pairs:
                exceptions.append(
                    {
                        "exception_id": f"MISSED-{planned.vehicle_id}-{planned.geofence_id}",
                        "vehicle_id": planned.vehicle_id,
                        "geofence_id": planned.geofence_id,
                        "geofence_name": None,
                        "exception_type": "missed_planned_stop",
                        "severity": "high",
                        "confidence": "MEDIUM",
                        "evidence": "No reconstructed visit event matched this planned stop.",
                        "suggested_action": "Review GPS coverage, plan accuracy, or whether the driver skipped the stop.",
                        "event_id": None,
                        "event_lat": None,
                        "event_lon": None,
                        "review_status": "open",
                    }
                )

        for visit in visit_events.itertuples(index=False):
            if (visit.vehicle_id, visit.geofence_id) not in planned_pairs:
                exceptions.append(
                    {
                        "exception_id": f"UNEXPECTED-{visit.event_id}",
                        "vehicle_id": visit.vehicle_id,
                        "geofence_id": visit.geofence_id,
                        "geofence_name": visit.geofence_name,
                        "exception_type": "unexpected_geofence_visit",
                        "severity": "medium",
                        "confidence": "HIGH",
                        "evidence": "Visit was reconstructed but this geofence was not in planned_stops.",
                        "suggested_action": "Check route deviation, ad-hoc stop, wrong plan, or missing planned stop record.",
                        "event_id": visit.event_id,
                        "event_lat": visit.event_lat,
                        "event_lon": visit.event_lon,
                        "review_status": "open",
                    }
                )

    return pd.DataFrame(exceptions, columns=columns)


def run_georeplay(
    gps_df: pd.DataFrame,
    geofence_df: pd.DataFrame,
    planned_stops_df: pd.DataFrame | None = None,
    long_dwell_minutes: float = 45,
) -> GeoReplayResult:
    gps_points = prepare_gps_points(gps_df)
    geofences = prepare_geofences(geofence_df)
    planned_stops = prepare_planned_stops(planned_stops_df)
    inside_points = detect_inside_points(gps_points, geofences)
    visit_events = reconstruct_visit_events(inside_points)
    exceptions = detect_exceptions(visit_events, planned_stops, long_dwell_minutes)
    return GeoReplayResult(
        visit_events=visit_events,
        exceptions=exceptions,
        gps_points=gps_points,
        geofences=geofences,
        inside_points=inside_points,
    )


def reverse_geocode_locations(
    records: pd.DataFrame,
    lat_column: str,
    lon_column: str,
    output_column: str,
    user_agent: str = "transport-control-tower-georeplay",
    delay_seconds: float = 1,
) -> pd.DataFrame:
    """Reverse-geocode final geofence/event records only, never raw GPS pings."""
    if records.empty or lat_column not in records or lon_column not in records:
        return records

    geolocator = Nominatim(user_agent=user_agent, timeout=10)
    enriched = records.copy()
    cache: dict[tuple[float, float], str | None] = {}

    for row in enriched[[lat_column, lon_column]].dropna().itertuples(index=False):
        key = (round(float(row[0]), 5), round(float(row[1]), 5))
        if key in cache:
            continue
        location = geolocator.reverse(key, exactly_one=True, language="en")
        cache[key] = location.address if location else None
        time.sleep(delay_seconds)

    enriched[output_column] = [
        cache.get((round(float(lat), 5), round(float(lon), 5)))
        if pd.notna(lat) and pd.notna(lon)
        else None
        for lat, lon in zip(enriched[lat_column], enriched[lon_column], strict=False)
    ]
    return enriched


def create_map(
    gps_points: gpd.GeoDataFrame,
    geofences: gpd.GeoDataFrame,
    visit_events: pd.DataFrame,
):
    import folium

    center_lat = float(gps_points["lat"].mean()) if not gps_points.empty else 24.7136
    center_lon = float(gps_points["lon"].mean()) if not gps_points.empty else 46.6753
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

    for geofence in geofences.itertuples(index=False):
        folium.Circle(
            location=[geofence.center_lat, geofence.center_lon],
            radius=float(geofence.radius_m),
            popup=f"{geofence.geofence_id}: {geofence.name}",
            color="#2563eb",
            fill=True,
            fill_opacity=0.12,
        ).add_to(fmap)

    for vehicle_id, group in gps_points.groupby("vehicle_id"):
        ordered = group.sort_values("timestamp")
        coordinates = [[row.lat, row.lon] for row in ordered.itertuples(index=False)]
        folium.PolyLine(coordinates, color="#111827", weight=3, popup=str(vehicle_id)).add_to(fmap)
        for row in ordered.itertuples(index=False):
            folium.CircleMarker(
                location=[row.lat, row.lon],
                radius=3,
                color="#f97316",
                fill=True,
                fill_opacity=0.8,
                popup=f"{row.vehicle_id} | {row.timestamp}",
            ).add_to(fmap)

    for visit in visit_events.itertuples(index=False):
        folium.Marker(
            location=[visit.event_lat, visit.event_lon],
            popup=f"{visit.vehicle_id} at {visit.geofence_name}: {visit.dwell_minutes} min",
            icon=folium.Icon(color="green", icon="ok-sign"),
        ).add_to(fmap)

    return fmap
