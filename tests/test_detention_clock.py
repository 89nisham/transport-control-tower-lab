"""Unit tests for DetentionClock detention classification and exports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from detention_clock.engine import build_detention_report, run_detention_clock, write_outputs


def _visit_events() -> pd.DataFrame:
    """Build a mixed detention visit fixture."""
    return pd.DataFrame(
        [
            {
                "trip_id": "T-FREE",
                "vehicle_id": "VH-1",
                "geofence_id": "RUH_DC",
                "geofence_name": "Riyadh Dry Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T05:00:00+03:00",
                "exit_time": "2026-06-05T06:30:00+03:00",
                "dwell_minutes": 90,
            },
            {
                "trip_id": "T-APPROACH",
                "vehicle_id": "VH-2",
                "geofence_id": "RUH_DC",
                "geofence_name": "Riyadh Dry Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T05:00:00+03:00",
                "exit_time": "2026-06-05T06:50:00+03:00",
                "dwell_minutes": 110,
            },
            {
                "trip_id": "T-CHARGE",
                "vehicle_id": "VH-3",
                "geofence_id": "RUH_DC",
                "geofence_name": "Riyadh Dry Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T05:00:00+03:00",
                "exit_time": "2026-06-05T08:30:00+03:00",
                "dwell_minutes": 210,
            },
            {
                "trip_id": "T-MIN",
                "vehicle_id": "VH-4",
                "geofence_id": "JED_PORT",
                "geofence_name": "Jeddah Islamic Port",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T05:00:00Z",
                "exit_time": "2026-06-05T07:40:00Z",
                "dwell_minutes": 160,
            },
            {
                "trip_id": "T-MISSING",
                "vehicle_id": "VH-5",
                "geofence_id": "RUH_DC",
                "geofence_name": "Riyadh Dry Port",
                "geofence_type": "ORIGIN",
                "enter_time": "2026-06-05T05:00:00Z",
                "exit_time": None,
                "dwell_minutes": 180,
            },
            {
                "trip_id": "T-ZERO",
                "vehicle_id": "VH-6",
                "geofence_id": "JED_PORT",
                "geofence_name": "Jeddah Islamic Port",
                "geofence_type": "DESTINATION",
                "enter_time": "2026-06-05T05:00:00Z",
                "exit_time": "2026-06-05T05:00:00Z",
                "dwell_minutes": 0,
            },
        ]
    )


def _rules() -> pd.DataFrame:
    """Build detention rule fixtures."""
    return pd.DataFrame(
        [
            {
                "rule_id": "RULE-RUH-ACME",
                "customer_name": "Acme Foods",
                "geofence_type": "ORIGIN",
                "geofence_id": "RUH_DC",
                "free_minutes": 120,
                "rate_type": "hourly",
                "rate_per_hour": 180,
                "minimum_charge": 250,
                "currency": "SAR",
            },
            {
                "rule_id": "RULE-JED-ACME",
                "customer_name": "Acme Foods",
                "geofence_type": "DESTINATION",
                "geofence_id": "JED_PORT",
                "free_minutes": 150,
                "rate_type": "hourly",
                "rate_per_hour": 220,
                "minimum_charge": 300,
                "currency": "SAR",
            },
        ]
    )


def _trips() -> pd.DataFrame:
    """Build trip context fixtures."""
    return pd.DataFrame(
        [
            {
                "trip_id": trip_id,
                "customer_name": "Acme Foods",
                "carrier_name": "Desert Line Transport",
                "origin": "Riyadh",
                "destination": "Jeddah",
                "planned_arrival": "2026-06-05T12:00:00+03:00",
                "planned_departure": "2026-06-05T04:00:00+03:00",
            }
            for trip_id in [
                "T-FREE",
                "T-APPROACH",
                "T-CHARGE",
                "T-MIN",
                "T-MISSING",
                "T-ZERO",
            ]
        ]
    )


def test_detention_clock_assigns_free_time_buckets() -> None:
    """DetentionClock should separate free, approaching, and no-detention visits."""
    report = build_detention_report(_visit_events(), _rules(), _trips())
    buckets = dict(zip(report["trip_id"], report["risk_bucket"], strict=False))

    assert buckets["T-FREE"] == "WITHIN FREE TIME"
    assert buckets["T-APPROACH"] == "APPROACHING FREE TIME"
    assert buckets["T-ZERO"] == "NO DETENTION"


def test_chargeable_minutes_are_after_free_time_only() -> None:
    """Chargeable minutes should be dwell minus free time."""
    report = build_detention_report(_visit_events(), _rules(), _trips())
    charge = report[report["trip_id"] == "T-CHARGE"].iloc[0]

    assert charge["risk_bucket"] == "DETENTION"
    assert charge["chargeable_minutes"] == 90
    assert charge["chargeable_hours"] == 1.5
    assert charge["estimated_charge"] == 270


def test_minimum_charge_applies_only_when_chargeable() -> None:
    """Minimum charge should lift small chargeable cases but not free-time cases."""
    report = build_detention_report(_visit_events(), _rules(), _trips())
    minimum_case = report[report["trip_id"] == "T-MIN"].iloc[0]
    free_case = report[report["trip_id"] == "T-FREE"].iloc[0]

    assert minimum_case["chargeable_minutes"] == 10
    assert minimum_case["estimated_charge"] == 300
    assert free_case["chargeable_minutes"] == 0
    assert free_case["estimated_charge"] == 0


def test_missing_exit_is_flagged_without_charge() -> None:
    """Visits with entry but no exit should be flagged before charge calculation."""
    report = build_detention_report(_visit_events(), _rules(), _trips())
    missing = report[report["trip_id"] == "T-MISSING"].iloc[0]

    assert missing["risk_bucket"] == "MISSING EXIT"
    assert missing["chargeable_minutes"] == 0
    assert "Confirm exit time" in missing["suggested_action"]


def test_detention_clock_exports_smoke(tmp_path: Path) -> None:
    """DetentionClock should write report and chargeable-only CSV exports."""
    result = run_detention_clock(_visit_events(), _rules(), _trips())
    report_path, chargeable_path = write_outputs(result, tmp_path)

    assert report_path.exists()
    assert chargeable_path.exists()
    assert "detention_report" in report_path.name
    assert not pd.read_csv(chargeable_path).empty

