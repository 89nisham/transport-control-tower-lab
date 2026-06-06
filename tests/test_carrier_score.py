"""Contract tests for CarrierScore SLA scoring."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from carrier_score.engine import (
    CONFIDENCE_BUCKETS,
    EXCEPTION_SUMMARY_COLUMNS,
    RISK_BUCKETS,
    SCORECARD_COLUMNS,
    prepare_rules,
    run_carrier_score,
    write_outputs,
)


DEMO_DIR = Path("carrier_score/demo_data")


def _demo(name: str) -> pd.DataFrame:
    return pd.read_csv(DEMO_DIR / name)


def _demo_result():
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
    return _demo_result().carrier_scorecard.set_index("carrier_name").loc[name]


def _trips(count: int = 4, carrier: str = "Test Carrier") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trip_id": f"T-{idx}",
                "carrier_name": carrier,
                "customer_name": "Demo Customer",
                "origin": "Riyadh",
                "destination": "Dammam",
                "lane_id": "RUH-DMM",
                "promised_arrival": "2026-06-01T10:00:00Z",
                "delivered_time": "2026-06-01T09:50:00Z",
            }
            for idx in range(1, count + 1)
        ]
    )


def test_score_starts_at_100_and_applies_weighted_penalties() -> None:
    delay = pd.DataFrame(
        [
            {"trip_id": "T-1", "primary_delay_reason": "LATE ARRIVAL", "risk_bucket": "DELAYED"},
            {"trip_id": "T-2", "primary_delay_reason": "ON TIME", "risk_bucket": "ON TIME"},
        ]
    )
    row = run_carrier_score(_trips(), delay_df=delay).carrier_scorecard.iloc[0]
    assert row["late_trip_rate"] == 0.25
    assert row["score_penalty"] == 5
    assert row["score"] == 95


def test_configurable_scoring_rules_override_defaults() -> None:
    delay = pd.DataFrame([{"trip_id": "T-1", "primary_delay_reason": "LATE ARRIVAL", "risk_bucket": "DELAYED"}])
    rules = pd.DataFrame(
        [
            {
                "metric_name": "late_trip_rate",
                "weight": 100,
                "direction": "lower_is_better",
                "enabled": "yes",
                "good_threshold": 0,
                "bad_threshold": 1,
            }
        ]
    )
    row = run_carrier_score(_trips(), delay_df=delay, rules_df=rules).carrier_scorecard.iloc[0]
    assert row["score"] == 71.25


def test_lower_is_better_metric_penalty() -> None:
    rules, warnings = prepare_rules(
        pd.DataFrame(
            [
                {
                    "metric_name": "fuel_exception_rate",
                    "weight": 10,
                    "direction": "lower_is_better",
                    "enabled": "true",
                    "good_threshold": 0,
                    "bad_threshold": 1,
                }
            ]
        )
    )
    assert warnings == []
    assert rules["fuel_exception_rate"]["direction"] == "lower_is_better"


def test_higher_is_better_metric_penalty() -> None:
    row = run_carrier_score(_trips()).carrier_scorecard.iloc[0]
    assert row["data_completeness_rate"] == 0
    assert row["score_penalty"] == 5


def test_risk_bucket_classification() -> None:
    assert RISK_BUCKETS == {"EXCELLENT", "GOOD", "WATCH", "AT RISK", "INSUFFICIENT DATA"}
    demo = _demo_result().carrier_scorecard.set_index("carrier_name")
    assert demo.loc["Atlas Roadlink", "risk_bucket"] == "EXCELLENT"
    assert demo.loc["Cedar Freight", "risk_bucket"] == "EXCELLENT"
    assert demo.loc["Peninsula Cargo", "risk_bucket"] == "AT RISK"
    assert demo.loc["New Route Pilot", "risk_bucket"] == "INSUFFICIENT DATA"


def test_confidence_bucket_classification() -> None:
    assert CONFIDENCE_BUCKETS == {"HIGH", "MEDIUM", "LOW SAMPLE", "DATA LIMITED", "DATA MISSING"}
    demo = _demo_result().carrier_scorecard.set_index("carrier_name")
    assert demo.loc["Atlas Roadlink", "confidence_bucket"] == "HIGH"
    assert demo.loc["Cedar Freight", "confidence_bucket"] == "MEDIUM"
    assert demo.loc["New Route Pilot", "confidence_bucket"] == "LOW SAMPLE"


def test_insufficient_data_classification() -> None:
    row = run_carrier_score(pd.DataFrame([{"trip_id": "T-1", "carrier_name": "Tiny Carrier"}])).carrier_scorecard.iloc[0]
    assert row["risk_bucket"] == "INSUFFICIENT DATA"
    assert row["confidence_bucket"] == "DATA LIMITED"


def test_missing_optional_files_do_not_crash() -> None:
    result = run_carrier_score(_trips())
    assert len(result.carrier_scorecard) == 1
    assert result.carrier_exception_summary.empty


def test_delay_metrics_join_by_trip_id() -> None:
    row = _carrier("Red Sea Haulage")
    assert row["late_trip_rate"] == 0.8
    assert row["top_issue"] == "late trips"


def test_pod_metrics_join_by_trip_id() -> None:
    row = _carrier("Peninsula Cargo")
    assert row["missing_pod_rate"] == 1
    assert row["overdue_pod_rate"] == 1


def test_detention_exposure_calculation() -> None:
    row = _carrier("Dock Time Logistics")
    assert row["detention_case_rate"] == 0.6667
    assert row["estimated_detention_exposure"] == 1100


def test_update_exception_rate_calculation() -> None:
    row = _carrier("Signal Gap Transport")
    assert row["update_exception_rate"] == 1


def test_fuel_exception_rate_calculation() -> None:
    row = _carrier("Fuel Review Fleet")
    assert row["fuel_exception_rate"] == 1
    assert row["total_fuel_exception_liters"] == 395


def test_gate_exception_rate_calculation() -> None:
    row = _carrier("New Route Pilot")
    assert row["gate_exception_rate"] == 0.5


def test_ban_conflict_rate_calculation() -> None:
    row = _carrier("City Window Movers")
    assert row["ban_conflict_rate"] == 0.6667


def test_invoice_blocker_rate_calculation() -> None:
    row = _carrier("Invoice Hold Express")
    assert row["invoice_blocker_rate"] == 0.6667


def test_top_issue_selection() -> None:
    assert _carrier("Fuel Review Fleet")["top_issue"] == "fuel exceptions"
    assert _carrier("Atlas Roadlink")["top_issue"] == "No dominant issue"


def test_output_schema_contract() -> None:
    result = _demo_result()
    assert list(result.carrier_scorecard.columns) == SCORECARD_COLUMNS
    assert list(result.carrier_exception_summary.columns) == EXCEPTION_SUMMARY_COLUMNS


def test_export_smoke(tmp_path: Path) -> None:
    scorecard_path, summary_path = write_outputs(_demo_result(), tmp_path)
    scorecard = pd.read_csv(scorecard_path)
    summary = pd.read_csv(summary_path)
    assert list(scorecard.columns) == SCORECARD_COLUMNS
    assert list(summary.columns) == EXCEPTION_SUMMARY_COLUMNS


def test_demo_data_smoke() -> None:
    result = _demo_result()
    scorecard = result.carrier_scorecard
    assert len(scorecard) == 10
    assert result.kpis["total_trips"] == 42
    assert {"EXCELLENT", "GOOD", "AT RISK", "INSUFFICIENT DATA"}.issubset(set(scorecard["risk_bucket"]))
    assert not result.carrier_exception_summary.empty
