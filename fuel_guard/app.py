"""Streamlit interface for FuelGuard fuel-vs-GPS reconciliation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from fuel_guard.engine import STATUS_ORDER, run_fuel_guard, write_outputs


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
STATUS_COLORS = {
    "HIGH RISK": "#dc2626",
    "DATA MISSING": "#9333ea",
    "REVIEW": "#ca8a04",
    "OK": "#15803d",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    """Read an uploaded CSV or fall back to bundled FuelGuard demo data."""
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _read_optional_uploaded_or_demo(
    uploaded_file,
    demo_path: Path,
    use_demo: bool,
) -> pd.DataFrame | None:
    """Read optional CSV input when uploaded or when demo mode is enabled."""
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    if use_demo:
        return pd.read_csv(demo_path)
    return None


def _download_csv(label: str, df: pd.DataFrame, filename: str) -> None:
    """Render a Streamlit CSV download button for one output dataframe."""
    st.download_button(label=label, data=df.to_csv(index=False), file_name=filename, mime="text/csv")


def _status_style(value: str) -> str:
    """Return table styling for a FuelGuard status value."""
    color = STATUS_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the FuelGuard Streamlit application."""
    st.set_page_config(page_title="FuelGuard", layout="wide")
    st.title("FuelGuard")
    st.caption("Reconcile fuel transactions against GPS and GeoReplay stop evidence for review.")

    with st.sidebar:
        st.header("Inputs")
        fuel_events_file = st.file_uploader("fuel_events.csv", type=["csv"])
        visit_events_file = st.file_uploader("visit_events.csv from GeoReplay (optional)", type=["csv"])
        gps_points_file = st.file_uploader("gps_points.csv (optional)", type=["csv"])
        fuel_sites_file = st.file_uploader("fuel_sites.csv (optional)", type=["csv"])
        trips_file = st.file_uploader("trips.csv (optional)", type=["csv"])
        use_demo_optional = st.checkbox("Load demo optional evidence", value=True)
        gps_window = st.number_input("Fuel matching window minutes", min_value=5, value=30, step=5)
        gps_distance = st.number_input("Fuel site radius meters", min_value=50, value=500, step=50)
        high_liters = st.number_input("High liters threshold", min_value=100, value=450, step=50)
        stop_speed = st.number_input("Stop speed threshold kph", min_value=0, value=5, step=1)
        min_stop = st.number_input("Minimum stop dwell minutes", min_value=0, value=10, step=1)
        chart_by = st.selectbox("Chart by", ["Risk bucket", "Exception type", "Vehicle"])
        run_button = st.button("Run FuelGuard", type="primary")

    st.info(
        "No upload needed for the demo: FuelGuard loads synthetic GCC fuel events, "
        "GeoReplay visits, GPS points, known fuel sites, and trip windows from `fuel_guard/demo_data/`."
    )

    if not run_button:
        st.stop()

    fuel_events_df = _read_uploaded_or_demo(fuel_events_file, DEMO_DIR / "fuel_events.csv")
    visits_df = _read_optional_uploaded_or_demo(
        visit_events_file,
        DEMO_DIR / "visit_events.csv",
        use_demo_optional,
    )
    gps_df = _read_optional_uploaded_or_demo(
        gps_points_file,
        DEMO_DIR / "gps_points.csv",
        use_demo_optional,
    )
    sites_df = _read_optional_uploaded_or_demo(
        fuel_sites_file,
        DEMO_DIR / "fuel_sites.csv",
        use_demo_optional,
    )
    trips_df = _read_optional_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv", use_demo_optional)

    result = run_fuel_guard(
        fuel_events_df,
        visits_df,
        gps_df,
        sites_df,
        trips_df,
        gps_time_window_minutes=float(gps_window),
        gps_distance_threshold_m=float(gps_distance),
        minimum_stop_minutes=float(min_stop),
        high_liter_threshold=float(high_liters),
        stop_speed_threshold_kph=float(stop_speed),
    )
    report_path, exceptions_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    metric_cols[0].metric("Fuel events", int(result.kpis["total_fuel_events"]))
    metric_cols[1].metric("Matched", int(result.kpis["matched_events"]))
    metric_cols[2].metric("Exceptions", int(result.kpis["exception_events"]))
    metric_cols[3].metric("Duplicate receipts", int(result.kpis["duplicate_receipts"]))
    metric_cols[4].metric("High-liter events", int(result.kpis["high_liter_events"]))
    metric_cols[5].metric("Liters under review", round(result.kpis["total_liters_under_review"], 1))

    chart_column = {
        "Risk bucket": "risk_bucket",
        "Exception type": "exception_flags",
        "Vehicle": "vehicle_id",
    }[chart_by]
    chart_data = result.fuel_reconciliation_report.copy()
    if chart_column == "exception_flags":
        chart_data = chart_data.assign(exception_flags=chart_data["exception_flags"].str.split("; "))
        chart_data = chart_data.explode("exception_flags")
    chart_data = (
        chart_data.groupby(chart_column, as_index=False)["fuel_event_id"]
        .count()
        .rename(columns={"fuel_event_id": "fuel_events"})
    )
    chart = px.bar(
        chart_data,
        x=chart_column,
        y="fuel_events",
        color=chart_column,
        color_discrete_map=STATUS_COLORS,
        category_orders={"risk_bucket": STATUS_ORDER},
        text_auto=".0f",
    )
    chart.update_layout(
        showlegend=False,
        margin=dict(l=10, r=10, t=20, b=10),
        height=300,
        xaxis_title="",
        yaxis_title="Fuel events",
    )
    st.plotly_chart(chart, use_container_width=True)

    with st.expander("How to read this"):
        st.write(
            "`OK` means the fuel event has supporting evidence and no exception flags. "
            "`REVIEW`, `DATA MISSING`, and `HIGH RISK` are review buckets for control-tower follow-up; "
            "they are not accusations or payment decisions."
        )

    with st.expander("Limitations"):
        st.write(
            "FuelGuard is deterministic and file-based. It does not connect to fuel cards, ERP, "
            "live telematics, driver workflows, legal claims, or payment systems."
        )

    tab_report, tab_exceptions, tab_exports = st.tabs(["Reconciliation Report", "Exceptions", "Exports"])

    with tab_report:
        styled = result.fuel_reconciliation_report.style.map(
            _status_style,
            subset=["risk_bucket"],
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_exceptions:
        st.dataframe(result.fuel_exceptions, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{report_path}` and `{exceptions_path}`.")
        _download_csv(
            "Download fuel_reconciliation_report.csv",
            result.fuel_reconciliation_report,
            "fuel_reconciliation_report.csv",
        )
        _download_csv("Download fuel_exceptions.csv", result.fuel_exceptions, "fuel_exceptions.csv")


if __name__ == "__main__":
    main()
