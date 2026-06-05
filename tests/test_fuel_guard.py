"""Unit tests for FuelGuard fuel-vs-GPS reconciliation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from fuel_guard.engine import build_fuel_reconciliation_report, run_fuel_guard, write_outputs


def _fuel_events() -> pd.DataFrame:
    """Build mixed fuel event fixtures."""
    return pd.DataFrame(
        [
            {
                "fuel_event_id": "FG-OK",
                "vehicle_id": "VH-1",
                "fuel_time": "2026-06-05T10:20:00+03:00",
                "liters": 280,
                "station_name": "Riyadh Industrial Fuel",
                "station_id": "FS-RUH",
                "lat": 24.7138,
                "lon": 46.6753,
                "odometer": 184200,
                "receipt_no": "R-1001",
                "driver_name": "Ahmed Saleh",
                "carrier_name": "Desert Line Transport",
                "trip_id": "T-1",
            },
            {
                "fuel_event_id": "FG-NO-STOP",
                "vehicle_id": "VH-2",
                "fuel_time": "2026-06-05T11:30:00+03:00",
                "liters": 240,
                "station_name": "Dammam Highway Diesel",
                "station_id": "FS-DMM",
                "lat": 26.3961,
                "lon": 50.1194,
                "odometer": 99120,
                "receipt_no": "R-2002",
                "trip_id": "T-2",
            },
            {
                "fuel_event_id": "FG-NO-GPS",
                "vehicle_id": "VH-3",
                "fuel_time": "2026-06-05T12:15:00+03:00",
                "liters": 220,
                "station_name": "Jeddah South Fuel",
                "station_id": "FS-JED",
                "lat": 21.4859,
                "lon": 39.1925,
                "odometer": 140500,
                "receipt_no": "R-3003",
                "trip_id": "T-3",
            },
            {
                "fuel_event_id": "FG-DUP-1",
                "vehicle_id": "VH-4",
                "fuel_time": "2026-06-05T13:05:00+03:00",
                "liters": 260,
                "station_name": "Riyadh Industrial Fuel",
                "station_id": "FS-RUH",
                "lat": 24.7138,
                "lon": 46.6753,
                "odometer": 77400,
                "receipt_no": "R-4004",
                "trip_id": "T-4",
            },
            {
                "fuel_event_id": "FG-DUP-2",
                "vehicle_id": "VH-4",
                "fuel_time": "2026-06-05T13:12:00+03:00",
                "liters": 260,
                "station_name": "Riyadh Industrial Fuel",
                "station_id": "FS-RUH",
                "lat": 24.7138,
                "lon": 46.6753,
                "odometer": 77380,
                "receipt_no": "R-4004",
                "trip_id": "T-4",
            },
            {
                "fuel_event_id": "FG-HIGH",
                "vehicle_id": "VH-5",
                "fuel_time": "2026-06-05T14:10:00+03:00",
                "liters": 760,
                "station_name": "Dammam Highway Diesel",
                "station_id": "FS-DMM",
                "lat": 26.3961,
                "lon": 50.1194,
                "odometer": 203200,
                "receipt_no": "R-5005",
                "trip_id": "T-5",
            },
            {
                "fuel_event_id": "FG-OUTSIDE",
                "vehicle_id": "VH-6",
                "fuel_time": "2026-06-05T22:20:00+03:00",
                "liters": 300,
                "station_name": "Al Kharj Fuel Stop",
                "station_id": "FS-KHJ",
                "lat": 24.1550,
                "lon": 47.3120,
                "odometer": 55210,
                "receipt_no": "R-6006",
                "trip_id": "T-6",
            },
            {
                "fuel_event_id": "FG-UNKNOWN",
                "vehicle_id": "VH-7",
                "fuel_time": "2026-06-05T15:10:00+03:00",
                "liters": 210,
                "station_name": "Kuwait Remote Fuel",
                "station_id": "FS-KWT-99",
                "lat": 29.3759,
                "lon": 47.9774,
                "odometer": 88400,
                "receipt_no": "R-7007",
                "trip_id": "T-7",
            },
        ]
    )


def _fuel_sites() -> pd.DataFrame:
    """Build known fuel site fixtures."""
    return pd.DataFrame(
        [
            {"station_id": "FS-RUH", "station_name": "Riyadh Industrial Fuel", "lat": 24.7138, "lon": 46.6753, "radius_m": 300},
            {"station_id": "FS-DMM", "station_name": "Dammam Highway Diesel", "lat": 26.3961, "lon": 50.1194, "radius_m": 300},
            {"station_id": "FS-JED", "station_name": "Jeddah South Fuel", "lat": 21.4859, "lon": 39.1925, "radius_m": 300},
            {"station_id": "FS-KHJ", "station_name": "Al Kharj Fuel Stop", "lat": 24.1550, "lon": 47.3120, "radius_m": 300},
        ]
    )


def _gps_points() -> pd.DataFrame:
    """Build GPS evidence fixtures."""
    return pd.DataFrame(
        [
            {"vehicle_id": "VH-1", "timestamp": "2026-06-05T10:18:00+03:00", "lat": 24.7139, "lon": 46.6754, "speed_kph": 0},
            {"vehicle_id": "VH-2", "timestamp": "2026-06-05T11:29:00+03:00", "lat": 26.3962, "lon": 50.1193, "speed_kph": 25},
            {"vehicle_id": "VH-4", "timestamp": "2026-06-05T13:06:00+03:00", "lat": 24.7139, "lon": 46.6753, "speed_kph": 0},
            {"vehicle_id": "VH-4", "timestamp": "2026-06-05T13:13:00+03:00", "lat": 24.7139, "lon": 46.6753, "speed_kph": 0},
            {"vehicle_id": "VH-5", "timestamp": "2026-06-05T14:12:00+03:00", "lat": 26.3960, "lon": 50.1196, "speed_kph": 0},
            {"vehicle_id": "VH-6", "timestamp": "2026-06-05T22:19:00+03:00", "lat": 24.1551, "lon": 47.3121, "speed_kph": 0},
            {"vehicle_id": "VH-7", "timestamp": "2026-06-05T15:08:00+03:00", "lat": 29.3759, "lon": 47.9774, "speed_kph": 0},
        ]
    )


def _visits() -> pd.DataFrame:
    """Build GeoReplay visit evidence fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": "T-1",
                "vehicle_id": "VH-1",
                "geofence_id": "FS-RUH",
                "geofence_name": "Riyadh Industrial Fuel",
                "geofence_type": "FUEL",
                "enter_time": "2026-06-05T10:05:00+03:00",
                "exit_time": "2026-06-05T10:35:00+03:00",
                "dwell_minutes": 30,
            },
            {
                "trip_id": "T-2",
                "vehicle_id": "VH-2",
                "geofence_id": "FS-DMM",
                "geofence_name": "Dammam Highway Diesel",
                "geofence_type": "FUEL",
                "enter_time": "2026-06-05T11:26:00+03:00",
                "exit_time": "2026-06-05T11:31:00+03:00",
                "dwell_minutes": 5,
            },
            {
                "trip_id": "T-4",
                "vehicle_id": "VH-4",
                "geofence_id": "FS-RUH",
                "geofence_name": "Riyadh Industrial Fuel",
                "geofence_type": "FUEL",
                "enter_time": "2026-06-05T12:55:00+03:00",
                "exit_time": "2026-06-05T13:25:00+03:00",
                "dwell_minutes": 30,
            },
            {
                "trip_id": "T-5",
                "vehicle_id": "VH-5",
                "geofence_id": "FS-DMM",
                "geofence_name": "Dammam Highway Diesel",
                "geofence_type": "FUEL",
                "enter_time": "2026-06-05T14:00:00+03:00",
                "exit_time": "2026-06-05T14:25:00+03:00",
                "dwell_minutes": 25,
            },
            {
                "trip_id": "T-6",
                "vehicle_id": "VH-6",
                "geofence_id": "FS-KHJ",
                "geofence_name": "Al Kharj Fuel Stop",
                "geofence_type": "FUEL",
                "enter_time": "2026-06-05T22:05:00+03:00",
                "exit_time": "2026-06-05T22:35:00+03:00",
                "dwell_minutes": 30,
            },
        ]
    )


