"""Unit tests for PODPulse POD aging classification."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pod_pulse.engine import (
    ACCEPTED_INVOICE_STATUSES,
    ACCEPTED_POD_STATUSES,
    OVERDUE_COLUMNS,
    REPORT_COLUMNS,
    _age_bucket,
    run_pod_pulse,
    write_outputs,
)


REVIEW_TIME = "2026-06-10T12:00:00Z"


def _deliveries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("PP-OK", "Gulf Fresh Foods", "2026-06-09T09:00:00+03:00", "VH-P01"),
            ("PP-MISSING-WARN", "Arabian Retail Group", "2026-06-10T09:00:00+03:00", "VH-P02"),
            ("PP-OVERDUE", "Red Sea Pharma", "2026-06-07T08:00:00+03:00", "VH-P03"),
            ("PP-CRITICAL", "Saudi Parts Co", "2026-06-01T07:00:00+03:00", "VH-P04"),
            ("PP-REJECTED", "GCC Electronics", "2026-06-07T12:00:00+03:00", "VH-P05"),
            ("PP-RESUBMITTED", "Qatar Cold Chain", "2026-06-09T18:00:00+03:00", "VH-P06"),
            ("PP-LATE", "Red Sea Pharma", "2026-06-06T10:00:00+03:00", "VH-P07"),
            ("PP-INVOICE-BLOCKED", "Emirates Home Supply", "2026-06-09T16:00:00+04:00", "VH-P08"),
            ("PP-NOT-DELIVERED", "Kuwait Retail Hub", None, "VH-P09"),
            ("PP-DATA-MISSING", None, "2026-06-09T11:00:00+03:00", "VH-P10"),
        ],
        columns=["trip_id", "customer_name", "delivered_time", "vehicle_id"],
    ).assign(
        carrier_name="Gulf Bridge Freight",
        origin="Origin DC",
        destination="Destination Store",
        promised_arrival="2026-06-10T10:00:00Z",
    )


def _pods() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("PP-OK", "APPROVED", "2026-06-09T14:00:00+03:00", None, None, "billing", "2026-06-09T16:00:00+03:00", None),
            ("PP-MISSING-WARN", "MISSING", None, None, None, None, None, None),
            ("PP-OVERDUE", "MISSING", None, None, None, None, None, None),
            ("PP-CRITICAL", "MISSING", None, None, None, None, None, None),
            ("PP-REJECTED", "REJECTED", "2026-06-07T18:00:00+03:00", "2026-06-08T09:00:00+03:00", "Stamp missing", "portal", None, None),
            ("PP-RESUBMITTED", "RESUBMITTED", "2026-06-10T09:00:00+03:00", "2026-06-10T10:00:00+03:00", "Name mismatch", "portal", None, "2026-06-10T11:00:00+03:00"),
            ("PP-LATE", "RECEIVED", "2026-06-09T15:00:00+03:00", None, None, "portal", None, None),
            ("PP-INVOICE-BLOCKED", "RECEIVED", "2026-06-09T20:00:00+04:00", None, None, "billing", None, None),
            ("PP-NOT-DELIVERED", "MISSING", None, None, None, None, None, None),
            ("PP-DATA-MISSING", "APPROVED", "2026-06-09T14:00:00+03:00", None, None, "billing", "2026-06-09T16:00:00+03:00", None),
        ],
        columns=[
            "trip_id",
            "pod_status",
            "pod_received_time",
            "pod_rejected_time",
            "rejection_reason",
            "uploaded_by",
            "approved_time",
            "resubmitted_time",
        ],
    )


def _invoices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("PP-OK", "READY", "INV-1", None),
            ("PP-MISSING-WARN", "READY", None, None),
            ("PP-OVERDUE", "NOT READY", None, None),
            ("PP-CRITICAL", "NOT READY", None, None),
            ("PP-REJECTED", "BLOCKED", None, "Rejected POD needs corrected document"),
            ("PP-RESUBMITTED", "READY", None, None),
            ("PP-LATE", "READY", "INV-7", None),
            ("PP-INVOICE-BLOCKED", "NOT READY", None, "POD approval pending before invoice release"),
            ("PP-NOT-DELIVERED", "NOT READY", None, None),
            ("PP-DATA-MISSING", "READY", "INV-10", None),
        ],
        columns=["trip_id", "invoice_status", "invoice_no", "blocked_reason"],
    )


def _result():
    return run_pod_pulse(_deliveries(), _pods(), _invoices(), review_time=REVIEW_TIME)


def _report() -> pd.DataFrame:
    return _result().pod_aging_report


def _row(report: pd.DataFrame, trip_id: str) -> pd.Series:
    return report[report["trip_id"] == trip_id].iloc[0]


def test_pod_age_calculation() -> None:
    row = _row(_report(), "PP-OK")
    assert row["pod_age_hours"] == 5
    assert row["pod_age_days"] == 0.21


def test_aging_bucket_classification() -> None:
    report = _report()
    assert _row(report, "PP-OK")["aging_bucket"] == "0-24H"
    assert _row(report, "PP-OVERDUE")["aging_bucket"] == "72H+"
    assert _row(report, "PP-CRITICAL")["aging_bucket"] == "7D+"
    assert _age_bucket(36) == "24-48H"
    assert _age_bucket(60) == "48-72H"


def test_missing_pod_detection() -> None:
    row = _row(_report(), "PP-MISSING-WARN")
    assert row["pod_gap_type"] == "POD MISSING"
    assert row["severity"] == "MEDIUM"


def test_overdue_pod_detection() -> None:
    row = _row(_report(), "PP-OVERDUE")
    assert row["pod_gap_type"] == "POD OVERDUE"
    assert row["severity"] == "HIGH"


def test_critical_missing_pod_detection() -> None:
    row = _row(_report(), "PP-CRITICAL")
    assert row["pod_gap_type"] == "POD OVERDUE"
    assert row["aging_bucket"] == "7D+"
    assert row["severity"] == "CRITICAL"


def test_rejected_pod_detection() -> None:
    row = _row(_report(), "PP-REJECTED")
    assert row["pod_gap_type"] == "POD REJECTED"
    assert row["severity"] == "CRITICAL"
    assert "Stamp missing" in row["evidence"]


def test_resubmitted_pending_approval_detection() -> None:
    row = _row(_report(), "PP-RESUBMITTED")
    assert row["pod_gap_type"] == "POD RESUBMITTED"
    assert row["risk_bucket"] == "REVIEW"


def test_late_received_pod_detection() -> None:
    row = _row(_report(), "PP-LATE")
    assert row["pod_gap_type"] == "POD LATE"
    assert row["pod_age_hours"] == 77


def test_invoice_blocked_detection() -> None:
    row = _row(_report(), "PP-INVOICE-BLOCKED")
    assert row["pod_gap_type"] == "INVOICE BLOCKED"
    assert bool(row["invoice_blocked"]) is True


def test_not_delivered_classification() -> None:
    row = _row(_report(), "PP-NOT-DELIVERED")
    assert row["pod_gap_type"] == "NOT DELIVERED"
    assert row["risk_bucket"] == "DATA MISSING"


def test_data_missing_classification() -> None:
    row = _row(_report(), "PP-DATA-MISSING")
    assert row["pod_gap_type"] == "DATA MISSING"
    assert row["risk_bucket"] == "DATA MISSING"


def test_risk_bucket_classification() -> None:
    report = _report()
    assert set(report["risk_bucket"]).issuperset(
        {"OK", "WATCH", "REVIEW", "HIGH RISK", "DATA MISSING"}
    )


def test_export_smoke(tmp_path: Path) -> None:
    result = _result()
    report_path, overdue_path = write_outputs(result, tmp_path)
    assert report_path.exists()
    assert overdue_path.exists()
    assert list(pd.read_csv(report_path).columns) == REPORT_COLUMNS
    assert list(pd.read_csv(overdue_path).columns) == OVERDUE_COLUMNS


def test_demo_data_smoke() -> None:
    base = Path("pod_pulse/demo_data")
    result = run_pod_pulse(
        pd.read_csv(base / "deliveries.csv"),
        pd.read_csv(base / "pod_status.csv"),
        pd.read_csv(base / "invoice_status.csv"),
        review_time=REVIEW_TIME,
    )
    assert result.kpis["total_deliveries"] == 10
    assert list(result.pod_aging_report.columns) == REPORT_COLUMNS
    assert list(result.overdue_pods.columns) == OVERDUE_COLUMNS
    assert set(pd.read_csv(base / "pod_status.csv")["pod_status"]) == ACCEPTED_POD_STATUSES - {"NOT_REQUIRED"}
    assert set(pd.read_csv(base / "invoice_status.csv")["invoice_status"]).issubset(
        ACCEPTED_INVOICE_STATUSES
    )
    assert set(result.pod_aging_report["pod_gap_type"]).issuperset(
        {
            "OK",
            "POD MISSING",
            "POD OVERDUE",
            "POD REJECTED",
            "POD RESUBMITTED",
            "POD LATE",
            "INVOICE BLOCKED",
            "NOT DELIVERED",
            "DATA MISSING",
        }
    )
