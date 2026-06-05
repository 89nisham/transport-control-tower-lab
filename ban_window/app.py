"""Streamlit interface for BanWindow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from ban_window.engine import run_ban_window, write_outputs
from ban_window.models import BanWindowSettings


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
STATUS_COLORS = {
    "CLEAR": "#15803d",
    "CONFLICT": "#dc2626",
    "WATCH": "#ca8a04",
    "MISSING TIMING": "#64748b",
    "MISSING CITY": "#7f1d1d",
    "VEHICLE CLASS UNKNOWN": "#9333ea",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame | None:
    if uploaded_file is None:
        if demo_path.exists():
            return pd.read_csv(demo_path)
        return None
    return pd.read_csv(uploaded_file)


def _metric_card(column, label: str, value: float) -> None:
    column.metric(label, f"{value:.1f}" if isinstance(value, float) and not value.is_integer() else int(value))


def _style_status(value: str) -> str:
    color = STATUS_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the BanWindow Streamlit app."""
    st.set_page_config(page_title="BanWindow", layout="wide")
    st.title("BanWindow")
    st.caption(
        "Checks planned or predicted trip movement intervals against uploaded restriction windows."
    )

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        ban_file = st.file_uploader("ban_windows.csv", type=["csv"])
        eta_file = st.file_uploader("eta_risk_board.csv (optional)", type=["csv"])
        visits_file = st.file_uploader("visit_events.csv (optional)", type=["csv"])

        st.header("Settings")
        settings = BanWindowSettings(
            watch_buffer_minutes=st.number_input(
                "Watch buffer minutes",
                min_value=0,
                value=60,
                step=15,
            ),
            expansion_padding_days=st.number_input(
                "Window expansion padding days",
                min_value=0,
                value=1,
                step=1,
            ),
        )
        chart_by = st.selectbox("Chart by", ["risk_status", "city", "vehicle_class", "carrier_name"])
        run_button = st.button("Run BanWindow", type="primary")

    st.info(
        "Demo mode uses synthetic planning data only. BanWindow does not include legal rules; "
        "it checks only the restriction windows uploaded in `ban_windows.csv`."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")
    ban_df = _read_uploaded_or_demo(ban_file, DEMO_DIR / "ban_windows.csv")
    eta_df = _read_uploaded_or_demo(eta_file, DEMO_DIR / "eta_risk_board.csv")
    visits_df = _read_uploaded_or_demo(visits_file, DEMO_DIR / "visit_events.csv")
    if trips_df is None or ban_df is None:
        st.error("Upload trips.csv and ban_windows.csv, or keep demo mode enabled.")
        st.stop()

    result = run_ban_window(trips_df, ban_df, eta_df, visits_df, settings=settings)
    risk_path, conflict_path = write_outputs(result, OUTPUT_DIR)

    metric_cols = st.columns(6)
    _metric_card(metric_cols[0], "Trips", result.kpis["total_trips"])
    _metric_card(metric_cols[1], "Conflicts", result.kpis["conflict_trips"])
    _metric_card(metric_cols[2], "Watch", result.kpis["watch_trips"])
    _metric_card(metric_cols[3], "Needs data", result.kpis["missing_data_trips"])
    _metric_card(metric_cols[4], "Conflict rows", result.kpis["conflict_rows"])
    _metric_card(metric_cols[5], "Windows", result.kpis["expanded_windows"])

    chart_data = result.ban_risk_board.groupby(chart_by, dropna=False, as_index=False).size()
    chart_data = chart_data.rename(columns={"size": "trips"})
    chart = px.bar(
        chart_data,
        x=chart_by,
        y="trips",
        color=chart_by,
        color_discrete_map=STATUS_COLORS,
        text_auto=".0f",
    )
    chart.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(chart, use_container_width=True)

    tab_board, tab_conflicts, tab_windows, tab_exports, tab_notes = st.tabs(
        ["Risk board", "Conflicts", "Expanded windows", "Exports", "Notes"]
    )

    with tab_board:
        styled = result.ban_risk_board.style.map(_style_status, subset=["risk_status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    with tab_conflicts:
        st.dataframe(result.ban_conflicts, use_container_width=True, hide_index=True)

    with tab_windows:
        st.dataframe(result.expanded_windows, use_container_width=True, hide_index=True)

    with tab_exports:
        st.write(f"Wrote `{risk_path}` and `{conflict_path}`.")
        st.download_button(
            "Download ban_risk_board.csv",
            result.ban_risk_board.to_csv(index=False),
            "ban_risk_board.csv",
            "text/csv",
        )
        st.download_button(
            "Download ban_conflicts.csv",
            result.ban_conflicts.to_csv(index=False),
            "ban_conflicts.csv",
            "text/csv",
        )

    with tab_notes:
        st.subheader("Planning Use")
        st.write(
            "Use the risk status, matched window count, conflict count, and evidence fields "
            "to decide which trips need planning review."
        )
        st.subheader("Important Limitation")
        st.write(
            "BanWindow is deterministic and file-based. It does not contain legal rules, "
            "scrape regulations, issue permits, optimize routes, or send driver messages. "
            "Every restriction window must come from the uploaded CSV."
        )


if __name__ == "__main__":
    main()

