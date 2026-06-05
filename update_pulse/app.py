"""Streamlit interface for UpdatePulse update-discipline review."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from update_pulse.engine import STATUS_ORDER, run_update_pulse, write_outputs


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
STATUS_COLORS = {
    "NEEDS REVIEW": "#dc2626",
    "UPDATE GAP": "#ca8a04",
    "OK": "#15803d",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    """Read an uploaded CSV or fall back to bundled UpdatePulse demo data."""
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _read_optional_uploaded_or_demo(
    uploaded_file,
    demo_path: Path,
    use_demo: bool,
) -> pd.DataFrame | None:
    """Read optional visit evidence when uploaded or demo mode is enabled."""
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    if use_demo:
        return pd.read_csv(demo_path)
    return None


def _download_csv(label: str, df: pd.DataFrame, filename: str) -> None:
    """Render a Streamlit CSV download button for one output dataframe."""
    st.download_button(label=label, data=df.to_csv(index=False), file_name=filename, mime="text/csv")


def _status_style(value: str) -> str:
    """Return table styling for an UpdatePulse status value."""
    color = STATUS_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the UpdatePulse Streamlit application."""
    st.set_page_config(page_title="UpdatePulse", layout="wide")
    st.title("UpdatePulse")
    st.caption("Review TMS and driver update timing against planned and actual event evidence.")

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        updates_file = st.file_uploader("tms_updates.csv or driver_updates.csv", type=["csv"])
        visit_events_file = st.file_uploader("visit_events.csv from GeoReplay (optional)", type=["csv"])
        use_demo_visits = st.checkbox("Load demo actual event evidence", value=True)
        grace_minutes = st.number_input("Late update grace minutes", min_value=0, value=15, step=5)
        early_threshold = st.number_input("Early update review threshold minutes", min_value=0, value=30, step=5)
        match_window = st.number_input("Update matching window hours", min_value=1, value=8, step=1)
        chart_by = st.selectbox("Chart by", ["Update status", "Exception type", "Carrier"])
        run_button = st.button("Run UpdatePulse", type="primary")

    st.info(
        "No upload needed for the demo: UpdatePulse loads synthetic GCC trips, "
        "TMS updates, and GeoReplay visit evidence from `update_pulse/demo_data/`."
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

    result = run_update_pulse(
        trips_df,
        updates_df,
        visits_df,
        grace_minutes=float(grace_minutes),
        early_threshold_minutes=float(early_threshold),
        match_window_hours=float(match_window),
    )
    report_path, exceptions_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Milestones", int(result.kpis["total_milestones"]))
    metric_cols[1].metric("OK", int(result.kpis["ok_milestones"]))
    metric_cols[2].metric("Update gaps", int(result.kpis["update_gaps"]))
    metric_cols[3].metric("Late updates", int(result.kpis["late_updates"]))
    metric_cols[4].metric("Sequence issues", int(result.kpis["sequence_issues"]))
    metric_cols[5].metric("No event evidence", int(result.kpis["no_event_evidence"]))

    chart_column = {
        "Update status": "update_status",
        "Exception type": "exception_type",
        "Carrier": "carrier_name",
    }[chart_by]
    chart_data = result.update_discipline_report.copy()
    if chart_column == "exception_type":
        chart_data = chart_data.assign(exception_type=chart_data["exception_type"].str.split("; "))
        chart_data = chart_data.explode("exception_type")
    chart_data = (
        chart_data.groupby(chart_column, dropna=False, as_index=False)["trip_id"]
        .count()
        .rename(columns={"trip_id": "milestones"})
    )
    chart = px.bar(
        chart_data,
        x=chart_column,
        y="milestones",
        color=chart_column,
        color_discrete_map=STATUS_COLORS,
        category_orders={"update_status": STATUS_ORDER},
        text_auto=".0f",
    )
    chart.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=10),
        height=300,
        xaxis_title="",
        yaxis_title="Milestones",
    )
    st.plotly_chart(chart, use_container_width=True)

    with st.expander("How to read this"):
        st.write(
            "`OK` means the milestone update is supported by timing and available event evidence. "
            "`UPDATE GAP` and `NEEDS REVIEW` are neutral review buckets for dispatch follow-up; "
            "they are not disciplinary labels."
        )

    tab_report, tab_exceptions, tab_exports = st.tabs(["Update Report", "Exceptions", "Exports"])

    with tab_report:
        styled = result.update_discipline_report.style.map(
            _status_style,
            subset=["update_status"],
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_exceptions:
        st.dataframe(result.update_exceptions, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{exceptions_path}`.")
        _download_csv(
            "Download update_discipline_report.csv",
            result.update_discipline_report,
            "update_discipline_report.csv",
        )
        _download_csv(
            "Download update_exceptions.csv",
            result.update_exceptions,
            "update_exceptions.csv",
        )


if __name__ == "__main__":
    main()
