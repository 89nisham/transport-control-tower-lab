"""Streamlit interface for GateTruth trip gate verification."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from gate_truth.engine import STATUS_ORDER, run_gate_truth, write_outputs


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
STATUS_COLORS = {
    "EXCEPTION": "#dc2626",
    "AMBIGUOUS": "#9333ea",
    "AMBIGUOUS MATCH": "#9333ea",
    "INCOMPLETE": "#ca8a04",
    "OK": "#15803d",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    """Read an uploaded CSV or fall back to bundled GateTruth demo data."""
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _download_csv(label: str, df: pd.DataFrame, filename: str) -> None:
    """Render a Streamlit CSV download button for one output dataframe."""
    st.download_button(label=label, data=df.to_csv(index=False), file_name=filename, mime="text/csv")


def _status_style(value: str) -> str:
    """Return table styling for an evidence status value."""
    color = STATUS_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the GateTruth Streamlit application."""
    st.set_page_config(page_title="GateTruth", layout="wide")
    st.title("GateTruth")
    st.caption("Verify actual origin and destination gate evidence from GeoReplay visits.")

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        visit_events_file = st.file_uploader("visit_events.csv from GeoReplay", type=["csv"])
        planned_stops_file = st.file_uploader("planned_stops.csv (optional)", type=["csv"])
        start_grace = st.number_input("Late start grace minutes", min_value=0, value=15, step=5)
        arrival_grace = st.number_input("Late arrival grace minutes", min_value=0, value=15, step=5)
        early_threshold = st.number_input(
            "Early arrival review threshold minutes",
            min_value=0,
            value=60,
            step=15,
        )
        run_button = st.button("Run GateTruth", type="primary")

    st.info(
        "No upload needed for the demo: GateTruth loads synthetic GCC trips, "
        "GeoReplay visit events, and planned stops from `gate_truth/demo_data/`."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")
    visits_df = _read_uploaded_or_demo(visit_events_file, DEMO_DIR / "visit_events.csv")
    stops_df = _read_uploaded_or_demo(planned_stops_file, DEMO_DIR / "planned_stops.csv")

    result = run_gate_truth(
        trips_df,
        visits_df,
        stops_df,
        start_grace_minutes=float(start_grace),
        arrival_grace_minutes=float(arrival_grace),
        early_arrival_threshold_minutes=float(early_threshold),
    )
    report_path, exceptions_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Total trips", int(result.kpis["total_trips"]))
    metric_cols[1].metric("Confirmed starts", int(result.kpis["confirmed_starts"]))
    metric_cols[2].metric("Confirmed arrivals", int(result.kpis["confirmed_arrivals"]))
    metric_cols[3].metric("Missing origin exits", int(result.kpis["missing_origin_exits"]))
    metric_cols[4].metric("Missing dest entries", int(result.kpis["missing_destination_entries"]))
    metric_cols[5].metric("Late arrivals", int(result.kpis["late_arrivals"]))

    chart_data = (
        result.gate_truth_report.groupby("gate_truth_status", as_index=False)["trip_id"]
        .count()
        .rename(columns={"trip_id": "trips"})
    )
    chart = px.bar(
        chart_data,
        x="gate_truth_status",
        y="trips",
        color="gate_truth_status",
        color_discrete_map=STATUS_COLORS,
        category_orders={"gate_truth_status": STATUS_ORDER},
        text_auto=".0f",
    )
    chart.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=10),
        height=300,
        xaxis_title="",
        yaxis_title="Trips",
    )
    st.plotly_chart(chart, use_container_width=True)

    tab_report, tab_exceptions, tab_exports = st.tabs(
        ["Gate Truth Report", "Exceptions", "Exports"]
    )

    with tab_report:
        styled = result.gate_truth_report.style.map(_status_style, subset=["gate_truth_status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_exceptions:
        st.dataframe(result.gate_exceptions, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{exceptions_path}`.")
        _download_csv(
            "Download gate_truth_report.csv",
            result.gate_truth_report,
            "gate_truth_report.csv",
        )
        _download_csv(
            "Download gate_exceptions.csv",
            result.gate_exceptions,
            "gate_exceptions.csv",
        )


if __name__ == "__main__":
    main()
