"""Streamlit interface for LaneLab."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from lane_lab.engine import run_lane_lab, write_outputs
from lane_lab.models import LaneLabSettings


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
CONFIDENCE_COLORS = {
    "GOOD": "#15803d",
    "LOW SAMPLE": "#ca8a04",
    "UNSTABLE": "#dc2626",
    "CHECK DATA": "#7f1d1d",
    "NO BASELINE": "#64748b",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _metric_card(column, label: str, value: float) -> None:
    column.metric(label, f"{value:.1f}" if isinstance(value, float) and not value.is_integer() else int(value))


def _style_confidence(value: str) -> str:
    color = CONFIDENCE_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the LaneLab Streamlit app."""
    st.set_page_config(page_title="LaneLab", layout="wide")
    st.title("LaneLab")
    st.caption(
        "Builds p50/p75/p90 lane travel-time profiles from historical trips and "
        "GeoReplay visit events."
    )

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("historical_trips.csv", type=["csv"])
        visits_file = st.file_uploader("historical_visit_events.csv", type=["csv"])

        st.header("Settings")
        settings = LaneLabSettings(
            low_sample_threshold=st.number_input("Low sample threshold", min_value=1, value=5, step=1),
            unstable_p90_p50_ratio_threshold=st.number_input(
                "Unstable p90/p50 ratio",
                min_value=0.0,
                value=1.5,
                step=0.1,
            ),
            outlier_iqr_multiplier=st.number_input(
                "Outlier IQR multiplier",
                min_value=0.0,
                value=1.5,
                step=0.25,
            ),
            extreme_duration_min_minutes=st.number_input(
                "Extreme duration minimum minutes",
                min_value=0,
                value=30,
                step=5,
            ),
            extreme_duration_max_minutes=st.number_input(
                "Extreme duration maximum minutes",
                min_value=1,
                value=2880,
                step=60,
            ),
            min_usable_trips_for_percentiles=st.number_input(
                "Minimum usable trips for percentiles",
                min_value=1,
                value=2,
                step=1,
            ),
        )
        chart_by = st.selectbox("Chart by", ["confidence_bucket", "carrier_name", "customer_name"])
        run_button = st.button("Run LaneLab", type="primary")

    st.info(
        "Demo mode uses synthetic GCC logistics data only. Upload CSVs to replace the demo inputs."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "historical_trips.csv")
    visits_df = _read_uploaded_or_demo(visits_file, DEMO_DIR / "historical_visit_events.csv")
    result = run_lane_lab(trips_df, visits_df, settings=settings)
    baseline_path, outlier_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    _metric_card(metric_cols[0], "Lanes", result.kpis["total_lanes"])
    _metric_card(metric_cols[1], "Trips", result.kpis["total_trips"])
    _metric_card(metric_cols[2], "Usable trips", result.kpis["usable_trips"])
    _metric_card(metric_cols[3], "Invalid trips", result.kpis["invalid_trips"])
    _metric_card(metric_cols[4], "Outliers", result.kpis["outlier_trips"])
    _metric_card(metric_cols[5], "Risky lanes", result.kpis["low_confidence_lanes"])

    chart_data = result.lane_baselines.groupby(chart_by, dropna=False, as_index=False).size()
    chart_data = chart_data.rename(columns={"size": "lanes"})
    chart = px.bar(
        chart_data,
        x=chart_by,
        y="lanes",
        color=chart_by,
        color_discrete_map=CONFIDENCE_COLORS,
        text_auto=".0f",
    )
    chart.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(chart, use_container_width=True)

    tab_baselines, tab_outliers, tab_durations, tab_exports, tab_notes = st.tabs(
        ["Lane baselines", "Outliers", "Trip durations", "Exports", "Notes"]
    )

    with tab_baselines:
        styled = result.lane_baselines.style.map(_style_confidence, subset=["confidence_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_outliers:
        st.dataframe(result.lane_outliers, use_container_width=True, hide_index=True)

    with tab_durations:
        st.dataframe(result.trip_durations, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{baseline_path}` and `{outlier_path}`.")
        st.download_button(
            "Download lane_baselines.csv",
            result.lane_baselines.to_csv(index=False),
            "lane_baselines.csv",
            "text/csv",
        )
        st.download_button(
            "Download lane_outliers.csv",
            result.lane_outliers.to_csv(index=False),
            "lane_outliers.csv",
            "text/csv",
        )

    with tab_notes:
        st.subheader("How to read this")
        st.write(
            "Use confidence bucket, sample size, invalid trips, and outlier count to decide "
            "which lane baselines are ready for ETA and SLA review."
        )
        st.subheader("Limitations")
        st.write(
            "LaneLab is deterministic and file-based. It does not predict traffic, optimize routes, "
            "or connect to live systems. Results depend on historical trip and GeoReplay visit quality."
        )


if __name__ == "__main__":
    main()
