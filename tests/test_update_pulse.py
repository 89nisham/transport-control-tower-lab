"""Unit tests for UpdatePulse update-discipline review."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from update_pulse.engine import build_expected_milestones, run_update_pulse, write_outputs
from update_pulse.models import UpdatePulseSettings


def _trips() -> pd.DataFrame:
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
                "trip_id": "UP-MISSING",
                "vehicle_id": "VH-2",
                "carrier_name": "Gulf Road Carriers",
                "origin": "Dammam Port",
                "destination": "Riyadh Store",
                "planned_departure": "2026-06-05T08:00:00+03:00",
                "promised_arrival": "2026-06-05T15:00:00+03:00",
            },
            {
                "trip_id": "UP-LATE",
                "vehicle_id": "VH-3",
                "origin": "Jeddah Port",
                "destination": "Makkah DC",
                "planned_departure": "2026-06-05T06:30:00+03:00",
                "promised_arrival": "2026-06-05T11:30:00+03:00",
            },
            {
                "trip_id": "UP-EARLY",
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
            {
                "trip_id": "UP-SEQ",
                "vehicle_id": "VH-6",
                "origin": "Dubai South",
                "destination": "Doha DC",
                "planned_departure": "2026-06-05T05:00:00+04:00",
                "promised_arrival": "2026-06-05T16:00:00+03:00",
            },
        ]
    )


def _updates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("UP-OK", "VH-1", "2026-06-05T04:55:00+03:00", "ASSIGNED"),
            ("UP-OK", "VH-1", "2026-06-05T06:52:00+03:00", "ARRIVED_ORIGIN"),
            ("UP-OK", "VH-1", "2026-06-05T07:04:00+03:00", "DEPARTED_ORIGIN"),
            ("UP-OK", "VH-1", "2026-06-05T16:58:00+03:00", "ARRIVED_DESTINATION"),
            ("UP-OK", "VH-1", "2026-06-05T18:12:00+03:00", "DELIVERED"),
            ("UP-MISSING", "VH-2", "2026-06-05T05:58:00+03:00", "ASSIGNED"),
            ("UP-MISSING", "VH-2", "2026-06-05T07:28:00+03:00", "ARRIVED_ORIGIN"),
            ("UP-MISSING", "VH-2", "2026-06-05T15:05:00+03:00", "ARRIVED_DESTINATION"),
            ("UP-MISSING", "VH-2", "2026-06-05T16:35:00+03:00", "DELIVERED"),
            ("UP-LATE", "VH-3", "2026-06-05T04:30:00+03:00", "ASSIGNED"),
            ("UP-LATE", "VH-3", "2026-06-05T06:05:00+03:00", "ARRIVED_ORIGIN"),
            ("UP-LATE", "VH-3", "2026-06-05T06:45:00+03:00", "DEPARTED_ORIGIN"),
            ("UP-LATE", "VH-3", "2026-06-05T12:10:00+03:00", "ARRIVED_DESTINATION"),
            ("UP-LATE", "VH-3", "2026-06-05T12:45:00+03:00", "DELIVERED"),
            ("UP-EARLY", "VH-4", "2026-06-05T07:00:00+03:00", "ASSIGNED"),
            ("UP-EARLY", "VH-4", "2026-06-05T08:40:00+03:00", "ARRIVED_ORIGIN"),
            ("UP-EARLY", "VH-4", "2026-06-05T09:05:00+03:00", "DEPARTED_ORIGIN"),
            ("UP-EARLY", "VH-4", "2026-06-05T15:08:00+03:00", "ARRIVED_DESTINATION"),
            ("UP-EARLY", "VH-4", "2026-06-05T15:20:00+03:00", "DELIVERED"),
            ("UP-DUP", "VH-5", "2026-06-05T08:00:00+03:00", "ASSIGNED"),
            ("UP-DUP", "VH-5", "2026-06-05T09:42:00+03:00", "ARRIVED_ORIGIN"),
            ("UP-DUP", "VH-5", "2026-06-05T09:45:00+03:00", "ARRIVED_ORIGIN"),
            ("UP-DUP", "VH-5", "2026-06-05T10:05:00+03:00", "DEPARTED_ORIGIN"),
            ("UP-DUP", "VH-5", "2026-06-05T15:28:00+03:00", "ARRIVED_DESTINATION"),
            ("UP-DUP", "VH-5", "2026-06-05T16:15:00+03:00", "DELIVERED"),
            ("UP-SEQ", "VH-6", "2026-06-05T02:55:00+04:00", "ASSIGNED"),
            ("UP-SEQ", "VH-6", "2026-06-05T05:35:00+04:00", "DEPARTED_ORIGIN"),
            ("UP-SEQ", "VH-6", "2026-06-05T06:05:00+04:00", "ARRIVED_ORIGIN"),
        ],
        columns=["trip_id", "vehicle_id", "update_time", "status"],
    ).assign(updated_by="driver", source="TMS")


def _visits() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("UP-OK", "VH-1", "Riyadh Hub", "ORIGIN", "2026-06-05T06:50:00+03:00", "2026-06-05T07:03:00+03:00"),
            ("UP-OK", "VH-1", "Jeddah DC", "DESTINATION", "2026-06-05T16:55:00+03:00", "2026-06-05T18:10:00+03:00"),
            ("UP-MISSING", "VH-2", "Dammam Port", "PICKUP", "2026-06-05T07:25:00+03:00", "2026-06-05T08:55:00+03:00"),
            ("UP-MISSING", "VH-2", "Riyadh Store", "CUSTOMER", "2026-06-05T15:00:00+03:00", "2026-06-05T16:35:00+03:00"),
            ("UP-LATE", "VH-3", "Jeddah Port", "ORIGIN", "2026-06-05T06:00:00+03:00", "2026-06-05T06:44:00+03:00"),
            ("UP-LATE", "VH-3", "Makkah DC", "DELIVERY", "2026-06-05T11:35:00+03:00", "2026-06-05T12:40:00+03:00"),
            ("UP-EARLY", "VH-4", "Riyadh Pharma Hub", "HUB", "2026-06-05T08:38:00+03:00", "2026-06-05T09:03:00+03:00"),
            ("UP-EARLY", "VH-4", "Dammam Hospital", "DESTINATION", "2026-06-05T15:04:00+03:00", "2026-06-05T16:00:00+03:00"),
            ("UP-DUP", "VH-5", "Jeddah Crossdock", "ORIGIN", "2026-06-05T09:40:00+03:00", "2026-06-05T10:04:00+03:00"),
            ("UP-DUP", "VH-5", "Medina Store", "DELIVERY", "2026-06-05T15:26:00+03:00", "2026-06-05T16:10:00+03:00"),
            (None, "VH-6", "Dubai South", "ORIGIN", "2026-06-05T05:35:00+04:00", "2026-06-05T06:00:00+04:00"),
        ],
        columns=["trip_id", "vehicle_id", "geofence_name", "geofence_type", "enter_time", "exit_time"],
    ).assign(geofence_id="GF", dwell_minutes=30)


def _report() -> pd.DataFrame:
    return run_update_pulse(_trips(), _updates(), _visits()).update_discipline_report


def _row(report: pd.DataFrame, trip_id: str, expected_status: str) -> pd.Series:
    return report[(report["trip_id"] == trip_id) & (report["expected_status"] == expected_status)].iloc[0]


def test_expected_milestone_generation() -> None:
    milestones = build_expected_milestones(_trips().head(1), UpdatePulseSettings(include_pod_collected=True))
    assert milestones["expected_status"].tolist() == [
        "ASSIGNED",
        "ARRIVED_ORIGIN",
        "DEPARTED_ORIGIN",
        "ARRIVED_DESTINATION",
        "DELIVERED",
        "POD_COLLECTED",
    ]
    assert _row(milestones, "UP-OK", "ASSIGNED")["expected_time"].hour == 2


def test_missing_update_detection() -> None:
    row = _row(_report(), "UP-MISSING", "DEPARTED_ORIGIN")
    assert row["update_gap_type"] == "MISSING UPDATE"
    assert row["severity"] == "HIGH"


def test_late_update_detection() -> None:
    row = _row(_report(), "UP-LATE", "ARRIVED_DESTINATION")
    assert row["update_gap_type"] == "LATE UPDATE"


def test_early_update_detection() -> None:
    row = _row(_report(), "UP-EARLY", "DELIVERED")
    assert row["update_gap_type"] == "EARLY UPDATE"
    assert row["severity"] == "HIGH"


def test_duplicate_update_detection() -> None:
    row = _row(_report(), "UP-DUP", "ARRIVED_ORIGIN")
    assert row["update_gap_type"] == "DUPLICATE UPDATE"


def test_out_of_sequence_detection() -> None:
    row = _row(_report(), "UP-SEQ", "ARRIVED_ORIGIN")
    assert row["sequence_status"] == "OUT OF SEQUENCE"
    assert row["update_gap_type"] == "OUT OF SEQUENCE"


def test_no_actual_event_evidence() -> None:
    row = _row(_report(), "UP-SEQ", "ARRIVED_DESTINATION")
    assert row["evidence_status"] == "NO ACTUAL EVENT EVIDENCE"


def test_origin_destination_visit_evidence_matching() -> None:
    report = _report()
    assert _row(report, "UP-OK", "ARRIVED_ORIGIN")["evidence_status"] == "SUPPORTED BY ACTUAL EVENT"
    assert _row(report, "UP-OK", "DELIVERED")["evidence_status"] == "SUPPORTED BY ACTUAL EVENT"


def test_risk_bucket_classification() -> None:
    report = _report()
    assert _row(report, "UP-MISSING", "DEPARTED_ORIGIN")["risk_bucket"] == "DATA MISSING"
    assert _row(report, "UP-OK", "ASSIGNED")["risk_bucket"] == "OK"


def test_export_smoke(tmp_path: Path) -> None:
    result = run_update_pulse(_trips(), _updates(), _visits())
    report_path, exceptions_path = write_outputs(result, tmp_path)
    assert report_path.exists()
    assert exceptions_path.exists()
    assert len(pd.read_csv(report_path)) == len(result.update_discipline_report)
    assert len(pd.read_csv(exceptions_path)) == len(result.update_exceptions)


def test_demo_data_smoke() -> None:
    base = Path("update_pulse/demo_data")
    result = run_update_pulse(
        pd.read_csv(base / "trips.csv"),
        pd.read_csv(base / "tms_updates.csv"),
        pd.read_csv(base / "visit_events.csv"),
    )
    assert result.kpis["total_trips"] == 8
    assert result.kpis["total_expected_updates"] == 40
    assert set(result.update_discipline_report["update_gap_type"]).issuperset(
        {"MISSING UPDATE", "LATE UPDATE", "EARLY UPDATE", "DUPLICATE UPDATE", "OUT OF SEQUENCE"}
    )
