"""Unit tests for DelayLens delay classification."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from delay_lens.engine import run_delay_lens, write_outputs


def _trips() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trip_id": "DL-OK",
                "vehicle_id": "VH-1",
                "customer_name": "Gulf Fresh Foods",
                "carrier_name": "Desert Line Transport",
                "lane_id": "DXB-RUH",
                "origin": "Dubai South",
                "destination": "Riyadh Dry Port",
                "planned_departure": "2026-06-05T07:00:00+04:00",
                "promised_arrival": "2026-06-05T17:00:00+03:00",
            },
            {
                "trip_id": "DL-LATE-DEP",
                "vehicle_id": "VH-2",
                "lane_id": "JED-MED",
                "origin": "Jeddah Crossdock",
                "destination": "Medina Store",
                "planned_departure": "2026-06-05T08:00:00+03:00",
                "promised_arrival": "2026-06-05T14:00:00+03:00",
            },
            {
                "trip_id": "DL-ORIGIN-DWELL",
                "vehicle_id": "VH-3",
                "lane_id": "JED-MAK",
                "origin": "Jeddah Port",
                "destination": "Makkah DC",
                "planned_departure": "2026-06-05T08:00:00+03:00",
                "promised_arrival": "2026-06-05T12:00:00+03:00",
            },
            {
                "trip_id": "DL-HUB-DWELL",
                "vehicle_id": "VH-4",
                "lane_id": "RUH-DMM",
                "origin": "Riyadh Hub",
                "destination": "Dammam Hospital",
                "planned_departure": "2026-06-05T09:00:00+03:00",
                "promised_arrival": "2026-06-05T15:00:00+03:00",
            },
            {
                "trip_id": "DL-ENROUTE",
                "vehicle_id": "VH-5",
                "lane_id": "DMM-RUH",
                "origin": "Dammam Port",
                "destination": "Riyadh Store",
                "planned_departure": "2026-06-05T06:00:00+03:00",
                "promised_arrival": "2026-06-05T13:00:00+03:00",
            },
            {
                "trip_id": "DL-DEST-DWELL",
                "vehicle_id": "VH-6",
                "lane_id": "AUH-DXB",
                "origin": "Abu Dhabi DC",
                "destination": "Dubai Mall Receiving",
                "planned_departure": "2026-06-05T10:00:00+04:00",
                "promised_arrival": "2026-06-05T13:00:00+04:00",
            },
            {
                "trip_id": "DL-MISSING-SIGNAL",
                "vehicle_id": "VH-7",
                "lane_id": "DOH-DMM",
                "origin": "Doha Crossdock",
                "destination": "Dammam Cold Store",
                "planned_departure": "2026-06-05T05:00:00+03:00",
                "promised_arrival": "2026-06-05T16:00:00+03:00",
            },
            {
                "trip_id": "DL-BASELINE-MISSING",
                "vehicle_id": "VH-8",
                "lane_id": "BAH-RUH",
                "origin": "Bahrain Port",
                "destination": "Riyadh Parts DC",
                "planned_departure": "2026-06-05T06:30:00+03:00",
                "promised_arrival": "2026-06-05T14:30:00+03:00",
            },
            {
                "trip_id": "DL-LATE-ARRIVAL",
                "vehicle_id": "VH-9",
                "lane_id": "MCT-DXB",
                "origin": "Muscat DC",
                "destination": "Dubai Festival City",
                "planned_departure": "2026-06-05T08:00:00+04:00",
                "promised_arrival": "2026-06-05T14:00:00+04:00",
            },
        ]
    )


def _visits() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("DL-OK", "VH-1", "Dubai South", "ORIGIN", "2026-06-05T06:30:00+04:00", "2026-06-05T07:00:00+04:00", 30),
            ("DL-OK", "VH-1", "Riyadh Dry Port", "DESTINATION", "2026-06-05T16:45:00+03:00", "2026-06-05T17:15:00+03:00", 30),
            ("DL-LATE-DEP", "VH-2", "Jeddah Crossdock", "ORIGIN", "2026-06-05T07:45:00+03:00", "2026-06-05T08:45:00+03:00", 60),
            ("DL-LATE-DEP", "VH-2", "Medina Store", "CUSTOMER", "2026-06-05T14:35:00+03:00", "2026-06-05T15:05:00+03:00", 30),
            ("DL-ORIGIN-DWELL", "VH-3", "Jeddah Port", "PICKUP", "2026-06-05T06:25:00+03:00", "2026-06-05T08:00:00+03:00", 95),
            ("DL-ORIGIN-DWELL", "VH-3", "Makkah DC", "DELIVERY", "2026-06-05T11:50:00+03:00", "2026-06-05T12:30:00+03:00", 40),
            ("DL-HUB-DWELL", "VH-4", "Riyadh Hub", "ORIGIN", "2026-06-05T08:35:00+03:00", "2026-06-05T09:00:00+03:00", 25),
            ("DL-HUB-DWELL", "VH-4", "Hofuf Crossdock", "HUB", "2026-06-05T11:00:00+03:00", "2026-06-05T14:00:00+03:00", 180),
            ("DL-HUB-DWELL", "VH-4", "Dammam Hospital", "DESTINATION", "2026-06-05T16:30:00+03:00", "2026-06-05T17:00:00+03:00", 30),
            ("DL-ENROUTE", "VH-5", "Dammam Port", "ORIGIN", "2026-06-05T05:35:00+03:00", "2026-06-05T06:00:00+03:00", 25),
            ("DL-ENROUTE", "VH-5", "Riyadh Store", "CUSTOMER", "2026-06-05T15:05:00+03:00", "2026-06-05T15:40:00+03:00", 35),
            ("DL-DEST-DWELL", "VH-6", "Abu Dhabi DC", "ORIGIN", "2026-06-05T09:35:00+04:00", "2026-06-05T10:00:00+04:00", 25),
            ("DL-DEST-DWELL", "VH-6", "Dubai Mall Receiving", "DELIVERY", "2026-06-05T12:50:00+04:00", "2026-06-05T15:00:00+04:00", 130),
            (None, "VH-8", "Bahrain Port", "PORT", "2026-06-05T06:00:00+03:00", "2026-06-05T06:30:00+03:00", 30),
            (None, "VH-8", "Riyadh Parts DC", "DESTINATION", "2026-06-05T15:45:00+03:00", "2026-06-05T16:15:00+03:00", 30),
            ("DL-LATE-ARRIVAL", "VH-9", "Muscat DC", "ORIGIN", "2026-06-05T07:35:00+04:00", "2026-06-05T08:00:00+04:00", 25),
            ("DL-LATE-ARRIVAL", "VH-9", "Dubai Festival City", "DESTINATION", "2026-06-05T16:30:00+04:00", "2026-06-05T17:00:00+04:00", 30),
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
    ).assign(geofence_id="GF")


def _baselines() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("DXB-RUH", "Dubai South", "Riyadh Dry Port", 645),
            ("JED-MED", "Jeddah Crossdock", "Medina Store", 330),
            ("JED-MAK", "Jeddah Port", "Makkah DC", 240),
            ("RUH-DMM", "Riyadh Hub", "Dammam Hospital", 360),
            ("DMM-RUH", "Dammam Port", "Riyadh Store", 390),
            ("AUH-DXB", "Abu Dhabi DC", "Dubai Mall Receiving", 170),
            ("DOH-DMM", "Doha Crossdock", "Dammam Cold Store", 660),
            ("MCT-DXB", "Muscat DC", "Dubai Festival City", 510),
        ],
        columns=["lane_id", "origin", "destination", "baseline_minutes"],
    )


def _report() -> pd.DataFrame:
    return run_delay_lens(_trips(), _visits(), _baselines()).delay_classification_report


def _row(report: pd.DataFrame, trip_id: str) -> pd.Series:
    return report[report["trip_id"] == trip_id].iloc[0]


def test_clean_trip_is_on_track() -> None:
    row = _row(_report(), "DL-OK")
    assert row["primary_delay_reason"] == "ON TIME"
    assert row["risk_bucket"] == "ON TIME"


def test_origin_exit_detection() -> None:
    row = _row(_report(), "DL-OK")
    assert row["actual_origin_exit"].isoformat() == "2026-06-05T03:00:00+00:00"


def test_destination_entry_detection() -> None:
    row = _row(_report(), "DL-OK")
    assert row["actual_destination_entry"].isoformat() == "2026-06-05T13:45:00+00:00"


def test_late_departure_detection() -> None:
    row = _row(_report(), "DL-LATE-DEP")
    assert row["primary_delay_reason"] == "LATE DEPARTURE"
    assert row["severity"] == "HIGH"


def test_origin_dwell_detection() -> None:
    row = _row(_report(), "DL-ORIGIN-DWELL")
    assert row["primary_delay_reason"] == "ORIGIN DWELL"
    assert row["origin_dwell_minutes"] == 95


def test_hub_dwell_detection() -> None:
    row = _row(_report(), "DL-HUB-DWELL")
    assert row["primary_delay_reason"] == "HUB DWELL"
    assert row["hub_dwell_minutes"] == 180


def test_enroute_delay_detection() -> None:
    row = _row(_report(), "DL-ENROUTE")
    assert row["primary_delay_reason"] == "ENROUTE DELAY"
    assert row["baseline_delta_minutes"] > 30


def test_destination_dwell_detection() -> None:
    row = _row(_report(), "DL-DEST-DWELL")
    assert row["primary_delay_reason"] == "DESTINATION DWELL"
    assert row["destination_dwell_minutes"] == 130


def test_missing_signal_handling() -> None:
    row = _row(_report(), "DL-MISSING-SIGNAL")
    assert row["primary_delay_reason"] == "MISSING SIGNAL"
    assert row["risk_bucket"] == "DATA MISSING"


def test_baseline_missing_handling() -> None:
    row = _row(_report(), "DL-BASELINE-MISSING")
    assert row["primary_delay_reason"] == "BASELINE MISSING"
    assert row["risk_bucket"] == "WATCH"


def test_late_arrival_fallback_and_critical_risk() -> None:
    row = _row(_report(), "DL-LATE-ARRIVAL")
    assert row["primary_delay_reason"] == "LATE ARRIVAL"
    assert row["arrival_delay_minutes"] == 150
    assert row["risk_bucket"] == "CRITICAL"
    assert row["severity"] == "CRITICAL"


def test_risk_bucket_classification() -> None:
    report = _report()
    assert set(report["risk_bucket"]).issuperset(
        {"ON TIME", "WATCH", "DELAYED", "CRITICAL", "DATA MISSING"}
    )


def test_export_smoke(tmp_path: Path) -> None:
    result = run_delay_lens(_trips(), _visits(), _baselines())
    report_path, critical_path = write_outputs(result, tmp_path)
    assert report_path.exists()
    assert critical_path.exists()
    assert len(pd.read_csv(report_path)) == len(result.delay_classification_report)
    assert len(pd.read_csv(critical_path)) == len(result.critical_delays)


def test_demo_data_smoke() -> None:
    base = Path("delay_lens/demo_data")
    result = run_delay_lens(
        pd.read_csv(base / "trips.csv"),
        pd.read_csv(base / "visit_events.csv"),
        pd.read_csv(base / "lane_baselines.csv"),
    )
    assert result.kpis["total_trips"] == 9
    assert set(result.delay_classification_report["primary_delay_reason"]).issuperset(
        {
            "ON TIME",
            "LATE DEPARTURE",
            "ORIGIN DWELL",
            "HUB DWELL",
            "ENROUTE DELAY",
            "DESTINATION DWELL",
            "MISSING SIGNAL",
            "BASELINE MISSING",
            "LATE ARRIVAL",
        }
    )
