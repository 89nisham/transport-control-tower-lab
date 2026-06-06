"""Contract tests for TowerBrief daily management briefs."""

from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd

from tower_brief.engine import (
    BRIEF_COLUMNS,
    OWNER_BY_SOURCE,
    REQUIRED_MARKDOWN_SECTIONS,
    SOURCE_FILES,
    read_input_directory,
    run_tower_brief,
    write_outputs,
)
from tower_brief.models import TowerBriefSettings


DEMO_DIR = Path("tower_brief/demo_data")


def _settings() -> TowerBriefSettings:
    return TowerBriefSettings(brief_date="2026-06-06")


def _demo_result():
    return run_tower_brief(read_input_directory(DEMO_DIR), settings=_settings())


def _trips() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trip_id": "T-1",
                "vehicle_id": "V-1",
                "customer_name": "Demo Customer",
                "carrier_name": "Demo Carrier",
                "promised_arrival": "2026-06-06T10:00:00Z",
            }
        ]
    )


def test_source_file_normalization() -> None:
    result = run_tower_brief(
        {
            "trips.csv": _trips(),
            "delay_classification_report.csv": pd.DataFrame(
                [{"Trip ID": "T-1", "Primary Delay Reason": "Late Arrival", "Risk Bucket": "Critical"}]
            ),
        },
        settings=_settings(),
    )
    assert result.action_table.iloc[0]["trip_id"] == "T-1"
    assert result.action_table.iloc[0]["exception_type"] == "LATE ARRIVAL"


def test_action_row_generation_from_delay_lens() -> None:
    result = run_tower_brief(
        {
            "trips.csv": _trips(),
            "delay_classification_report.csv": pd.DataFrame(
                [{"trip_id": "T-1", "primary_delay_reason": "LATE ARRIVAL", "risk_bucket": "CRITICAL"}]
            ),
        },
        settings=_settings(),
    )
    row = result.action_table[result.action_table["source_product"] == "DelayLens"].iloc[0]
    assert row["priority"] == "CRITICAL"
    assert row["owner"] == "control_tower"


def test_action_row_generation_from_pod_pulse() -> None:
    result = run_tower_brief(
        {
            "trips.csv": _trips(),
            "pod_aging_report.csv": pd.DataFrame(
                [{"trip_id": "T-1", "pod_gap_type": "POD REJECTED", "risk_bucket": "HIGH", "invoice_blocked": True}]
            ),
        },
        settings=_settings(),
    )
    row = result.action_table[result.action_table["source_product"] == "PODPulse"].iloc[0]
    assert row["priority"] == "CRITICAL"
    assert row["owner"] == "documentation_or_billing"


def test_action_row_generation_from_detention_clock() -> None:
    result = run_tower_brief(
        {
            "trips.csv": _trips(),
            "detention_report.csv": pd.DataFrame(
                [{"trip_id": "T-1", "risk_bucket": "DETENTION", "estimated_charge": 1000}]
            ),
        },
        settings=_settings(),
    )
    row = result.action_table[result.action_table["source_product"] == "DetentionClock"].iloc[0]
    assert row["priority"] == "CRITICAL"
    assert row["financial_exposure"] == 1000


def test_action_row_generation_from_fuel_guard() -> None:
    result = run_tower_brief(
        {
            "fuel_exceptions.csv": pd.DataFrame(
                [{"fuel_event_id": "F-1", "vehicle_id": "V-1", "exception_type": "NO GPS EVIDENCE", "severity": "HIGH"}]
            )
        },
        settings=_settings(),
    )
    row = result.action_table[result.action_table["source_product"] == "FuelGuard"].iloc[0]
    assert row["priority"] == "CRITICAL"
    assert row["owner"] == "fleet_audit"


def test_action_row_generation_from_ban_window() -> None:
    result = run_tower_brief(
        {
            "trips.csv": _trips(),
            "ban_risk_board.csv": pd.DataFrame(
                [{"trip_id": "T-1", "risk_bucket": "BAN CONFLICT", "overlap_minutes": 120}]
            ),
        },
        settings=_settings(),
    )
    row = result.action_table[result.action_table["source_product"] == "BanWindow"].iloc[0]
    assert row["priority"] == "CRITICAL"
    assert row["owner"] == "planning"


def test_action_row_generation_from_carrier_score() -> None:
    result = run_tower_brief(
        {
            "carrier_scorecard.csv": pd.DataFrame(
                [{"carrier_name": "Demo Carrier", "risk_bucket": "AT RISK", "score": 55, "top_issue": "late trips"}]
            )
        },
        settings=_settings(),
    )
    row = result.action_table[result.action_table["source_product"] == "CarrierScore"].iloc[0]
    assert row["priority"] == "CRITICAL"
    assert row["owner"] == "transport_manager"


def test_priority_classification_critical() -> None:
    row = _demo_result().action_table.iloc[0]
    assert row["priority"] == "CRITICAL"


