"""Streamlit interface for UpdatePulse."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from update_pulse.engine import run_update_pulse, write_outputs
from update_pulse.models import UpdatePulseSettings


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
RISK_COLORS = {
    "OK": "#15803d",
    "WATCH": "#ca8a04",
    "REVIEW": "#2563eb",
    "HIGH RISK": "#dc2626",
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
    """Run the UpdatePulse Streamlit app."""
    st.set_page_config(page_title="UpdatePulse", layout="wide")
    st.title("UpdatePulse")
    st.caption("Audits driver and TMS update discipline against planned trips and optional GeoReplay event truth.")

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        updates_file = st.file_uploader("tms_updates.csv or driver_updates.csv", type=["csv"])
        visit_events_file = st.file_uploader("visit_events.csv from GeoReplay (optional)", type=["csv"])
        use_demo_visits = st.checkbox("Use demo visit evidence when no file is uploaded", value=True)

        st.header("Settings")
        settings = UpdatePulseSettings(
            late_tolerance_minutes=st.number_input("Late tolerance minutes", min_value=0, value=15, step=5),
            early_tolerance_minutes=st.number_input("Early tolerance minutes", min_value=0, value=15, step=5),
            duplicate_update_window_minutes=st.number_input(
                "Duplicate update window minutes",
                min_value=0,
                value=10,
                step=5,
            ),
            assigned_lead_minutes=st.number_input("Assigned lead time minutes", min_value=0, value=120, step=15),
            include_pod_collected=st.toggle("Include optional POD_COLLECTED milestone", value=False),
        )
        chart_by = st.selectbox("Chart by", ["exception_type", "carrier_name", "driver_name", "risk_bucket"])
        run_button = st.button("Run UpdatePulse", type="primary")

    st.info(
        "Demo mode uses synthetic GCC logistics data only. Upload your own CSVs to replace the demo inputs."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")
    updates_df = _read_uploaded_or_demo(updates_file, DEMO_DIR / "tms_updates.csv")
    visits_df = _read_optional_uploaded_or_demo(
        visit_events_file,
        DEMO_DIR / "visit_events.csv",
        use_demo_visits,
    )

    result = run_update_pulse(trips_df, updates_df, visits_df, settings=settings)
    report_path, exceptions_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(7)
    _metric_card(metric_cols[0], "Total trips", result.kpis["total_trips"])
    _metric_card(metric_cols[1], "Expected updates", result.kpis["total_expected_updates"])
    _metric_card(metric_cols[2], "Exceptions", result.kpis["update_exceptions"])
    _metric_card(metric_cols[3], "Missing", result.kpis["missing_updates"])
    _metric_card(metric_cols[4], "Late", result.kpis["late_updates"])
    _metric_card(metric_cols[5], "Sequence", result.kpis["out_of_sequence_cases"])
    _metric_card(metric_cols[6], "Avg delay min", result.kpis["average_update_delay_minutes"])

    if chart_by == "exception_type":
        chart_data = result.update_exceptions.groupby("exception_type", as_index=False).size()
        y_label = "exceptions"
    else:
        chart_data = result.update_discipline_report.groupby(chart_by, dropna=False, as_index=False).size()
        y_label = "milestones"
    chart_data = chart_data.rename(columns={"size": y_label})
    chart = px.bar(
        chart_data,
        x=chart_by,
        y=y_label,
        color=chart_by,
        color_discrete_map=RISK_COLORS,
        text_auto=".0f",
    )
    chart.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(chart, use_container_width=True)

    tab_report, tab_exceptions, tab_exports, tab_notes = st.tabs(
        ["Update discipline", "Exceptions", "Exports", "Notes"]
    )

    with tab_report:
        styled = result.update_discipline_report.style.map(_style_risk, subset=["risk_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_exceptions:
        st.dataframe(result.update_exceptions, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{exceptions_path}`.")
        st.download_button(
            "Download update_discipline_report.csv",
            result.update_discipline_report.to_csv(index=False),
            "update_discipline_report.csv",
            "text/csv",
        )
        st.download_button(
            "Download update_exceptions.csv",
            result.update_exceptions.to_csv(index=False),
            "update_exceptions.csv",
            "text/csv",
        )

    with tab_notes:
        st.subheader("How to read this")
        st.write(
            "Use the report to spot update gaps, late updates, sequence issues, duplicate updates, "
            "and milestones that need review because no actual event evidence supports them."
        )
        st.subheader("Limitations")
        st.write(
            "UpdatePulse is a deterministic local audit tool. It does not connect to live TMS systems, "
            "does not score drivers, and does not prove intent. It depends on CSV quality and geofence coverage."
        )


if __name__ == "__main__":
    main()
