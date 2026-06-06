"""Unit tests for CarrierScore SLA scoring."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from carrier_score.engine import (
    CONFIDENCE_BUCKETS,
    EXCEPTION_SUMMARY_COLUMNS,
    RISK_BUCKETS,
    SCORECARD_COLUMNS,
    prepare_report,
    prepare_rules,
    prepare_trips,
    run_carrier_score,
    write_outputs,
)


DEMO_DIR = Path("carrier_score/demo_data")


def _demo(name: str) -> pd.DataFrame:
    return pd.read_csv(DEMO_DIR / name)


def _result():
    return run_carrier_score(
        _demo("trips.csv"),
        _demo("delay_classification_report.csv"),
        _demo("pod_aging_report.csv"),
        _demo("detention_report.csv"),
        _demo("update_discipline_report.csv"),
        _demo("fuel_exceptions.csv"),
        _demo("gate_truth_report.csv"),
        _demo("ban_risk_board.csv"),
        _demo("carrier_score_rules.csv"),
    )


def _carrier(name: str) -> pd.Series:
    return _result().carrier_scorecard.set_index("carrier_name").loc[name]


def test_prepare_trips_requires_trip_id_and_carrier_name() -> None:
    trips = prepare_trips(pd.DataFrame([{"Trip ID": "A1", "Carrier Name": "Demo Carrier"}]))
    assert trips.loc[0, "trip_id"] == "A1"
    assert trips.loc[0, "carrier_name"] == "Demo Carrier"


def test_prepare_trips_rejects_missing_required_columns() -> None:
    try:
        prepare_trips(pd.DataFrame([{"trip_id": "A1"}]))
    except ValueError as exc:
        assert "carrier_name" in str(exc)
    else:
        raise AssertionError("Expected missing carrier_name to fail")


def test_optional_delay_report_requires_declared_columns() -> None:
    try:
        prepare_report(pd.DataFrame([{"trip_id": "A1", "risk_bucket": "LATE"}]), "delay")
    except ValueError as exc:
        assert "primary_delay_reason" in str(exc)
    else:
        raise AssertionError("Expected missing delay column to fail")


def test_delay_minutes_can_create_late_trip_flag() -> None:
    report = prepare_report(
        pd.DataFrame(
            [
                {
                    "trip_id": "A1",
                    "primary_delay_reason": "late arrival",
                    "risk_bucket": "ON TRACK",
                    "arrival_delay_minutes": 30,
                }
            ]
        ),
        "delay",
    )
    assert bool(report.loc[0, "is_exception"])
    assert report.loc[0, "severity_score"] == 1


def test_rules_are_normalized_to_one() -> None:
    weights = prepare_rules(
        pd.DataFrame(
            [
                {"metric": "late_trip_rate", "weight": 2},
                {"metric": "missing_pod_rate", "weight": 1},
                {"metric": "unknown_metric", "weight": 99},
            ]
        )
    )
    assert round(sum(weights.values()), 6) == 1
    assert round(weights["late_trip_rate"], 4) == 0.6667


def test_scorecard_schema_is_exact() -> None:
    assert list(_result().carrier_scorecard.columns) == SCORECARD_COLUMNS


def test_exception_summary_schema_is_exact() -> None:
    assert list(_result().carrier_exception_summary.columns) == EXCEPTION_SUMMARY_COLUMNS


def test_all_risk_buckets_are_supported() -> None:
    assert {"STRONG", "STABLE", "WATCHLIST", "NEEDS REVIEW", "DATA GAP"} == RISK_BUCKETS


def test_all_confidence_buckets_are_supported() -> None:
    assert {"HIGH", "MEDIUM", "LOW", "DATA GAP"} == CONFIDENCE_BUCKETS


def test_multi_source_carrier_gets_needs_review_score() -> None:
    gulf = _carrier("Gulf Bridge")
    assert gulf["total_trips"] == 5
    assert gulf["late_trip_count"] == 3
    assert gulf["missing_pod_count"] == 2
    assert gulf["risk_bucket"] == "NEEDS REVIEW"
    assert gulf["confidence_bucket"] == "HIGH"
    assert gulf["top_issue"] == "Delay performance"


def test_clean_carrier_gets_strong_score() -> None:
    north = _carrier("North Star Logistics")
    assert north["risk_bucket"] == "STRONG"
    assert north["sla_score"] == 100
    assert north["exception_count"] == 0


def test_single_trip_carrier_has_low_confidence() -> None:
    one_trip = _carrier("One Trip Express")
    assert one_trip["confidence_bucket"] == "LOW"
    assert one_trip["exception_rate"] == 1


def test_missing_optional_sources_create_data_gap_confidence() -> None:
    result = run_carrier_score(pd.DataFrame([{"trip_id": "A1", "carrier_name": "Demo Carrier"}]))
    row = result.carrier_scorecard.iloc[0]
    assert row["risk_bucket"] == "DATA GAP"
    assert row["confidence_bucket"] == "DATA GAP"


def test_optional_report_carrier_name_falls_back_to_trips() -> None:
    result = run_carrier_score(
        pd.DataFrame([{"trip_id": "A1", "carrier_name": "Fallback Carrier"}]),
        delay_df=pd.DataFrame(
            [
                {
                    "trip_id": "A1",
                    "primary_delay_reason": "late arrival",
                    "risk_bucket": "LATE",
                    "arrival_delay_minutes": 90,
                }
            ]
        ),
    )
    row = result.carrier_scorecard.iloc[0]
    assert row["carrier_name"] == "Fallback Carrier"
    assert row["late_trip_count"] == 1


def test_summary_includes_neutral_exception_area() -> None:
    summary = _result().carrier_exception_summary
    gulf_summary = summary[summary["carrier_name"] == "Gulf Bridge"]
    assert "Delay performance" in set(gulf_summary["exception_area"])
    assert not gulf_summary["suggested_action"].str.contains("penalty|claim|invoice", case=False).any()


def test_write_outputs_creates_both_csvs(tmp_path: Path) -> None:
    scorecard_path, summary_path = write_outputs(_result(), tmp_path)
    assert scorecard_path.name == "carrier_scorecard.csv"
    assert summary_path.name == "carrier_exception_summary.csv"
    assert scorecard_path.exists()
    assert summary_path.exists()
