"""Unit tests for BanWindow restriction-window checks."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ban_window.engine import (
    BAN_CONFLICT_COLUMNS,
    BAN_RISK_COLUMNS,
    RISK_STATUSES,
    expand_ban_windows,
    prepare_ban_windows,
    prepare_trips,
    run_ban_window,
    write_outputs,
)
from ban_window.models import BanWindowSettings


def _trips() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (
                "TRIP-CLEAR",
                "VH-101",
                "Riyadh DC",
                "Dammam Store",
                "2026-05-04T02:00:00+03:00",
                "2026-05-04T06:00:00+03:00",
                "Gulf Fresh Foods",
                "Gulf Bridge",
                "Riyadh",
                "HEAVY",
                "",
                "",
            ),
            (
                "TRIP-CONFLICT",
                "VH-102",
                "Riyadh DC",
                "Riyadh Mall",
                "2026-05-04T07:30:00+03:00",
                "2026-05-04T09:30:00+03:00",
                "Najd Retail",
                "Desert Falcon",
                "Riyadh",
                "HEAVY",
                "",
                "",
            ),
            (
                "TRIP-WATCH",
                "VH-103",
                "Jeddah Port",
                "Jeddah Mall",
                "2026-05-04T09:30:00+03:00",
                "2026-05-04T10:15:00+03:00",
                "Red Sea Pharma",
                "Hejaz Line",
                "Jeddah",
                "LIGHT",
                "",
                "",
            ),
            (
                "TRIP-MISSING-TIME",
                "VH-104",
                "Dammam Port",
                "Khobar Store",
                "",
                "",
                "Eastern Foods",
                "Gulf Bridge",
                "Dammam",
                "HEAVY",
                "",
                "",
            ),
            (
                "TRIP-MISSING-CITY",
                "VH-105",
                "Dubai JAFZA",
                "Dubai Store",
                "2026-05-04T06:00:00+04:00",
                "2026-05-04T08:00:00+04:00",
                "Emirates Home",
                "Desert Falcon",
                "",
                "HEAVY",
                "",
                "",
            ),
            (
                "TRIP-UNKNOWN-CLASS",
                "VH-106",
                "Doha Hub",
                "Doha Retail",
                "2026-05-04T07:30:00+03:00",
                "2026-05-04T08:30:00+03:00",
                "GCC Electronics",
                "Peninsula Freight",
                "Doha",
                "",
                "",
                "",
            ),
            (
                "TRIP-ETA",
                "VH-107",
                "Muscat Port",
                "Muscat DC",
                "2026-05-04T04:00:00+04:00",
                "2026-05-04T08:00:00+04:00",
                "Oman Retail",
                "Gulf Bridge",
                "Muscat",
                "HEAVY",
                "",
                "",
            ),
            (
                "TRIP-CITY-WINDOW",
                "VH-108",
                "Kuwait DC",
                "Kuwait Mall",
                "2026-05-04T05:00:00+03:00",
                "2026-05-04T11:00:00+03:00",
                "Kuwait Retail",
                "North Gulf",
                "Kuwait City",
                "HEAVY",
                "2026-05-04T08:00:00+03:00",
                "2026-05-04T09:00:00+03:00",
            ),
            (
                "TRIP-VISIT",
                "VH-109",
                "Abu Dhabi Port",
                "Abu Dhabi DC",
                "",
                "2026-05-04T11:00:00+04:00",
                "Emirates Home",
                "Desert Falcon",
                "Abu Dhabi",
                "HEAVY",
                "",
                "",
            ),
        ],
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
    return pd.DataFrame(
        [
            (
                "BW-RUH-HEAVY",
                "Riyadh",
                "Riyadh Central",
                "HEAVY",
                "04:00",
                "08:00",
                "Mon",
                "2026-05-01",
                "2026-05-10",
                "Synthetic planning restriction",
            ),
            (
                "BW-JED-ALL",
                "Jeddah",
                "Jeddah Mall Zone",
                "",
                "08:00",
                "09:00",
                "Mon",
                "2026-05-01",
                "2026-05-10",
                "Synthetic receiving window",
            ),
            (
                "BW-DOH-HEAVY",
                "Doha",
                "Doha Corniche",
                "HEAVY",
                "07:00",
                "09:00",
                "Mon",
                "2026-05-01",
                "2026-05-10",
                "Synthetic city restriction",
            ),
            (
                "BW-MCT-HEAVY",
                "Muscat",
                "Muscat Port Gate",
                "HEAVY",
                "2026-05-04T08:30:00+04:00",
                "2026-05-04T09:30:00+04:00",
                "",
                "",
                "",
                "Synthetic dated window",
            ),
            (
                "BW-KWI-HEAVY",
                "Kuwait City",
                "Kuwait Mall Dock",
                "HEAVY",
                "05:30",
                "06:30",
                "Mon",
                "2026-05-01",
                "2026-05-10",
                "Synthetic mall receiving window",
            ),
            (
                "BW-AUH-HEAVY",
                "Abu Dhabi",
                "Abu Dhabi Industrial Gate",
                "HEAVY",
                "03:30",
                "04:30",
                "Mon",
                "2026-05-01",
                "2026-05-10",
                "Synthetic restricted movement",
            ),
        ],
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
        [("TRIP-ETA", "2026-05-04T09:00:00+04:00", "AT RISK", "2026-05-04T06:00:00+04:00")],
        columns=["trip_id", "predicted_arrival", "risk_status", "latest_event_time"],
    )


def _visits() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (
                "TRIP-VISIT",
                "VH-109",
                "Abu Dhabi Port",
                "ORIGIN",
                "2026-05-04T07:45:00+04:00",
                "2026-05-04T08:00:00+04:00",
                15,
            )
        ],
        columns=[
            "trip_id",
            "vehicle_id",
            "geofence_name",
            "geofence_type",
            "enter_time",
            "exit_time",
            "dwell_minutes",
        ],
    )


def _result():
    return run_ban_window(_trips(), _ban_windows(), _eta(), _visits())


def _risk(trip_id: str) -> pd.Series:
    return _result().ban_risk_board.set_index("trip_id").loc[trip_id]


def test_time_only_window_expansion_by_day() -> None:
    trips = prepare_trips(_trips())
    windows = expand_ban_windows(prepare_ban_windows(_ban_windows()), trips)
    riyadh = windows[windows["ban_id"] == "BW-RUH-HEAVY"].iloc[0]
    assert str(riyadh["ban_start"]) == "2026-05-04 04:00:00+00:00"
    assert str(riyadh["ban_end"]) == "2026-05-04 08:00:00+00:00"


def test_direct_ban_overlap() -> None:
    row = _risk("TRIP-CONFLICT")
    assert row["risk_status"] == "CONFLICT"
    assert row["conflict_count"] == 1


def test_clear_trip() -> None:
    assert _risk("TRIP-CLEAR")["risk_status"] == "CLEAR"


def test_watch_case_with_buffer() -> None:
    row = _risk("TRIP-WATCH")
    assert row["risk_status"] == "WATCH"
    assert row["watch_count"] == 1


def test_missing_timing_flag() -> None:
    assert _risk("TRIP-MISSING-TIME")["risk_status"] == "MISSING TIMING"


def test_missing_city_flag() -> None:
    assert _risk("TRIP-MISSING-CITY")["risk_status"] == "MISSING CITY"


def test_vehicle_class_uncertainty() -> None:
    row = _risk("TRIP-UNKNOWN-CLASS")
    assert row["risk_status"] == "VEHICLE CLASS UNKNOWN"
    assert row["matched_window_count"] == 1


def test_eta_predicted_interval_can_create_conflict() -> None:
    row = _risk("TRIP-ETA")
    assert row["timing_source"] == "eta_risk_board"
    assert row["risk_status"] == "CONFLICT"


def test_planned_city_window_preferred() -> None:
    row = _risk("TRIP-CITY-WINDOW")
    assert row["timing_source"] == "planned_city_window"
    assert row["risk_status"] == "CONFLICT"


def test_visit_events_fallback_interval() -> None:
    row = _risk("TRIP-VISIT")
    assert row["timing_source"] == "visit_events_to_promised_arrival"
    assert row["risk_status"] == "CONFLICT"


def test_output_schema_contract() -> None:
    result = _result()
    assert list(result.ban_risk_board.columns) == BAN_RISK_COLUMNS
    assert list(result.ban_conflicts.columns) == BAN_CONFLICT_COLUMNS
    assert set(result.ban_risk_board["risk_status"]).issubset(RISK_STATUSES)


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
    assert RISK_STATUSES.issubset(set(result.ban_risk_board["risk_status"]))
    assert result.kpis["conflict_rows"] >= 4
