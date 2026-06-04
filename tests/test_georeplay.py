from __future__ import annotations

import pandas as pd

from georeplay.engine import run_georeplay


def _gps() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "vehicle_id": "VH-1",
                "timestamp": "2026-06-01 08:00:00",
                "lat": 24.7100,
                "lon": 46.6700,
                "speed_kph": 30,
            },
            {
                "vehicle_id": "VH-1",
                "timestamp": "2026-06-01 08:05:00",
                "lat": 24.7136,
                "lon": 46.6753,
                "speed_kph": 0,
            },
            {
                "vehicle_id": "VH-1",
                "timestamp": "2026-06-01 08:20:00",
                "lat": 24.7137,
                "lon": 46.6754,
                "speed_kph": 0,
            },
            {
                "vehicle_id": "VH-1",
                "timestamp": "2026-06-01 09:10:00",
                "lat": 24.7138,
                "lon": 46.6755,
                "speed_kph": 0,
            },
            {
                "vehicle_id": "VH-1",
                "timestamp": "2026-06-01 09:30:00",
                "lat": 24.7200,
                "lon": 46.6900,
                "speed_kph": 35,
            },
        ]
    )


def _geofences() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "geofence_id": "RUH_DC",
                "name": "Riyadh DC",
                "lat": 24.7136,
                "lon": 46.6753,
                "radius_m": 300,
                "geofence_type": "depot",
            },
            {
                "geofence_id": "JED_DC",
                "name": "Jeddah DC",
                "lat": 21.5161,
                "lon": 39.1729,
                "radius_m": 300,
                "geofence_type": "depot",
            },
        ]
    )


def test_geofence_entry_exit_and_dwell_are_reconstructed() -> None:
    result = run_georeplay(_gps(), _geofences(), long_dwell_minutes=45)

    assert len(result.visit_events) == 1
    visit = result.visit_events.iloc[0]
    assert visit["geofence_id"] == "RUH_DC"
    assert str(visit["entry_time"]) == "2026-06-01 08:05:00"
    assert str(visit["exit_time"]) == "2026-06-01 09:10:00"
    assert visit["dwell_minutes"] == 65


def test_long_dwell_exception_is_detected() -> None:
    result = run_georeplay(_gps(), _geofences(), long_dwell_minutes=45)

    exception_types = set(result.exceptions["exception_type"])
    assert "long_dwell" in exception_types


def test_missed_planned_stop_is_detected() -> None:
    planned = pd.DataFrame(
        [
            {"vehicle_id": "VH-1", "geofence_id": "RUH_DC", "planned_arrival": "2026-06-01 08:05:00"},
            {"vehicle_id": "VH-1", "geofence_id": "JED_DC", "planned_arrival": "2026-06-01 18:00:00"},
        ]
    )
    result = run_georeplay(_gps(), _geofences(), planned, long_dwell_minutes=45)

    missed = result.exceptions[result.exceptions["exception_type"] == "missed_planned_stop"]
    assert len(missed) == 1
    assert missed.iloc[0]["geofence_id"] == "JED_DC"


def test_unexpected_geofence_visit_is_detected() -> None:
    planned = pd.DataFrame(
        [{"vehicle_id": "VH-1", "geofence_id": "JED_DC", "planned_arrival": "2026-06-01 18:00:00"}]
    )
    result = run_georeplay(_gps(), _geofences(), planned, long_dwell_minutes=45)

    exception_types = set(result.exceptions["exception_type"])
    assert "unexpected_geofence_visit" in exception_types
