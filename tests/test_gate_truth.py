"""Unit tests for GateTruth trip gate verification."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from gate_truth.engine import build_gate_truth_report, run_gate_truth, write_outputs


def _trips() -> pd.DataFrame:
    """Build mixed planned trip fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": "T-OK",
                "vehicle_id": "VH-1",
                "customer_name": "Acme Foods",
                "carrier_name": "Desert Line Transport",
                "origin": "Riyadh Hub",
                "destination": "Jeddah DC",
                "origin_geofence_id": "RUH_HUB",
                "destination_geofence_id": "JED_DC",
                "planned_departure": "2026-06-05T07:00:00+03:00",
                "promised_arrival": "2026-06-05T17:00:00+03:00",
            },
            {
                "trip_id": "T-LATE",
                "vehicle_id": "VH-2",
                "customer_name": "Gulf Retail",
                "carrier_name": "Gulf Road Carriers",
                "origin": "Dammam Port",
                "destination": "Riyadh Store",
                "origin_geofence_id": "DMM_PORT",
                "destination_geofence_id": "RUH_STORE",
                "planned_departure": "2026-06-05T08:00:00+03:00",
                "promised_arrival": "2026-06-05T15:00:00+03:00",
            },
            {
                "trip_id": "T-MISSING",
                "vehicle_id": "VH-3",
                "customer_name": "Fresh Basket",
                "carrier_name": "North Star Logistics",
                "origin": "Jeddah Port",
                "destination": "Makkah DC",
                "origin_geofence_id": "JED_PORT",
                "destination_geofence_id": "MAK_DC",
                "planned_departure": "2026-06-05T06:30:00+03:00",
                "promised_arrival": "2026-06-05T11:30:00+03:00",
            },
            {
                "trip_id": "T-AMB",
                "vehicle_id": "VH-4",
                "customer_name": "Acme Foods",
                "carrier_name": "Desert Line Transport",
                "origin": "Riyadh Hub",
                "destination": "Dammam Yard",
                "origin_geofence_id": "",
                "destination_geofence_id": "DMM_YARD",
                "planned_departure": "2026-06-05T07:30:00+03:00",
                "promised_arrival": "2026-06-05T16:30:00+03:00",
            },
            {
                "trip_id": "T-NONE",
                "vehicle_id": "VH-5",
                "customer_name": "Najd Pharma",
                "carrier_name": "Eastern Freight",
                "origin": "Riyadh Pharma Hub",
                "destination": "Dammam Hospital",
                "origin_geofence_id": "RUH_PHARMA",
                "destination_geofence_id": "DMM_HOSP",
                "planned_departure": "2026-06-05T09:00:00+03:00",
                "promised_arrival": "2026-06-05T15:00:00+03:00",
            },
        ]
    )


