"""Unit tests for LaneLab lane baseline generation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from lane_lab.engine import (
    BASELINE_COLUMNS,
    OUTLIER_COLUMNS,
    run_lane_lab,
    write_outputs,
)


def _trips() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("LL-A-01", "VH-A01", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge Freight", "Riyadh Dry Port", "Dammam DC", "2026-05-01T06:00:00+03:00", "2026-05-01T13:00:00+03:00"),
            ("LL-A-02", "VH-A02", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge Freight", "Riyadh Dry Port", "Dammam DC", "2026-05-02T06:00:00+03:00", "2026-05-02T13:00:00+03:00"),
            ("LL-A-03", "VH-A03", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge Freight", "Riyadh Dry Port", "Dammam DC", "2026-05-03T06:00:00+03:00", "2026-05-03T13:00:00+03:00"),
            ("LL-A-04", "VH-A04", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge Freight", "Riyadh Dry Port", "Dammam DC", "2026-05-04T06:00:00+03:00", "2026-05-04T13:00:00+03:00"),
            ("LL-A-05", "VH-A05", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge Freight", "Riyadh Dry Port", "Dammam DC", "2026-05-05T06:00:00+03:00", "2026-05-05T13:00:00+03:00"),
            ("LL-A-06", "VH-A06", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge Freight", "Riyadh Dry Port", "Dammam DC", "2026-05-06T06:00:00+03:00", "2026-05-06T13:00:00+03:00"),
            ("LL-B-01", "VH-B01", "JED-RUH", "Red Sea Pharma", "Hejaz Line Logistics", "Jeddah Port", "Riyadh DC", "2026-05-01T08:00:00+03:00", "2026-05-01T20:00:00+03:00"),
            ("LL-B-02", "VH-B02", "JED-RUH", "Red Sea Pharma", "Hejaz Line Logistics", "Jeddah Port", "Riyadh DC", "2026-05-02T08:00:00+03:00", "2026-05-02T20:00:00+03:00"),
            ("LL-C-01", "VH-C01", "DXB-AUH", "Emirates Home Supply", "Desert Falcon Transport", "Dubai JAFZA", "Abu Dhabi Store", "2026-05-03T09:00:00+04:00", "2026-05-03T13:00:00+04:00"),
            ("LL-MISSING", "VH-D01", "KWI-DOH", "GCC Electronics", "Peninsula Freight", "Kuwait DC", "Doha Retail Hub", "2026-05-04T06:00:00+03:00", "2026-05-04T18:00:00+03:00"),
        ],
        columns=[
            "trip_id",
            "vehicle_id",
            "lane_id",
            "customer_name",
            "carrier_name",
            "origin",
            "destination",
            "planned_departure",
            "promised_arrival",
        ],
    )


def _visits() -> pd.DataFrame:
    rows = [
        ("LL-A-01", "VH-A01", "Riyadh Dry Port", "ORIGIN", "2026-05-01T06:00:00+03:00", "2026-05-01T06:30:00+03:00", 30, "Dammam DC", "DESTINATION", "2026-05-01T12:30:00+03:00"),
        ("LL-A-02", "VH-A02", "Riyadh Dry Port", "ORIGIN", "2026-05-02T06:00:00+03:00", "2026-05-02T06:45:00+03:00", 45, "Dammam DC", "DESTINATION", "2026-05-02T13:00:00+03:00"),
        ("LL-A-03", "VH-A03", "Riyadh Dry Port", "ORIGIN", "2026-05-03T06:00:00+03:00", "2026-05-03T06:40:00+03:00", 40, "Dammam DC", "DESTINATION", "2026-05-03T13:00:00+03:00"),
        ("LL-A-04", "VH-A04", "Riyadh Dry Port", "ORIGIN", "2026-05-04T06:00:00+03:00", "2026-05-04T06:45:00+03:00", 45, "Dammam DC", "DESTINATION", "2026-05-04T13:00:00+03:00"),
        ("LL-A-05", "VH-A05", "Riyadh Dry Port", "ORIGIN", "2026-05-05T06:00:00+03:00", "2026-05-05T06:45:00+03:00", 45, "Dammam DC", "DESTINATION", "2026-05-05T13:00:00+03:00"),
        ("LL-A-06", "VH-A06", "Riyadh Dry Port", "ORIGIN", "2026-05-06T06:00:00+03:00", "2026-05-06T06:35:00+03:00", 35, "Dammam DC", "DESTINATION", "2026-05-06T19:20:00+03:00"),
        ("LL-B-01", "VH-B01", "Jeddah Port", "PICKUP", "2026-05-01T08:00:00+03:00", "2026-05-01T09:00:00+03:00", 60, "Riyadh DC", "CUSTOMER", "2026-05-01T19:00:00+03:00"),
        (None, "VH-B02", "Jeddah Port", "PICKUP", "2026-05-02T08:00:00+03:00", "2026-05-02T09:10:00+03:00", 70, "Riyadh DC", "CUSTOMER", "2026-05-02T19:30:00+03:00"),
        ("LL-C-01", "VH-C01", "Dubai JAFZA", "HUB", "2026-05-03T09:00:00+04:00", "2026-05-03T09:35:00+04:00", 35, "Abu Dhabi Store", "DELIVERY", "2026-05-03T09:20:00+04:00"),
        ("LL-MISSING", "VH-D01", "Kuwait DC", "ORIGIN", "2026-05-04T06:00:00+03:00", "2026-05-04T07:00:00+03:00", 60, None, None, None),
    ]
    event_rows = []
    for (
        trip_id,
        vehicle_id,
        origin_name,
        origin_type,
        origin_enter,
        origin_exit,
        origin_dwell,
        dest_name,
        dest_type,
        dest_enter,
    ) in rows:
        event_rows.append(
            (trip_id, vehicle_id, f"GF-{vehicle_id}-O", origin_name, origin_type, origin_enter, origin_exit, origin_dwell)
        )
        if dest_name is not None:
            event_rows.append(
                (trip_id, vehicle_id, f"GF-{vehicle_id}-D", dest_name, dest_type, dest_enter, dest_enter, 0)
            )
    return pd.DataFrame(
        event_rows,
        columns=[
            "trip_id",
            "vehicle_id",
            "geofence_id",
            "geofence_name",
            "geofence_type",
            "enter_time",
            "exit_time",
            "dwell_minutes",
        ],
    )


def _result():
    return run_lane_lab(_trips(), _visits())


def _baseline(lane_id: str) -> pd.Series:
    baselines = _result().lane_baselines
    return baselines[baselines["lane_id"] == lane_id].iloc[0]


def test_duration_calculation() -> None:
    duration = _result().trip_durations.set_index("trip_id").loc["LL-A-01"]
    assert duration["duration_minutes"] == 360
    assert bool(duration["is_usable"]) is True


def test_exact_trip_id_matching_is_preferred() -> None:
    duration = _result().trip_durations.set_index("trip_id").loc["LL-A-06"]
    assert duration["duration_minutes"] == 765


def test_vehicle_window_matching_when_trip_id_is_missing() -> None:
    duration = _result().trip_durations.set_index("trip_id").loc["LL-B-02"]
    assert duration["duration_minutes"] == 620


def test_lane_percentile_baseline_calculation() -> None:
    baseline = _baseline("RUH-DMM")
    assert baseline["usable_trip_count"] == 6
    assert baseline["p50_minutes"] == 375
    assert baseline["p75_minutes"] == 378.75
    assert baseline["p90_minutes"] == 572.5


def test_invalid_zero_or_negative_duration_is_excluded() -> None:
    baseline = _baseline("DXB-AUH")
    assert baseline["usable_trip_count"] == 0
    assert baseline["invalid_trip_count"] == 1
    assert baseline["confidence_bucket"] == "DATA MISSING"


def test_missing_destination_is_invalid_but_counted() -> None:
    baseline = _baseline("KWI-DOH")
    assert baseline["sample_size"] == 1
    assert baseline["invalid_trip_count"] == 1
    assert "0 usable trips" in baseline["evidence"]


def test_low_sample_confidence_bucket() -> None:
    baseline = _baseline("JED-RUH")
    assert baseline["usable_trip_count"] == 2
    assert baseline["confidence_bucket"] == "LOW SAMPLE"


def test_unstable_lane_and_outlier_detection() -> None:
    result = _result()
    baseline = result.lane_baselines[result.lane_baselines["lane_id"] == "RUH-DMM"].iloc[0]
    assert baseline["confidence_bucket"] == "UNSTABLE"
    assert baseline["outlier_count"] >= 1
    outlier = result.lane_outliers[result.lane_outliers["trip_id"] == "LL-A-06"].iloc[0]
    assert outlier["trip_id"] == "LL-A-06"
    assert outlier["outlier_type"] == "LONG DURATION"


def test_export_smoke(tmp_path: Path) -> None:
    baseline_path, outlier_path = write_outputs(_result(), tmp_path)
    assert baseline_path.exists()
    assert outlier_path.exists()
    assert list(pd.read_csv(baseline_path).columns) == BASELINE_COLUMNS
    assert list(pd.read_csv(outlier_path).columns) == OUTLIER_COLUMNS


def test_demo_data_smoke() -> None:
    base = Path("lane_lab/demo_data")
    result = run_lane_lab(
        pd.read_csv(base / "historical_trips.csv"),
        pd.read_csv(base / "historical_visit_events.csv"),
    )
    assert result.kpis["total_trips"] == 12
    assert list(result.lane_baselines.columns) == BASELINE_COLUMNS
    assert list(result.lane_outliers.columns) == OUTLIER_COLUMNS
    assert set(result.lane_baselines["confidence_bucket"]).issuperset(
        {"UNSTABLE", "LOW SAMPLE", "DATA MISSING"}
    )
    assert result.kpis["outlier_trips"] >= 1
