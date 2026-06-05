"""Streamlit interface for DelayLens."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from delay_lens.engine import run_delay_lens, write_outputs
from delay_lens.models import DelayLensSettings


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
    """Run the DelayLens Streamlit app."""
    st.set_page_config(page_title="DelayLens", layout="wide")
    st.title("DelayLens")
    st.caption(
        "Classifies late departure, dwell, enroute delay, missing signal, and baseline gaps "
        "from trip plans and GeoReplay visit events."
    )

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        visits_file = st.file_uploader("visit_events.csv", type=["csv"])
        baselines_file = st.file_uploader("lane_baselines.csv (optional)", type=["csv"])
        use_demo_baselines = st.checkbox("Use demo lane baselines when no file is uploaded", value=True)

        st.header("Settings")
        settings = DelayLensSettings(
            late_departure_tolerance_minutes=st.number_input(
                "Late departure tolerance minutes",
                min_value=0,
                value=15,
                step=5,
            ),
            late_arrival_tolerance_minutes=st.number_input(
                "Late arrival tolerance minutes",
                min_value=0,
                value=15,
                step=5,
            ),
            origin_dwell_threshold_minutes=st.number_input(
                "Origin dwell threshold minutes",
                min_value=0,
                value=60,
                step=10,
            ),
            hub_dwell_threshold_minutes=st.number_input(
                "Hub dwell threshold minutes",
                min_value=0,
                value=45,
                step=5,
            ),
            destination_dwell_threshold_minutes=st.number_input(
                "Destination dwell threshold minutes",
                min_value=0,
                value=60,
                step=10,
            ),
            baseline_delta_threshold_minutes=st.number_input(
                "Baseline delta threshold minutes",
                min_value=0,
                value=30,
                step=10,
            ),
            critical_arrival_delay_threshold_minutes=st.number_input(
                "Critical arrival delay threshold minutes",
                min_value=0,
                value=120,
                step=15,
            ),
        )
        chart_by = st.selectbox(
            "Chart by",
            ["primary_delay_reason", "carrier_name", "risk_bucket", "severity"],
        )
        run_button = st.button("Run DelayLens", type="primary")

    st.info(
        "Demo mode uses synthetic GCC logistics data only. Upload your own CSVs to replace the demo inputs."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")
    visits_df = _read_uploaded_or_demo(visits_file, DEMO_DIR / "visit_events.csv")
    baselines_df = _read_optional_uploaded_or_demo(
        baselines_file,
        DEMO_DIR / "lane_baselines.csv",
        use_demo_baselines,
    )

    result = run_delay_lens(trips_df, visits_df, baselines_df, settings=settings)
    report_path, critical_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    _metric_card(metric_cols[0], "Total trips", result.kpis["total_trips"])
    _metric_card(metric_cols[1], "Delayed trips", result.kpis["delayed_trips"])
    _metric_card(metric_cols[2], "Critical", result.kpis["critical_delays"])
    _metric_card(metric_cols[3], "Missing signal", result.kpis["missing_signal"])
    _metric_card(metric_cols[4], "Baseline missing", result.kpis["baseline_missing"])
    _metric_card(metric_cols[5], "Avg arrival delay", result.kpis["average_arrival_delay_minutes"])

    chart_data = result.delay_classification_report.groupby(chart_by, dropna=False, as_index=False).size()
    chart_data = chart_data.rename(columns={"size": "trips"})
    chart = px.bar(
        chart_data,
        x=chart_by,
        y="trips",
        color=chart_by,
        color_discrete_map=RISK_COLORS,
        text_auto=".0f",
    )
    chart.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(chart, use_container_width=True)

    tab_report, tab_critical, tab_exports, tab_notes = st.tabs(
        ["Delay classification", "Critical delays", "Exports", "Notes"]
    )

    with tab_report:
        styled = result.delay_classification_report.style.map(_style_risk, subset=["risk_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_critical:
        st.dataframe(result.critical_delays, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{critical_path}`.")
        st.download_button(
            "Download delay_classification_report.csv",
            result.delay_classification_report.to_csv(index=False),
            "delay_classification_report.csv",
            "text/csv",
        )
        st.download_button(
            "Download critical_delays.csv",
            result.critical_delays.to_csv(index=False),
            "critical_delays.csv",
            "text/csv",
        )

    with tab_notes:
        st.subheader("How to read this")
        st.write(
            "Use the primary delay reason to see where time was most likely lost. "
            "Secondary flags show supporting signals such as late arrival, long dwell, "
            "missing baseline, or missing visit evidence."
        )
        st.subheader("Limitations")
        st.write(
            "DelayLens is deterministic and file-based. It does not assign blame, infer traffic, "
            "or prove root cause. Results depend on GeoReplay event quality, trip timing quality, "
            "and lane baseline coverage."
        )


if __name__ == "__main__":
    main()