def _visits() -> pd.DataFrame:
    """Build visit event evidence fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": "T-OK",
                "vehicle_id": "VH-1",
                "geofence_id": "RUH_HUB",
                "geofence_name": "Riyadh Hub",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T06:20:00+03:00",
                "exit_time": "2026-06-05T06:55:00+03:00",
                "dwell_minutes": 35,
            },
            {
                "trip_id": "T-OK",
                "vehicle_id": "VH-1",
                "geofence_id": "JED_DC",
                "geofence_name": "Jeddah DC",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T16:40:00+03:00",
                "exit_time": "2026-06-05T18:00:00+03:00",
                "dwell_minutes": 80,
            },
            {
                "trip_id": "T-LATE",
                "vehicle_id": "VH-2",
                "geofence_id": "DMM_PORT",
                "geofence_name": "Dammam Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T07:10:00+03:00",
                "exit_time": "2026-06-05T09:10:00+03:00",
                "dwell_minutes": 120,
            },
            {
                "trip_id": "T-LATE",
                "vehicle_id": "VH-2",
                "geofence_id": "RUH_STORE",
                "geofence_name": "Riyadh Store",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T16:00:00+03:00",
                "exit_time": "2026-06-05T16:30:00+03:00",
                "dwell_minutes": 30,
            },
            {
                "trip_id": "T-MISSING",
                "vehicle_id": "VH-3",
                "geofence_id": "JED_PORT",
                "geofence_name": "Jeddah Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T06:00:00+03:00",
                "exit_time": None,
                "dwell_minutes": 90,
            },
            {
                "trip_id": "T-AMB",
                "vehicle_id": "VH-4",
                "geofence_id": "RUH_HUB_A",
                "geofence_name": "Riyadh Hub Gate A",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T06:50:00+03:00",
                "exit_time": "2026-06-05T07:25:00+03:00",
                "dwell_minutes": 35,
            },
            {
                "trip_id": "T-AMB",
                "vehicle_id": "VH-4",
                "geofence_id": "RUH_HUB_B",
                "geofence_name": "Riyadh Hub Gate B",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T06:55:00+03:00",
                "exit_time": "2026-06-05T07:35:00+03:00",
                "dwell_minutes": 40,
            },
            {
                "trip_id": "T-AMB",
                "vehicle_id": "VH-4",
                "geofence_id": "DMM_YARD",
                "geofence_name": "Dammam Yard",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T16:10:00+03:00",
                "exit_time": "2026-06-05T17:00:00+03:00",
                "dwell_minutes": 50,
            },
        ]
    )


def test_gate_truth_verifies_clean_origin_and_destination() -> None:
    """Trips with matching origin exit and destination entry should be verified."""
    report = build_gate_truth_report(_trips(), _visits())
    verified = report[report["trip_id"] == "T-OK"].iloc[0]

    assert verified["gate_truth_status"] == "OK"
    assert verified["exception_type"] == "NONE"
    assert pd.notna(verified["actual_origin_exit"])
    assert pd.notna(verified["actual_destination_entry"])
    assert verified["confidence_bucket"] == "HIGH"


def test_origin_exit_detection() -> None:
    """GateTruth should capture actual origin exit evidence."""
    report = build_gate_truth_report(_trips(), _visits())
    verified = report[report["trip_id"] == "T-OK"].iloc[0]

    assert str(verified["actual_origin_exit"]) == "2026-06-05 03:55:00+00:00"


def test_destination_entry_detection() -> None:
    """GateTruth should capture actual destination entry evidence."""
    report = build_gate_truth_report(_trips(), _visits())
    verified = report[report["trip_id"] == "T-OK"].iloc[0]

    assert str(verified["actual_destination_entry"]) == "2026-06-05 13:40:00+00:00"


def test_late_start_detection() -> None:
    """Origin exits after the configured grace should be late starts."""
    report = build_gate_truth_report(_trips(), _visits())
    late = report[report["trip_id"] == "T-LATE"].iloc[0]

    assert late["gate_truth_status"] == "EXCEPTION"
    assert "LATE START" in late["exception_type"]
    assert late["start_delay_minutes"] == 70


def test_late_arrival_detection() -> None:
    """Destination entries after the configured grace should be late arrivals."""
    report = build_gate_truth_report(_trips(), _visits())
    late = report[report["trip_id"] == "T-LATE"].iloc[0]

    assert late["gate_truth_status"] == "EXCEPTION"
    assert "LATE ARRIVAL" in late["exception_type"]
    assert late["arrival_delay_minutes"] == 60


def test_missing_origin_exit() -> None:
    """Origin visits without exit_time should be flagged."""
    report = build_gate_truth_report(_trips(), _visits())
    missing = report[report["trip_id"] == "T-MISSING"].iloc[0]

    assert missing["gate_truth_status"] == "INCOMPLETE"
    assert "MISSING ORIGIN EXIT" in missing["exception_type"]


def test_missing_destination_entry() -> None:
    """Trips without destination visit evidence should be flagged."""
    report = build_gate_truth_report(_trips(), _visits())
    missing = report[report["trip_id"] == "T-MISSING"].iloc[0]

    assert missing["gate_truth_status"] == "INCOMPLETE"
    assert "MISSING DESTINATION ENTRY" in missing["exception_type"]


def test_ambiguous_event_match_is_preserved_for_review() -> None:
    """Multiple plausible candidate visits should not be silently collapsed."""
    report = build_gate_truth_report(_trips(), _visits())
    ambiguous = report[report["trip_id"] == "T-AMB"].iloc[0]

    assert ambiguous["gate_truth_status"] == "AMBIGUOUS MATCH"
    assert ambiguous["origin_candidate_count"] == 2
    assert "AMBIGUOUS MATCH" in ambiguous["exception_type"]


def test_no_visit_evidence() -> None:
    """Trips with no useful visit events should keep a clear no-evidence reason."""
    report = build_gate_truth_report(_trips(), _visits())
    no_evidence = report[report["trip_id"] == "T-NONE"].iloc[0]

    assert no_evidence["gate_truth_status"] == "INCOMPLETE"
    assert "NO VISIT EVIDENCE" in no_evidence["exception_type"]
    assert no_evidence["confidence_bucket"] == "NO EVIDENCE"


def test_planned_stops_can_supply_geofence_hints() -> None:
    """Optional planned stops should strengthen matching when trip IDs omit geofence IDs."""
    trips = _trips().copy()
    trips.loc[trips["trip_id"] == "T-OK", "origin_geofence_id"] = ""
    stops = pd.DataFrame(
        [
            {
                "trip_id": "T-OK",
                "vehicle_id": "VH-1",
                "geofence_id": "RUH_HUB",
                "stop_sequence": 1,
                "stop_type": "ORIGIN",
            }
        ]
    )

    report = build_gate_truth_report(trips, _visits(), stops)
    verified = report[report["trip_id"] == "T-OK"].iloc[0]

    assert verified["origin_geofence_id"] == "RUH_HUB"
    assert verified["origin_candidate_count"] == 1


def test_demo_data_smoke() -> None:
    """Bundled demo data should run without uploads."""
    demo_dir = Path("gate_truth/demo_data")
    result = run_gate_truth(
        pd.read_csv(demo_dir / "trips.csv"),
        pd.read_csv(demo_dir / "visit_events.csv"),
        pd.read_csv(demo_dir / "planned_stops.csv"),
    )

    assert result.kpis["total_trips"] > 0
    assert not result.gate_truth_report.empty


def test_gate_truth_exports_smoke(tmp_path: Path) -> None:
    """GateTruth should write full report and exceptions-only CSV exports."""
    result = run_gate_truth(_trips(), _visits())
    report_path, exceptions_path = write_outputs(result, tmp_path)

    assert report_path.exists()
    assert exceptions_path.exists()
    assert "gate_truth_report" in report_path.name
    assert "gate_exceptions" in exceptions_path.name
    assert set(pd.read_csv(report_path).columns).issuperset(
        {"gate_truth_status", "exception_type", "evidence", "confidence_bucket"}
    )
    assert list(pd.read_csv(exceptions_path).columns) == [
        "trip_id",
        "vehicle_id",
        "customer_name",
        "carrier_name",
        "exception_type",
        "severity",
        "evidence",
        "suggested_action",
    ]
