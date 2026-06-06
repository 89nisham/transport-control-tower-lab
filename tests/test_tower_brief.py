"""Contract tests for TowerBrief daily management briefs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from tower_brief.engine import ACTION_COLUMNS, SOURCE_FILES, read_input_directory, run_tower_brief, write_outputs


DEMO_DIR = Path("tower_brief/demo_data")


def _demo_result():
    return run_tower_brief(read_input_directory(DEMO_DIR))


def test_demo_builds_daily_action_table() -> None:
    result = _demo_result()
    assert list(result.action_table.columns) == ACTION_COLUMNS
    assert len(result.action_table) >= 8
    assert result.action_table.iloc[0]["priority_bucket"] == "P1"


def test_all_source_files_are_optional() -> None:
    result = run_tower_brief({})
    assert result.action_table.empty
    assert set(result.source_status["status"]) == {"MISSING"}


def test_missing_files_are_reported_in_source_coverage() -> None:
    result = run_tower_brief({"trips.csv": pd.read_csv(DEMO_DIR / "trips.csv")})
    missing = result.source_status[result.source_status["status"] == "MISSING"]
    assert len(missing) == len(SOURCE_FILES) - 1


def test_missing_required_columns_become_config_warning() -> None:
    result = run_tower_brief({"fuel_exceptions.csv": pd.DataFrame([{"trip_id": "TB-001"}])})
    assert result.config_warnings == [
        "fuel_exceptions.csv DATA MISSING: missing required columns: exception_type, fuel_event_id, vehicle_id"
    ]
    assert result.source_status.set_index("source_file").loc["fuel_exceptions.csv", "status"] == "DATA MISSING"


def test_trip_context_fills_customer_and_carrier() -> None:
    result = run_tower_brief(
        {
            "trips.csv": pd.read_csv(DEMO_DIR / "trips.csv"),
            "delay_classification_report.csv": pd.DataFrame(
                [{"trip_id": "TB-002", "primary_delay_reason": "LATE ARRIVAL", "risk_bucket": "CRITICAL"}]
            ),
        }
    )
    row = result.action_table.iloc[0]
    assert row["customer_name"] == "Gulf Foods"
    assert row["carrier_name"] == "Red Sea Haulage"


def test_priority_sorts_critical_before_high() -> None:
    result = _demo_result()
    scores = result.action_table["severity"].tolist()
    assert scores.index("CRITICAL") < scores.index("HIGH")


def test_owner_mapping_routes_billing_and_dispatch_work() -> None:
    result = _demo_result().action_table
    owners = set(result["owner"])
    assert "Billing Review" in owners
    assert "Dispatch Lead" in owners


def test_kpi_snapshot_counts_exposure() -> None:
    kpis = dict(zip(_demo_result().kpi_snapshot["metric"], _demo_result().kpi_snapshot["value"], strict=True))
    assert kpis["total_trips"] == 8
    assert kpis["open_actions"] >= 8
    assert kpis["financial_exposure"] >= 900


def test_brief_sections_are_deterministic() -> None:
    brief = _demo_result().brief_markdown
    assert "# Daily Control Tower Brief" in brief
    assert "## Executive Snapshot" in brief
    assert "## Top Actions" in brief
    assert "No open exceptions" not in brief


def test_export_smoke(tmp_path: Path) -> None:
    markdown_path, html_path, csv_path = write_outputs(_demo_result(), tmp_path)
    exported = pd.read_csv(csv_path)
    assert markdown_path.read_text(encoding="utf-8").startswith("# Daily Control Tower Brief")
    assert "<html" in html_path.read_text(encoding="utf-8")
    assert list(exported.columns) == ACTION_COLUMNS
