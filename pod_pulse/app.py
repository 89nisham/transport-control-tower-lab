"""Streamlit interface for PODPulse."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from pod_pulse.engine import run_pod_pulse, write_outputs
from pod_pulse.models import PODPulseSettings


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
RISK_COLORS = {
    "ON TIME": "#15803d",
    "WATCH": "#ca8a04",
    "DELAYED": "#dc2626",
    "CRITICAL": "#991b1b",
    "DATA MISSING": "#64748b",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _read_optional_uploaded_or_demo(uploaded_file, demo_path: Path, use_demo: bool) -> pd.DataFrame | None:
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    if use_demo:
        return pd.read_csv(demo_path)
    return None


def _metric_card(column, label: str, value: float) -> None:
    column.metric(label, f"{value:.1f}" if isinstance(value, float) and not value.is_integer() else int(value))


def _style_risk(value: str) -> str:
    color = RISK_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the PODPulse Streamlit app."""
    st.set_page_config(page_title="PODPulse", layout="wide")
    st.title("PODPulse")
    st.caption(
        "Tracks POD aging, missing documents, rejected PODs, approval pending cases, "
        "and invoice blockers from local CSV files."
    )

    with st.sidebar:
        st.header("Inputs")
        deliveries_file = st.file_uploader("deliveries.csv", type=["csv"])
        pod_file = st.file_uploader("pod_status.csv", type=["csv"])
        invoice_file = st.file_uploader("invoice_status.csv (optional)", type=["csv"])
        use_demo_invoice = st.checkbox("Use demo invoice status when no file is uploaded", value=True)

        st.header("Settings")
        settings = PODPulseSettings(
            pod_sla_hours=st.number_input("POD SLA hours", min_value=0, value=48, step=12),
            warning_threshold_hours=st.number_input(
                "Warning threshold hours",
                min_value=0,
                value=24,
                step=6,
            ),
            critical_threshold_hours=st.number_input(
                "Critical threshold hours",
                min_value=0,
                value=168,
                step=24,
            ),
        )
        review_time = st.text_input("Review time UTC", value="2026-06-10T12:00:00Z")
        chart_by = st.selectbox("Chart by", ["pod_gap_type", "risk_bucket", "carrier_name", "customer_name"])
        run_button = st.button("Run PODPulse", type="primary")

    st.info("Demo mode uses synthetic GCC logistics data only. Upload CSVs to replace the demo inputs.")

    if not run_button:
        st.stop()

    deliveries_df = _read_uploaded_or_demo(deliveries_file, DEMO_DIR / "deliveries.csv")
    pod_df = _read_uploaded_or_demo(pod_file, DEMO_DIR / "pod_status.csv")
    invoice_df = _read_optional_uploaded_or_demo(
        invoice_file,
        DEMO_DIR / "invoice_status.csv",
        use_demo_invoice,
    )

    result = run_pod_pulse(
        deliveries_df,
        pod_df,
        invoice_df,
        settings=settings,
        review_time=review_time,
    )
    report_path, overdue_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    _metric_card(metric_cols[0], "Deliveries", result.kpis["total_deliveries"])
    _metric_card(metric_cols[1], "Missing PODs", result.kpis["missing_pods"])
    _metric_card(metric_cols[2], "Late PODs", result.kpis["late_pods"])
    _metric_card(metric_cols[3], "Rejected", result.kpis["rejected_pods"])
    _metric_card(metric_cols[4], "Invoice blockers", result.kpis["invoice_blockers"])
    _metric_card(metric_cols[5], "Critical gaps", result.kpis["critical_pod_gaps"])

    chart_data = result.pod_aging_report.groupby(chart_by, dropna=False, as_index=False).size()
    chart_data = chart_data.rename(columns={"size": "deliveries"})
    chart = px.bar(
        chart_data,
        x=chart_by,
        y="deliveries",
        color=chart_by,
        color_discrete_map=RISK_COLORS,
        text_auto=".0f",
    )
    chart.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(chart, use_container_width=True)

    tab_report, tab_overdue, tab_exports, tab_notes = st.tabs(
        ["POD aging", "Overdue PODs", "Exports", "Notes"]
    )

    with tab_report:
        styled = result.pod_aging_report.style.map(_style_risk, subset=["risk_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_overdue:
        st.dataframe(result.overdue_pods, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{overdue_path}`.")
        st.download_button(
            "Download pod_aging_report.csv",
            result.pod_aging_report.to_csv(index=False),
            "pod_aging_report.csv",
            "text/csv",
        )
        st.download_button(
            "Download overdue_pods.csv",
            result.overdue_pods.to_csv(index=False),
            "overdue_pods.csv",
            "text/csv",
        )

    with tab_notes:
        st.subheader("How to read this")
        st.write(
            "Use POD gap type and aging bucket to prioritize missing documents, late receipts, "
            "rejected PODs, approval pending cases, and invoice blockers."
        )
        st.subheader("Limitations")
        st.write(
            "PODPulse is deterministic and file-based. It does not perform OCR, post to ERP, "
            "send emails, or decide commercial liability. Results depend on delivered time, "
            "POD status, and invoice status data quality."
        )


if __name__ == "__main__":
    main()

