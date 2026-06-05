"""Unit tests for PODPulse POD aging classification."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pod_pulse.engine import run_pod_pulse, write_outputs


REVIEW_TIME = "2026-06-10T12:00:00Z"


def _deliveries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("PP-OK", "Gulf Fresh Foods", "2026-06-09T09:00:00+03:00", "VH-P01"),
            ("PP-MISSING", "Arabian Retail Group", "2026-06-08T08:00:00+03:00", "VH-P02"),
            ("PP-LATE", "Red Sea Pharma", "2026-06-06T10:00:00+03:00", "VH-P03"),
            ("PP-REJECTED", "GCC Electronics", "2026-06-07T12:00:00+03:00", "VH-P04"),
            ("PP-BLOCKED", "Emirates Home Supply", "2026-06-09T16:00:00+04:00", "VH-P05"),
            ("PP-PENDING", "Qatar Cold Chain", "2026-06-09T18:00:00+03:00", "VH-P06"),
            ("PP-CRITICAL", "Saudi Parts Co", "2026-06-01T07:00:00+03:00", "VH-P07"),
            ("PP-NOT-REQ", "Oman Project Cargo", "2026-06-09T13:00:00+04:00", "VH-P08"),
            ("PP-NOT-DELIVERED", "Kuwait Retail Hub", None, "VH-P09"),
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
            ("PP-MISSING", "MISSING", None, None, None, None, None, None),
            ("PP-LATE", "RECEIVED", "2026-06-09T15:00:00+03:00", None, None, "portal", None, None),
            ("PP-REJECTED", "REJECTED", "2026-06-07T18:00:00+03:00", "2026-06-08T09:00:00+03:00", "Stamp missing", "portal", None, None),
            ("PP-BLOCKED", "APPROVED", "2026-06-09T20:00:00+04:00", None, None, "billing", "2026-06-10T08:00:00+04:00", None),
            ("PP-PENDING", "RESUBMITTED", "2026-06-10T09:00:00+03:00", "2026-06-10T10:00:00+03:00", "Name mismatch", "portal", None, "2026-06-10T11:00:00+03:00"),
            ("PP-CRITICAL", "MISSING", None, None, None, None, None, None),
            ("PP-NOT-REQ", "NOT_REQUIRED", None, None, None, None, None, None),
            ("PP-NOT-DELIVERED", "MISSING", None, None, None, None, None, None),
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
            ("PP-MISSING", "NOT READY", None, None),
            ("PP-LATE", "READY", "INV-3", None),
            ("PP-REJECTED", "BLOCKED", None, "Rejected POD needs corrected document"),
            ("PP-BLOCKED", "BLOCKED", "INV-5", "Customer PO mismatch"),
            ("PP-PENDING", "NOT READY", None, "Approval pending"),
            ("PP-CRITICAL", "NOT READY", None, None),
            ("PP-NOT-REQ", "INVOICED", "INV-8", None),
            ("PP-NOT-DELIVERED", "NOT READY", None, None),
        ],
        columns=["trip_id", "invoice_status", "invoice_no", "blocked_reason"],
    )


def _report() -> pd.DataFrame:
    return run_pod_pulse(_deliveries(), _pods(), _invoices(), review_time=REVIEW_TIME).pod_aging_report


def _row(report: pd.DataFrame, trip_id: str) -> pd.Series:
    return report[report["trip_id"] == trip_id].iloc[0]


def test_pod_received_within_sla() -> None:
    row = _row(_report(), "PP-OK")
    assert row["pod_gap_type"] == "POD RECEIVED"
    assert row["risk_bucket"] == "ON TIME"


def test_missing_document_classification() -> None:
    row = _row(_report(), "PP-MISSING")
    assert row["pod_gap_type"] == "MISSING DOCUMENT"
    assert row["aging_bucket"] == "48-72H"


def test_late_pod_classification() -> None:
    row = _row(_report(), "PP-LATE")
    assert row["pod_gap_type"] == "POD LATE"
    assert row["pod_age_hours"] == 77


def test_rejected_pod_classification() -> None:
    row = _row(_report(), "PP-REJECTED")
    assert row["pod_gap_type"] == "REJECTED POD"
    assert "Stamp missing" in row["evidence"]


def test_invoice_blocker_classification() -> None:
    row = _row(_report(), "PP-BLOCKED")
    assert row["pod_gap_type"] == "INVOICE BLOCKER"
    assert bool(row["invoice_blocked"]) is True


def test_approval_pending_classification() -> None:
    row = _row(_report(), "PP-PENDING")
    assert row["pod_gap_type"] == "APPROVAL PENDING"
    assert bool(row["invoice_blocked"]) is True


def test_critical_missing_pod_classification() -> None:
    row = _row(_report(), "PP-CRITICAL")
    assert row["pod_gap_type"] == "MISSING DOCUMENT"
    assert row["aging_bucket"] == "7D+"
    assert row["risk_bucket"] == "CRITICAL"


def test_not_required_classification() -> None:
    row = _row(_report(), "PP-NOT-REQ")
    assert row["pod_gap_type"] == "POD NOT REQUIRED"
    assert row["risk_bucket"] == "ON TIME"


def test_not_delivered_classification() -> None:
    row = _row(_report(), "PP-NOT-DELIVERED")
    assert row["pod_gap_type"] == "NOT DELIVERED"
    assert row["risk_bucket"] == "DATA MISSING"


def test_risk_bucket_classification() -> None:
    report = _report()
    assert set(report["risk_bucket"]).issuperset(
        {"ON TIME", "WATCH", "DELAYED", "CRITICAL", "DATA MISSING"}
    )


def test_export_smoke(tmp_path: Path) -> None:
    result = run_pod_pulse(_deliveries(), _pods(), _invoices(), review_time=REVIEW_TIME)
    report_path, overdue_path = write_outputs(result, tmp_path)
    assert report_path.exists()
    assert overdue_path.exists()
    assert len(pd.read_csv(report_path)) == len(result.pod_aging_report)
    assert len(pd.read_csv(overdue_path)) == len(result.overdue_pods)


def test_demo_data_smoke() -> None:
    base = Path("pod_pulse/demo_data")
    result = run_pod_pulse(
        pd.read_csv(base / "deliveries.csv"),
        pd.read_csv(base / "pod_status.csv"),
        pd.read_csv(base / "invoice_status.csv"),
        review_time=REVIEW_TIME,
    )
    assert result.kpis["total_deliveries"] == 9
    assert set(result.pod_aging_report["pod_gap_type"]).issuperset(
        {
            "POD RECEIVED",
            "MISSING DOCUMENT",
            "POD LATE",
            "REJECTED POD",
            "INVOICE BLOCKER",
            "APPROVAL PENDING",
            "POD NOT REQUIRED",
            "NOT DELIVERED",
        }
    )