def _trips() -> pd.DataFrame:
    """Build trip-window fixtures."""
    return pd.DataFrame(
        [
            {"trip_id": "T-1", "vehicle_id": "VH-1", "planned_departure": "2026-06-05T07:00:00+03:00", "promised_arrival": "2026-06-05T18:00:00+03:00"},
            {"trip_id": "T-2", "vehicle_id": "VH-2", "planned_departure": "2026-06-05T08:00:00+03:00", "promised_arrival": "2026-06-05T16:00:00+03:00"},
            {"trip_id": "T-3", "vehicle_id": "VH-3", "planned_departure": "2026-06-05T09:00:00+03:00", "promised_arrival": "2026-06-05T17:00:00+03:00"},
            {"trip_id": "T-4", "vehicle_id": "VH-4", "planned_departure": "2026-06-05T07:30:00+03:00", "promised_arrival": "2026-06-05T18:30:00+03:00"},
            {"trip_id": "T-5", "vehicle_id": "VH-5", "planned_departure": "2026-06-05T10:00:00+03:00", "promised_arrival": "2026-06-05T19:00:00+03:00"},
            {"trip_id": "T-6", "vehicle_id": "VH-6", "planned_departure": "2026-06-05T08:00:00+03:00", "promised_arrival": "2026-06-05T18:00:00+03:00"},
            {"trip_id": "T-7", "vehicle_id": "VH-7", "planned_departure": "2026-06-05T10:00:00+03:00", "promised_arrival": "2026-06-05T20:00:00+03:00"},
        ]
    )


