"""Streamlit interface for DetentionClock detention billing review."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from detention_clock.engine import DETENTION_ORDER, run_detention_clock, write_outputs


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
RISK_COLORS = {
    "MISSING EXIT": "#64748b",
    "DETENTION": "#dc2626",
    "APPROACHING FREE TIME": "#ca8a04",
    "WITHIN FREE TIME": "#15803d",
    "NO DETENTION": "#94a3b8",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    """Read an uploaded CSV or fall back to bundled DetentionClock demo data."""
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
    """Return table styling for a detention bucket value."""
    color = RISK_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the DetentionClock Streamlit application."""
    st.set_page_config(page_title="DetentionClock", layout="wide")
    st.title("DetentionClock")
    st.caption("Calculate chargeable detention from GeoReplay visits and local free-time rules.")

    with st.sidebar:
        st.header("Inputs")
        visit_events_file = st.file_uploader("visit_events.csv from GeoReplay", type=["csv"])
        detention_rules_file = st.file_uploader("detention_rules.csv", type=["csv"])
        trips_file = st.file_uploader("trips.csv (optional)", type=["csv"])
        chart_dimension = st.selectbox("Chart by", ["customer_name", "geofence_type"])
        run_button = st.button("Run DetentionClock", type="primary")

    st.info(
        "No upload needed for the demo: DetentionClock loads synthetic GCC visit events, "
        "detention rules, and trip context from `detention_clock/demo_data/`."
    )

    if not run_button:
        st.stop()

    visit_events_df = _read_uploaded_or_demo(
        visit_events_file,
        DEMO_DIR / "visit_events.csv",
    )
    rules_df = _read_uploaded_or_demo(
        detention_rules_file,
        DEMO_DIR / "detention_rules.csv",
    )
    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")

    try:
        result = run_detention_clock(visit_events_df, rules_df, trips_df)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    report_path, chargeable_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Total visits", int(result.kpis["total_visits"]))
    metric_cols[1].metric("Detention cases", int(result.kpis["detention_cases"]))
    metric_cols[2].metric("Missing exits", int(result.kpis["missing_exits"]))
    metric_cols[3].metric(
        "Chargeable minutes",
        int(result.kpis["total_chargeable_minutes"]),
    )
    metric_cols[4].metric(
        "Estimated amount",
        f"{result.kpis['estimated_detention_amount']:,.0f}",
    )

    chart_source = result.detention_report.copy()
    chart_source[chart_dimension] = chart_source[chart_dimension].fillna("Unassigned")
    chart_data = (
        chart_source.groupby([chart_dimension, "risk_bucket"], as_index=False)["estimated_charge"]
        .sum()
        .sort_values("estimated_charge", ascending=False)
    )
    chart = px.bar(
        chart_data,
        x=chart_dimension,
        y="estimated_charge",
        color="risk_bucket",
        color_discrete_map=RISK_COLORS,
        category_orders={"risk_bucket": DETENTION_ORDER},
        text_auto=".0f",
    )
    chart.update_layout(
        showlegend=True,
        margin=dict(l=10, r=10, t=20, b=10),
        height=300,
        xaxis_title="",
        yaxis_title="Estimated charge",
    )
    st.plotly_chart(chart, use_container_width=True)

    tab_report, tab_chargeable, tab_exports = st.tabs(
        ["Detention Report", "Chargeable Only", "Exports"]
    )

    with tab_report:
        styled = result.detention_report.style.map(_risk_style, subset=["risk_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_chargeable:
        st.dataframe(result.chargeable_detention, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{chargeable_path}`.")
        _download_csv(
            "Download detention_report.csv",
            result.detention_report,
            "detention_report.csv",
        )
        _download_csv(
            "Download chargeable_detention.csv",
            result.chargeable_detention,
            "chargeable_detention.csv",
        )


if __name__ == "__main__":
    main()