def test_priority_classification_high() -> None:
    result = run_tower_brief(
        {
            "trips.csv": _trips(),
            "gate_truth_report.csv": pd.DataFrame(
                [{"trip_id": "T-1", "gate_truth_status": "REVIEW", "exception_type": "MISSING DESTINATION ENTRY"}]
            ),
        },
        settings=_settings(),
    )
    assert result.action_table[result.action_table["source_product"] == "GateTruth"].iloc[0]["priority"] == "HIGH"


def test_priority_classification_data_gap() -> None:
    result = run_tower_brief({}, settings=_settings())
    assert "DATA GAP" in set(result.action_table["priority"])


def test_owner_assignment() -> None:
    result = _demo_result().action_table
    expected = set(OWNER_BY_SOURCE.values())
    assert expected.issubset(set(result["owner"]))


def test_financial_exposure_calculation() -> None:
    result = _demo_result()
    detention = result.action_table[result.action_table["source_product"] == "DetentionClock"]
    assert detention["financial_exposure"].sum() == 1900


def test_deduplication_within_same_source() -> None:
    delay_rows = _demo_result().action_table[
        (_demo_result().action_table["source_product"] == "DelayLens")
        & (_demo_result().action_table["trip_id"] == "TB-002")
    ]
    assert len(delay_rows) == 1
    assert "critical threshold" in delay_rows.iloc[0]["evidence"]


def test_no_deduplication_across_different_source_products() -> None:
    result = _demo_result().action_table
    tb002 = result[(result["trip_id"] == "TB-002") & (result["source_product"].isin(["ETA Watch", "DelayLens"]))]
    assert set(tb002["source_product"]) == {"ETA Watch", "DelayLens"}


def test_kpi_snapshot_calculation() -> None:
    kpis = dict(zip(_demo_result().kpi_snapshot["metric"], _demo_result().kpi_snapshot["value"], strict=True))
    assert kpis["critical_actions"] >= 6
    assert kpis["estimated_detention_exposure"] == 1900
    assert kpis["ban_conflicts"] == 1


def test_markdown_brief_generation() -> None:
    brief = _demo_result().brief_markdown
    for section in REQUIRED_MARKDOWN_SECTIONS:
        assert section in brief


def test_demo_customer_risks_section_includes_all_customer_rows() -> None:
    result = _demo_result()
    expected = result.action_table[
        (result.action_table["customer_name"] != "") & (result.action_table["source_product"] != "Trip Context")
    ]
    customer_risks = result.brief_markdown.split("## Customer Risks", 1)[1].split("## Carrier Watchlist", 1)[0]
    customer_bullets = [line for line in customer_risks.splitlines() if line.startswith("- ")]
    assert len(customer_bullets) == 14
    assert len(expected) == 14
    assert "HIGH | GateTruth | MISSING DESTINATION ENTRY" in customer_risks
    assert "customer: New Lane Pilot" in customer_risks
    assert "MEDIUM | BanWindow | VEHICLE CLASS UNKNOWN" in customer_risks
    assert "MEDIUM | ETA Watch | WATCH" in customer_risks
    assert "customer: Southern Parts" in customer_risks
    assert "MEDIUM | UpdatePulse | LATE UPDATE" in customer_risks
    assert "customer: Doha Retail" in customer_risks


def test_html_brief_generation_with_escaped_dynamic_text() -> None:
    result = run_tower_brief(
        {
            "fuel_exceptions.csv": pd.DataFrame(
                [
                    {
                        "fuel_event_id": "F-1",
                        "vehicle_id": "V-1",
                        "exception_type": "<script>alert(1)</script>",
                        "severity": "HIGH",
                    }
                ]
            )
        },
        settings=_settings(),
    )
    assert escape("<SCRIPT>ALERT(1)</SCRIPT>") in result.brief_html
    assert "<SCRIPT>ALERT(1)</SCRIPT>" not in result.brief_html


def test_csv_output_schema_contract() -> None:
    assert list(_demo_result().action_table.columns) == BRIEF_COLUMNS


def test_missing_optional_files_do_not_crash() -> None:
    result = run_tower_brief({"trips.csv": _trips()}, settings=_settings())
    assert result.source_status[result.source_status["status"] == "MISSING"].shape[0] == len(SOURCE_FILES) - 1


def test_demo_data_smoke() -> None:
    result = _demo_result()
    assert set(result.action_table["priority"]) == {"CRITICAL", "HIGH", "MEDIUM", "LOW", "DATA GAP"}
    assert len(result.action_table) >= 15
    assert not result.data_gaps.empty


def test_export_smoke(tmp_path: Path) -> None:
    markdown_path, html_path, csv_path = write_outputs(_demo_result(), tmp_path)
    exported = pd.read_csv(csv_path)
    assert markdown_path.read_text(encoding="utf-8").startswith("# Daily Control Tower Brief")
    assert "<html" in html_path.read_text(encoding="utf-8")
    assert list(exported.columns) == BRIEF_COLUMNS