def _report() -> pd.DataFrame:
    return build_fuel_reconciliation_report(
        _fuel_events(),
        _visits(),
        _gps_points(),
        _fuel_sites(),
        _trips(),
    )


def _row(report: pd.DataFrame, fuel_event_id: str) -> pd.Series:
    return report[report["fuel_event_id"] == fuel_event_id].iloc[0]


def test_fuel_event_with_gps_and_stop_evidence_is_matched() -> None:
    """A fuel event with nearby GPS and enough dwell should be matched."""
    row = _row(_report(), "FG-OK")

    assert row["risk_bucket"] == "OK"
    assert row["exception_flags"] == "OK"
    assert row["stop_evidence"] == "TRUE"


def test_gps_evidence_match_is_captured() -> None:
    """FuelGuard should preserve nearest GPS evidence distance."""
    row = _row(_report(), "FG-OK")

    assert row["distance_to_station_m"] < 30
    assert str(row["matched_event_time"]) == "2026-06-05 07:20:00+00:00"


def test_gps_point_match_without_visit_evidence() -> None:
    """GPS points should support a fuel event when visit evidence is unavailable."""
    row = _row(
        build_fuel_reconciliation_report(
            _fuel_events().head(1),
            pd.DataFrame(),
            _gps_points(),
            _fuel_sites(),
            _trips(),
        ),
        "FG-OK",
    )

    assert row["matched_evidence_type"] == "GPS"
    assert str(row["matched_event_time"]) == "2026-06-05 07:18:00+00:00"
    assert row["risk_bucket"] == "OK"


def test_visit_evidence_match_is_captured() -> None:
    """FuelGuard should preserve matching GeoReplay stop evidence."""
    row = _row(_report(), "FG-OK")

    assert row["matched_evidence_type"] == "VISIT"
    assert row["matched_geofence_name"] == "Riyadh Industrial Fuel"


