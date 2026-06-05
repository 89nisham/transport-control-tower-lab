"""Unit tests for UpdatePulse update-discipline review."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from update_pulse.engine import build_update_discipline_report, run_update_pulse, write_outputs


def _trips() -> pd.DataFrame:
    """Build mixed planned trip fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": "UP-OK",
                "vehicle_id": "VH-1",
                "driver_name": "Omar Hassan",
                "carrier_name": "Desert Line Transport",
                "customer_name": "Acme Foods",
                "origin": "Riyadh Hub",
                "destination": "Jeddah DC",
                "planned_departure": "2026-06-05T07:00:00+03:00",
                "promised_arrival": "2026-06-05T17:00:00+03:00",
            },
            {
                "trip_id": "UP-LATE",
                "vehicle_id": "VH-2",
                "origin": "Dammam Port",
                "destination": "Riyadh Store",
                "planned_departure": "2026-06-05T08:00:00+03:00",
                "promised_arrival": "2026-06-05T15:00:00+03:00",
            },
            {
                "trip_id": "UP-MISSING",
                "vehicle_id": "VH-3",
                "origin": "Jeddah Port",
                "destination": "Makkah DC",
                "planned_departure": "2026-06-05T06:30:00+03:00",
                "promised_arrival": "2026-06-05T11:30:00+03:00",
            },
            {
                "trip_id": "UP-SEQ",
                "vehicle_id": "VH-4",
                "origin": "Riyadh Pharma Hub",
                "destination": "Dammam Hospital",
                "planned_departure": "2026-06-05T09:00:00+03:00",
                "promised_arrival": "2026-06-05T15:00:00+03:00",
            },
            {
                "trip_id": "UP-DUP",
                "vehicle_id": "VH-5",
                "origin": "Jeddah Crossdock",
                "destination": "Medina Store",
                "planned_departure": "2026-06-05T10:00:00+03:00",
                "promised_arrival": "2026-06-05T15:30:00+03:00",
            },
        ]
    )


def _updates() -> pd.DataFrame:
    """Build TMS and driver update fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": "UP-OK",
                "vehicle_id": "VH-1",
                "update_time": "2026-06-05T07:05:00+03:00",
                "status": "departed",
            },
            {
                "trip_id": "UP-OK",
                "vehicle_id": "VH-1",
                "update_time": "2026-06-05T16:58:00+03:00",
                "status": "arrived",
            },
            {
                "trip_id": "UP-LATE",
                "vehicle_id": "VH-2",
                "update_time": "2026-06-05T09:10:00+03:00",
                "status": "departed",
            },
            {
                "trip_id": "UP-LATE",
                "vehicle_id": "VH-2",
                "update_time": "2026-06-05T16:00:00+03:00",
                "status": "delivered",
            },
            {
                "trip_id": "UP-MISSING",
                "vehicle_id": "VH-3",
                "update_time": "2026-06-05T06:35:00+03:00",
                "status": "departed",
            },
            {
                "trip_id": "UP-SEQ",
                "vehicle_id": "VH-4",
                "update_time": "2026-06-05T09:05:00+03:00",
                "status": "arrived",
            },
            {
                "trip_id": "UP-SEQ",
                "vehicle_id": "VH-4",
                "update_time": "2026-06-05T09:25:00+03:00",
                "status": "departed",
            },
            {
                "trip_id": "UP-DUP",
                "vehicle_id": "VH-5",
                "update_time": "2026-06-05T10:01:00+03:00",
                "status": "departed",
            },
            {
                "trip_id": "UP-DUP",
                "vehicle_id": "VH-5",
                "update_time": "2026-06-05T10:03:00+03:00",
                "status": "departed",
            },
            {
                "trip_id": "UP-DUP",
                "vehicle_id": "VH-5",
                "update_time": "2026-06-05T13:45:00+03:00",
                "status": "arrived",
            },
        ]
    )


def _visits() -> pd.DataFrame:
    """Build optional GeoReplay event evidence fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": "UP-OK",
                "vehicle_id": "VH-1",
                "geofence_name": "Riyadh Hub",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T06:20:00+03:00",
                "exit_time": "2026-06-05T07:02:00+03:00",
            },
            {
                "trip_id": "UP-OK",
                "vehicle_id": "VH-1",
                "geofence_name": "Jeddah DC",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T16:57:00+03:00",
                "exit_time": "2026-06-05T18:00:00+03:00",
            },
            {
                "trip_id": "UP-LATE",
                "vehicle_id": "VH-2",
                "geofence_name": "Dammam Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T07:00:00+03:00",
                "exit_time": "2026-06-05T09:05:00+03:00",
            },
            {
                "trip_id": "UP-LATE",
                "vehicle_id": "VH-2",
                "geofence_name": "Riyadh Store",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T15:55:00+03:00",
                "exit_time": "2026-06-05T16:35:00+03:00",
            },
            {
                "trip_id": "UP-MISSING",
                "vehicle_id": "VH-3",
                "geofence_name": "Jeddah Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T06:00:00+03:00",
                "exit_time": "2026-06-05T06:36:00+03:00",
            },
        ]
    )


