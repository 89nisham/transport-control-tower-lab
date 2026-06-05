"""Streamlit interface for ETA Watch risk monitoring."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from eta_watch.engine import RISK_ORDER, run_eta_watch, write_outputs


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
RISK_COLORS = {
    "ON TRACK": "#15803d",
    "WATCH": "#ca8a04",
    "AT RISK": "#ea580c",
    "LATE": "#dc2626",
    "NO SIGNAL": "#64748b",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    """Read an uploaded CSV or fall back to bundled ETA Watch demo data."""
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _download_csv(label: str, df: pd.DataFrame, filename: str) -> None:
    """Render a Streamlit CSV download button for one output dataframe."""
    st.download_button(
        label=label,
        data=df.to_csv(index=False),
        file_name=filename,
        mime="text/csv",
    )


def _risk_style(value: str) -> str:
    """Return table styling for a risk bucket value."""
    color = RISK_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the ETA Watch Streamlit application."""
    st.set_page_config(page_title="ETA Watch", layout="wide")
    st.title("ETA Watch")
    st.caption("Identify trips likely to miss planned ETA from local trip and GeoReplay files.")

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        visit_events_file = st.file_uploader("visit_events.csv from GeoReplay", type=["csv"])
        lane_baselines_file = st.file_uploader("lane_baselines.csv (optional)", type=["csv"])
        current_time = st.text_input(
            "Control-tower time (UTC)",
            value="2026-06-04T07:00:00Z",
            help="Demo-friendly current time. Uploaded timestamps are standardized to UTC.",
        )
        run_button = st.button("Run ETA Watch", type="primary")

    st.info(
        "No upload needed for the demo: ETA Watch loads synthetic trips, GeoReplay visit events, "
        "and lane baselines from `eta_watch/demo_data/`."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")
    visit_events_df = _read_uploaded_or_demo(visit_events_file, DEMO_DIR / "visit_events.csv")
    baselines_df = (
        None
        if lane_baselines_file is None and not (DEMO_DIR / "lane_baselines.csv").exists()
        else _read_uploaded_or_demo(lane_baselines_file, DEMO_DIR / "lane_baselines.csv")
    )

    try:
        result = run_eta_watch(trips_df, visit_events_df, baselines_df, current_time=current_time)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    risk_path, late_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Total trips", result.kpis["total_trips"])
    metric_cols[1].metric("On track", result.kpis["on_track"])
    metric_cols[2].metric("Watch", result.kpis["watch"])
    metric_cols[3].metric("At risk", result.kpis["at_risk"])
    metric_cols[4].metric("Late", result.kpis["late"])
    metric_cols[5].metric("No signal", result.kpis["no_signal"])

    counts = (
        result.risk_board["risk_bucket"]
        .value_counts()
        .reindex(RISK_ORDER, fill_value=0)
        .rename_axis("risk_bucket")
        .reset_index(name="trips")
    )
    chart = px.bar(
        counts,
        x="risk_bucket",
        y="trips",
        color="risk_bucket",
        color_discrete_map=RISK_COLORS,
        category_orders={"risk_bucket": RISK_ORDER},
        text="trips",
    )
    chart.update_layout(showlegend=False, margin=dict(l=10, r=10, t=20, b=10), height=260)
    st.plotly_chart(chart, use_container_width=True)

    tab_board, tab_detail, tab_exports = st.tabs(["ETA Risk Board", "Trip Detail", "Exports"])

    with tab_board:
        styled = result.risk_board.style.map(_risk_style, subset=["risk_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_detail:
        trip_ids = result.risk_board["trip_id"].tolist()
        selected_trip = st.selectbox("Trip", trip_ids)
        trip_row = result.risk_board[result.risk_board["trip_id"] == selected_trip].iloc[0]
        detail_cols = st.columns(3)
        detail_cols[0].metric("Risk", trip_row["risk_bucket"])
        detail_cols[1].metric("ETA delta minutes", trip_row["eta_delta_minutes"])
        detail_cols[2].metric("Remaining minutes", trip_row["estimated_remaining_minutes"])
        st.write(trip_row.to_frame(name="value"))

    with tab_exports:
        st.write(f"Wrote `{risk_path}` and `{late_path}`.")
        _download_csv("Download eta_risk_board.csv", result.risk_board, "eta_risk_board.csv")
        _download_csv("Download late_trips.csv", result.late_trips, "late_trips.csv")


if __name__ == "__main__":
    main()