def test_fuel_site_name_can_supply_missing_coordinates() -> None:
    """Known fuel sites should supply coordinates when a transaction lacks lat/lon."""
    fuel_events = _fuel_events().copy()
    fuel_events.loc[fuel_events["fuel_event_id"] == "FG-OK", ["station_id", "lat", "lon"]] = pd.NA
    row = _row(
        build_fuel_reconciliation_report(
            fuel_events,
            _visits(),
            _gps_points(),
            _fuel_sites(),
            _trips(),
        ),
        "FG-OK",
    )

    assert row["distance_to_station_m"] < 30
    assert row["matched_gps_lat"] == 24.7139


def test_no_supporting_gps_evidence_detection() -> None:
    """Fuel events without nearby GPS or visit evidence should need review."""
    row = _row(_report(), "FG-NO-GPS")

    assert row["risk_bucket"] == "DATA MISSING"
    assert "NO GPS EVIDENCE" in row["exception_flags"]
    assert row["matched_evidence_type"] == "FUEL EVENT LOCATION"


def test_no_stop_evidence_detection() -> None:
    """Nearby GPS without enough dwell should keep a no-stop-evidence flag."""
    row = _row(_report(), "FG-NO-STOP")

    assert row["risk_bucket"] == "REVIEW"
    assert "NO STOP NEAR FUEL" in row["exception_flags"]
    assert row["stop_evidence"] == "FALSE"


def test_duplicate_receipt_detection() -> None:
    """Duplicate receipt numbers for the same vehicle should be flagged."""
    report = _report()

    assert "DUPLICATE RECEIPT" in _row(report, "FG-DUP-1")["exception_flags"]
    assert "DUPLICATE RECEIPT" in _row(report, "FG-DUP-2")["exception_flags"]


def test_odometer_anomaly_detection() -> None:
    """Odometer values should not move backward for the same vehicle."""
    row = _row(_report(), "FG-DUP-2")

    assert "ODOMETER DROP" in row["exception_flags"]


def test_high_liter_outlier_detection() -> None:
    """Very large fills should be flagged for review."""
    row = _row(_report(), "FG-HIGH")

    assert "HIGH LITERS" in row["exception_flags"]


def test_outside_trip_window_detection() -> None:
    """Fuel events after the assigned trip window should be flagged."""
    row = _row(_report(), "FG-OUTSIDE")

    assert row["in_trip_window"] == "FALSE"
    assert "OUTSIDE TRIP WINDOW" in row["exception_flags"]


def test_unknown_station_detection() -> None:
    """Unknown station rows should be flagged when a fuel-site master is provided."""
    row = _row(_report(), "FG-UNKNOWN")

    assert "UNKNOWN STATION" in row["exception_flags"]
    assert row["severity"] == "MEDIUM"


def test_export_smoke(tmp_path: Path) -> None:
    """FuelGuard should write both CSV exports."""
    result = run_fuel_guard(_fuel_events(), _visits(), _gps_points(), _fuel_sites(), _trips())
    report_path, exceptions_path = write_outputs(result, tmp_path)

    assert report_path.exists()
    assert exceptions_path.exists()
    assert "fuel_event_id" in report_path.read_text()
    assert "suggested_action" in exceptions_path.read_text()


def test_demo_data_smoke() -> None:
    """Bundled demo data should run end to end."""
    base = Path("fuel_guard/demo_data")
    result = run_fuel_guard(
        pd.read_csv(base / "fuel_events.csv"),
        pd.read_csv(base / "visit_events.csv"),
        pd.read_csv(base / "gps_points.csv"),
        pd.read_csv(base / "fuel_sites.csv"),
        pd.read_csv(base / "trips.csv"),
    )

    assert len(result.fuel_reconciliation_report) == 8
    assert len(result.fuel_exceptions) == 7