def test_clean_update_milestones_are_ok() -> None:
    """On-time updates with event evidence should be OK."""
    report = build_update_discipline_report(_trips(), _updates(), _visits())
    clean = report[(report["trip_id"] == "UP-OK") & (report["milestone"] == "ORIGIN DEPARTURE")]

    row = clean.iloc[0]
    assert row["update_status"] == "OK"
    assert row["exception_type"] == "none"
    assert row["update_delay_minutes"] == 5


def test_late_update_detection() -> None:
    """Updates beyond the configured grace should be late updates."""
    report = build_update_discipline_report(_trips(), _updates(), _visits())
    late = report[(report["trip_id"] == "UP-LATE") & (report["milestone"] == "ORIGIN DEPARTURE")]

    row = late.iloc[0]
    assert row["update_status"] == "NEEDS REVIEW"
    assert "late update" in row["exception_type"]
    assert row["update_delay_minutes"] == 70


def test_missing_update_detection() -> None:
    """Missing arrival updates should be update gaps."""
    report = build_update_discipline_report(_trips(), _updates(), _visits())
    missing = report[
        (report["trip_id"] == "UP-MISSING") & (report["milestone"] == "DESTINATION ARRIVAL")
    ]

    row = missing.iloc[0]
    assert row["update_status"] == "UPDATE GAP"
    assert "missing update" in row["exception_type"]


def test_sequence_issue_detection() -> None:
    """Arrival before departure should create a neutral sequence issue."""
    report = build_update_discipline_report(_trips(), _updates(), _visits())
    sequence_rows = report[report["trip_id"] == "UP-SEQ"]

    assert sequence_rows["exception_type"].str.contains("sequence issue").all()


def test_duplicate_update_detection() -> None:
    """Repeated milestone updates should be flagged as duplicates."""
    report = build_update_discipline_report(_trips(), _updates(), _visits())
    duplicate = report[(report["trip_id"] == "UP-DUP") & (report["milestone"] == "ORIGIN DEPARTURE")]

    assert "duplicate update" in duplicate.iloc[0]["exception_type"]


def test_no_actual_event_evidence_detection() -> None:
    """When visits are supplied but no matching event exists, evidence should be flagged."""
    report = build_update_discipline_report(_trips(), _updates(), _visits())
    no_evidence = report[
        (report["trip_id"] == "UP-DUP") & (report["milestone"] == "DESTINATION ARRIVAL")
    ]

    assert "no actual event evidence" in no_evidence.iloc[0]["exception_type"]


def test_run_update_pulse_and_write_outputs(tmp_path: Path) -> None:
    """UpdatePulse should return report, exceptions, KPIs, and CSV exports."""
    result = run_update_pulse(_trips(), _updates(), _visits())
    report_path, exceptions_path = write_outputs(result, tmp_path)

    assert result.kpis["total_milestones"] == 10
    assert result.kpis["late_updates"] >= 2
    assert not result.update_exceptions.empty
    assert report_path.exists()
    assert exceptions_path.exists()
