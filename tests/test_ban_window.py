"""Unit tests for BanWindow restriction-window checks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ban_window.engine import (
    BAN_CONFLICT_COLUMNS,
    BAN_RISK_COLUMNS,
    RISK_BUCKETS,
    expand_ban_windows_for_trips,
    interval_overlap_minutes,
    prepare_ban_windows,
    prepare_trips,
    run_ban_window,
    write_outputs,
)
from ban_window.models import BanWindowSettings


def _trip(
    trip_id: str,
    vehicle_id: str,
    origin: str,
    destination: str,
    planned_departure: str,
    promised_arrival: str,
    city: str,
    vehicle_class: str,
) -> tuple[str, str, str, str, str, str, str, str, str, str, str, str]:
    return (
        trip_id,
        vehicle_id,
        origin,
        destination,
        planned_departure,
        promised_arrival,
        "GCC Demo Customer",
        "Gulf Bridge",
        city,
        vehicle_class,
        "",
        "",
    )


def _trips() -> pd.DataFrame:
    rows = [
        _trip(
            "TRIP-CLEAR",
            "VH-101",
            "Dammam DC",
            "Al Khobar Store",
            "2026-06-01T05:00:00Z",
            "2026-06-01T06:00:00Z",
            "Dammam",
            "HEAVY",
        ),
        _trip(
            "TRIP-CONFLICT",
            "VH-102",
            "Riyadh DC",
            "Riyadh Mall",
            "2026-06-01T07:30:00Z",
            "2026-06-01T09:30:00Z",
            "Riyadh",
            "HEAVY",
        ),
        _trip(
            "TRIP-WATCH",
            "VH-103",
            "Jeddah Port",
            "Jeddah Mall",
            "2026-06-01T09:30:00Z",
            "2026-06-01T10:35:00Z",
            "Jeddah",
            "LIGHT",
        ),
        _trip(
            "TRIP-MISSING-CITY",
            "VH-104",
            "Depot A",
            "Store B",
            "2026-06-01T06:00:00Z",
            "2026-06-01T08:00:00Z",
            "",
            "HEAVY",
        ),
        _trip(
            "TRIP-MISSING-TIME",
            "VH-105",
            "Dammam Port",
            "Khobar Store",
            "",
            "",
            "Dammam",
            "HEAVY",
        ),
        _trip(
            "TRIP-UNKNOWN-CLASS",
            "VH-106",
            "Doha Hub",
            "Doha Retail",
            "2026-06-01T07:30:00Z",
            "2026-06-01T08:30:00Z",
            "Doha",
            "",
        ),
        _trip(
            "TRIP-OVERNIGHT",
            "VH-107",
            "Muscat Port",
            "Muscat DC",
            "2026-06-01T23:30:00Z",
            "2026-06-02T02:00:00Z",
            "Muscat",
            "HEAVY",
        ),
        _trip(
            "TRIP-INACTIVE",
            "VH-108",
            "Kuwait DC",
            "Kuwait Mall",
            "2026-06-01T08:00:00Z",
            "2026-06-01T09:00:00Z",
            "Kuwait City",
            "HEAVY",
        ),
        _trip(
            "TRIP-ETA",
            "VH-109",
            "Abu Dhabi Port",
            "Abu Dhabi DC",
            "2026-06-01T06:00:00Z",
            "2026-06-01T08:00:00Z",
            "Abu Dhabi",
            "HEAVY",
        ),
        _trip(
            "TRIP-GENERIC",
            "VH-110",
            "Dubai JAFZA",
            "Dubai Store",
            "2026-06-01T11:15:00Z",
            "2026-06-01T11:45:00Z",
            "Dubai",
            "MEDIUM",
        ),
        _trip(
            "TRIP-INFERRED-CITY",
            "VH-111",
            "Bahrain Hub",
            "Riyadh North Store",
            "2026-06-01T07:30:00Z",
            "2026-06-01T08:30:00Z",
            "",
            "HEAVY",
        ),
        _trip(
            "TRIP-STRONGEST",
            "VH-112",
            "Riyadh DC",
            "Riyadh Mall",
            "2026-06-01T07:30:00Z",
            "2026-06-01T10:30:00Z",
            "Riyadh",
            "HEAVY",
        ),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "trip_id",
            "vehicle_id",
            "origin",
            "destination",
            "planned_departure",
            "promised_arrival",
            "customer_name",
            "carrier_name",
            "city",
            "vehicle_class",
            "planned_city_entry",
            "planned_city_exit",
        ],
    )


def _ban_windows() -> pd.DataFrame:
    rows = [
        ("BW-RUH-HEAVY", "Riyadh", "Riyadh Central", "HEAVY", "07:00", "09:00", "Mon", "2026-06-01", "2026-06-10", "Synthetic restriction"),
        ("BW-JED-ALL", "Jeddah", "Jeddah Mall Zone", "", "11:00", "12:00", "Mon", "2026-06-01", "2026-06-10", "Synthetic receiving window"),
        ("BW-DOH-HEAVY", "Doha", "Doha Corniche", "HEAVY", "07:00", "09:00", "Mon", "2026-06-01", "2026-06-10", "Synthetic class rule"),
        ("BW-MCT-NIGHT", "Muscat", "Muscat Port Gate", "HEAVY", "23:00", "05:00", "Mon", "2026-06-01", "2026-06-10", "Synthetic overnight window"),
        ("BW-KWI-INACTIVE", "Kuwait City", "Kuwait Mall Dock", "HEAVY", "08:00", "10:00", "Mon", "2026-05-01", "2026-05-15", "Inactive synthetic window"),
        ("BW-AUH-HEAVY", "Abu Dhabi", "Abu Dhabi Industrial Gate", "HEAVY", "08:30", "09:30", "Mon", "2026-06-01", "2026-06-10", "Synthetic ETA window"),
        ("BW-DXB-ALL", "Dubai", "Dubai Mall Dock", "", "11:00", "12:00", "Mon", "2026-06-01", "2026-06-10", "Synthetic generic rule"),
        ("BW-RUH-LONG", "Riyadh", "Riyadh Long Window", "HEAVY", "07:00", "10:00", "Mon", "2026-06-01", "2026-06-10", "Synthetic long restriction"),
        ("BW-TUE", "Dammam", "Dammam Tuesday", "HEAVY", "05:00", "07:00", "Tue", "2026-06-01", "2026-06-10", "Nonmatching weekday"),
    ]
    return pd.DataFrame(
        rows,
        columns=[
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
        ],
    )


def _eta() -> pd.DataFrame:
    return pd.DataFrame(
        [("TRIP-ETA", "2026-06-01T09:00:00Z", "AT RISK", "2026-06-01T06:00:00Z")],
        columns=["trip_id", "predicted_arrival", "risk_status", "latest_event_time"],
    )


def _result():
    return run_ban_window(_trips(), _ban_windows(), _eta())


def _risk(trip_id: str) -> pd.Series:
    return _result().ban_risk_board.set_index("trip_id").loc[trip_id]


def test_interval_overlap_detection() -> None:
    assert interval_overlap_minutes(
        pd.Timestamp("2026-06-01T07:00:00Z"),
        pd.Timestamp("2026-06-01T08:00:00Z"),
        pd.Timestamp("2026-06-01T07:30:00Z"),
        pd.Timestamp("2026-06-01T08:30:00Z"),
    ) == 30


def test_no_overlap_clear_classification() -> None:
    row = _risk("TRIP-CLEAR")
    assert row["risk_bucket"] == "CLEAR"
    assert row["severity"] == "OK"


def test_watch_buffer_classification() -> None:
    row = _risk("TRIP-WATCH")
    assert row["risk_bucket"] == "WATCH"
    assert row["severity"] == "MEDIUM"


def test_overnight_window_expansion_logic() -> None:
    trips = prepare_trips(_trips())
    windows = expand_ban_windows_for_trips(prepare_ban_windows(_ban_windows()), trips)
    row = windows[(windows["trip_id"] == "TRIP-OVERNIGHT") & (windows["ban_id"] == "BW-MCT-NIGHT")].iloc[0]
    assert str(row["ban_start"]) == "2026-06-01 23:00:00+00:00"
    assert str(row["ban_end"]) == "2026-06-02 05:00:00+00:00"
    assert _risk("TRIP-OVERNIGHT")["risk_bucket"] == "BAN CONFLICT"


def test_days_of_week_filtering() -> None:
    trips = prepare_trips(_trips())
    windows = expand_ban_windows_for_trips(prepare_ban_windows(_ban_windows()), trips)
    assert windows[windows["ban_id"] == "BW-TUE"].empty


def test_effective_from_effective_to_filtering() -> None:
    row = _risk("TRIP-INACTIVE")
    assert row["risk_bucket"] == "CLEAR"
    assert pd.isna(row["matched_ban_id"])


def test_vehicle_class_exact_match() -> None:
    row = _risk("TRIP-CONFLICT")
    assert row["risk_bucket"] == "BAN CONFLICT"
    assert row["ban_vehicle_class"] == "HEAVY"
    assert row["confidence_bucket"] == "HIGH"


def test_generic_vehicle_class_rule() -> None:
    row = _risk("TRIP-GENERIC")
    assert row["risk_bucket"] == "BAN CONFLICT"
    assert pd.isna(row["ban_vehicle_class"])
    assert row["confidence_bucket"] == "MEDIUM"


def test_vehicle_class_unknown_classification() -> None:
    row = _risk("TRIP-UNKNOWN-CLASS")
    assert row["risk_bucket"] == "VEHICLE CLASS UNKNOWN"
    assert row["severity"] == "MEDIUM"


def test_missing_city_classification() -> None:
    row = _risk("TRIP-MISSING-CITY")
    assert row["risk_bucket"] == "MISSING CITY"
    assert row["confidence_bucket"] == "DATA MISSING"


def test_missing_timing_classification() -> None:
    row = _risk("TRIP-MISSING-TIME")
    assert row["risk_bucket"] == "MISSING TIMING"
    assert row["severity"] == "LOW"


def test_eta_predicted_arrival_conflict() -> None:
    row = _risk("TRIP-ETA")
    assert row["risk_bucket"] == "BAN CONFLICT"
    assert str(row["predicted_arrival"]) == "2026-06-01 09:00:00+00:00"
    assert row["confidence_bucket"] == "LOW"


def test_multiple_ban_windows_with_strongest_risk_selected() -> None:
    row = _risk("TRIP-STRONGEST")
    assert row["risk_bucket"] == "BAN CONFLICT"
    assert row["matched_ban_id"] == "BW-RUH-LONG"
    assert row["severity"] == "CRITICAL"


def test_output_schema_contract() -> None:
    result = _result()
    assert list(result.ban_risk_board.columns) == BAN_RISK_COLUMNS
    assert list(result.ban_conflicts.columns) == BAN_CONFLICT_COLUMNS
    assert set(result.ban_risk_board["risk_bucket"]).issubset(RISK_BUCKETS)


def test_export_smoke(tmp_path: Path) -> None:
    risk_path, conflict_path = write_outputs(_result(), tmp_path)
    assert risk_path.exists()
    assert conflict_path.exists()
    assert list(pd.read_csv(risk_path).columns) == BAN_RISK_COLUMNS
    assert list(pd.read_csv(conflict_path).columns) == BAN_CONFLICT_COLUMNS


def test_demo_data_smoke() -> None:
    base = Path("ban_window/demo_data")
    result = run_ban_window(
        pd.read_csv(base / "trips.csv"),
        pd.read_csv(base / "ban_windows.csv"),
        pd.read_csv(base / "eta_risk_board.csv"),
        pd.read_csv(base / "visit_events.csv"),
        settings=BanWindowSettings(),
    )
    assert list(result.ban_risk_board.columns) == BAN_RISK_COLUMNS
    assert list(result.ban_conflicts.columns) == BAN_CONFLICT_COLUMNS
    assert RISK_BUCKETS.issubset(set(result.ban_risk_board["risk_bucket"]))
    assert len(result.ban_risk_board) >= 10
