"""Unit tests for LaneLab lane baseline generation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from lane_lab.engine import (
    BASELINE_COLUMNS,
    CONFIDENCE_BUCKETS,
    OUTLIER_COLUMNS,
    run_lane_lab,
    write_outputs,
)


def _trip(
    trip_id: str,
    vehicle_id: str,
    lane_id: str,
    customer: str,
    carrier: str,
    origin: str = "Riyadh Dry Port",
    destination: str = "Dammam DC",
) -> tuple[str, str, str, str, str, str, str, str, str]:
    return (
        trip_id,
        vehicle_id,
        lane_id,
        customer,
        carrier,
        origin,
        destination,
        "2026-05-01T06:00:00+03:00",
        "2026-05-01T20:00:00+03:00",
    )


def _visits_for_duration(
    trip_id: str | None,
    vehicle_id: str,
    origin_exit: str | None,
    destination_enter: str | None,
    origin_name: str = "Riyadh Dry Port",
    destination_name: str = "Dammam DC",
) -> list[tuple[str | None, str, str, str, str, str | None, str | None, int]]:
    rows = []
    if origin_exit is not None:
        rows.append(
            (
                trip_id,
                vehicle_id,
                f"GF-{vehicle_id}-O",
                origin_name,
                "ORIGIN",
                "2026-05-01T06:00:00+03:00",
                origin_exit,
                30,
            )
        )
    if destination_enter is not None:
        rows.append(
            (
                trip_id,
                vehicle_id,
                f"GF-{vehicle_id}-D",
                destination_name,
                "DESTINATION",
                destination_enter,
                destination_enter,
                0,
            )
        )
    return rows


def _trips() -> pd.DataFrame:
    rows = [
        *[
            _trip(f"GOOD-{i}", f"VH-G{i}", "RUH-DMM", "Gulf Fresh Foods", "Gulf Bridge")
            for i in range(1, 6)
        ],
        _trip("LOW-1", "VH-L1", "JED-RUH", "Red Sea Pharma", "Hejaz Line", "Jeddah Port", "Riyadh DC"),
        _trip("LOW-2", "VH-L2", "JED-RUH", "Red Sea Pharma", "Hejaz Line", "Jeddah Port", "Riyadh DC"),
        *[
            _trip(f"UNSTABLE-{i}", f"VH-U{i}", "DOH-MCT", "GCC Electronics", "Gulf Bridge", "Doha Hub", "Muscat DC")
            for i in range(1, 6)
        ],
        *[
            _trip(f"OUT-{i}", f"VH-O{i}", "DXB-AUH", "Emirates Home", "Desert Falcon", "Dubai JAFZA", "Abu Dhabi Store")
            for i in range(1, 6)
        ],
        _trip("MISS-ORIGIN", "VH-MO", "KWI-DOH", "Kuwait Retail", "Peninsula Freight", "Kuwait DC", "Doha Retail Hub"),
        _trip("MISS-DEST", "VH-MD", "KWI-DOH", "Kuwait Retail", "Peninsula Freight", "Kuwait DC", "Doha Retail Hub"),
        _trip("CHECK-VALID", "VH-CV", "KWI-DOH", "Kuwait Retail", "Peninsula Freight", "Kuwait DC", "Doha Retail Hub"),
        _trip("NEGATIVE", "VH-NG", "BAH-DMM", "Saudi Parts", "Causeway Logistics", "Bahrain Hub", "Dammam DC"),
        _trip("NO-BASE", "VH-NB", "MED-TAB", "Arabian Retail", "Northwest Freight", "Medina DC", "Tabuk Store"),
    ]
    return pd.DataFrame(
        rows,
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
    rows = []
    for i, minutes in enumerate([360, 365, 370, 375, 380], start=1):
        rows += _visits_for_duration(
            f"GOOD-{i}",
            f"VH-G{i}",
            "2026-05-01T07:00:00+03:00",
            pd.Timestamp("2026-05-01T07:00:00+03:00")
            + pd.Timedelta(minutes=minutes),
        )
    for i, minutes in enumerate([600, 620], start=1):
        rows += _visits_for_duration(
            None if i == 2 else f"LOW-{i}",
            f"VH-L{i}",
            "2026-05-01T09:00:00+03:00",
            pd.Timestamp("2026-05-01T09:00:00+03:00")
            + pd.Timedelta(minutes=minutes),
            "Jeddah Port",
            "Riyadh DC",
        )
    for i, minutes in enumerate([300, 310, 320, 330, 900], start=1):
        rows += _visits_for_duration(
            f"UNSTABLE-{i}",
            f"VH-U{i}",
            "2026-05-01T08:00:00+03:00",
            pd.Timestamp("2026-05-01T08:00:00+03:00")
            + pd.Timedelta(minutes=minutes),
            "Doha Hub",
            "Muscat DC",
        )
    for i, minutes in enumerate([120, 122, 124, 126, 600], start=1):
        rows += _visits_for_duration(
            f"OUT-{i}",
            f"VH-O{i}",
            "2026-05-01T09:00:00+04:00",
            pd.Timestamp("2026-05-01T09:00:00+04:00")
            + pd.Timedelta(minutes=minutes),
            "Dubai JAFZA",
            "Abu Dhabi Store",
        )
    rows += _visits_for_duration(
        "MISS-ORIGIN",
        "VH-MO",
        None,
        "2026-05-01T16:00:00+03:00",
        "Kuwait DC",
        "Doha Retail Hub",
    )
    rows += _visits_for_duration(
        "MISS-DEST",
        "VH-MD",
        "2026-05-01T07:00:00+03:00",
        None,
        "Kuwait DC",
        "Doha Retail Hub",
    )
    rows += _visits_for_duration(
        "CHECK-VALID",
        "VH-CV",
        "2026-05-01T07:00:00+03:00",
        "2026-05-01T16:00:00+03:00",
        "Kuwait DC",
        "Doha Retail Hub",
    )
    rows += _visits_for_duration(
        "NEGATIVE",
        "VH-NG",
        "2026-05-01T15:00:00+03:00",
        "2026-05-01T14:00:00+03:00",
        "Bahrain Hub",
        "Dammam DC",
    )
    return pd.DataFrame(
        rows,
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


def _duration(trip_id: str) -> pd.Series:
    return _result().trip_durations.set_index("trip_id").loc[trip_id]


def _baseline(lane_id: str) -> pd.Series:
    baselines = _result().lane_baselines
    return baselines[baselines["lane_id"] == lane_id].iloc[0]


def test_origin_exit_detection() -> None:
    assert str(_duration("GOOD-1")["actual_origin_exit"]) == "2026-05-01 04:00:00+00:00"


def test_destination_entry_detection() -> None:
    assert str(_duration("GOOD-1")["actual_destination_entry"]) == "2026-05-01 10:00:00+00:00"


def test_duration_calculation() -> None:
    assert _duration("GOOD-1")["duration_minutes"] == 360


def test_negative_duration_exclusion() -> None:
    duration = _duration("NEGATIVE")
    assert bool(duration["is_usable"]) is False
    assert duration["invalid_reason"] == "zero or negative duration"


def test_missing_origin_destination_invalid_handling() -> None:
    assert _duration("MISS-ORIGIN")["invalid_reason"] == "missing origin event"
    assert _duration("MISS-DEST")["invalid_reason"] == "missing destination event"
    assert _baseline("KWI-DOH")["confidence_bucket"] == "CHECK DATA"


def test_percentile_calculation() -> None:
    baseline = _baseline("RUH-DMM")
    assert baseline["p50_minutes"] == 370
    assert baseline["p75_minutes"] == 375
    assert baseline["p90_minutes"] == 378
    assert baseline["confidence_bucket"] == "GOOD"


def test_low_sample_bucket() -> None:
    baseline = _baseline("JED-RUH")
    assert baseline["usable_trip_count"] == 2
    assert baseline["confidence_bucket"] == "LOW SAMPLE"


def test_unstable_lane_bucket_by_p90_p50_ratio() -> None:
    baseline = _baseline("DOH-MCT")
    assert baseline["p90_minutes"] / baseline["p50_minutes"] > 1.5
    assert baseline["confidence_bucket"] == "UNSTABLE"


def test_iqr_outlier_detection() -> None:
    result = _result()
    outlier = result.lane_outliers[result.lane_outliers["trip_id"] == "OUT-5"].iloc[0]
    assert outlier["outlier_type"] == "LONG DURATION"
    assert _baseline("DXB-AUH")["outlier_count"] == 1


def test_no_baseline_bucket() -> None:
    assert _baseline("MED-TAB")["confidence_bucket"] == "NO BASELINE"


def test_customer_carrier_grouping() -> None:
    row = _baseline("RUH-DMM")
    assert row["customer_name"] == "Gulf Fresh Foods"
    assert row["carrier_name"] == "Gulf Bridge"


def test_output_schema_contract() -> None:
    result = _result()
    assert list(result.lane_baselines.columns) == BASELINE_COLUMNS
    assert list(result.lane_outliers.columns) == OUTLIER_COLUMNS
    assert set(result.lane_baselines["confidence_bucket"]).issubset(CONFIDENCE_BUCKETS)


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
    assert list(result.lane_baselines.columns) == BASELINE_COLUMNS
    assert list(result.lane_outliers.columns) == OUTLIER_COLUMNS
    assert set(result.lane_baselines["confidence_bucket"]) == CONFIDENCE_BUCKETS
    assert result.kpis["total_lanes"] >= 7
    assert result.kpis["outlier_trips"] >= 2
