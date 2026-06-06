"""Streamlit interface for CarrierScore."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from carrier_score.engine import run_carrier_score, write_outputs
from carrier_score.models import CarrierScoreSettings


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
STATUS_COLORS = {
    "EXCELLENT": "#15803d",
    "GOOD": "#2563eb",
    "WATCH": "#ca8a04",
    "AT RISK": "#dc2626",
    "INSUFFICIENT DATA": "#64748b",
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
    """Run the CarrierScore Streamlit app."""
    st.set_page_config(page_title="CarrierScore", layout="wide")
    st.title("CarrierScore")
    st.caption("Builds a neutral carrier SLA scorecard from trip files and optional exception outputs.")

    with st.sidebar:
        st.header("Inputs")
        trips_file = st.file_uploader("trips.csv", type=["csv"])
        delay_file = st.file_uploader("delay_classification_report.csv (optional)", type=["csv"])
        pod_file = st.file_uploader("pod_aging_report.csv (optional)", type=["csv"])
        detention_file = st.file_uploader("detention_report.csv (optional)", type=["csv"])
        update_file = st.file_uploader("update_discipline_report.csv (optional)", type=["csv"])
        fuel_file = st.file_uploader("fuel_exceptions.csv (optional)", type=["csv"])
        gate_file = st.file_uploader("gate_truth_report.csv (optional)", type=["csv"])
        ban_file = st.file_uploader("ban_risk_board.csv (optional)", type=["csv"])
        rules_file = st.file_uploader("carrier_score_rules.csv (optional)", type=["csv"])

        st.header("Settings")
        allow_rules = st.checkbox("Allow uploaded scoring rules", value=True)
        settings = CarrierScoreSettings(
            minimum_trips_for_reliable_score=st.number_input(
                "Minimum trips for reliable score",
                min_value=1,
                value=3,
            ),
            excellent_threshold=st.slider("Excellent threshold", 0, 100, 90),
            good_threshold=st.slider("Good threshold", 0, 100, 75),
            watch_threshold=st.slider("Watch threshold", 0, 100, 60),
            detention_exposure_high_threshold=st.number_input(
                "High detention exposure threshold",
                min_value=0.0,
                value=500.0,
                step=100.0,
            ),
            allow_uploaded_scoring_rules=allow_rules,
        )
        chart_by = st.selectbox(
            "Chart by",
            ["score", "risk_bucket", "carrier_name", "top_issue", "confidence_bucket"],
        )
        run_button = st.button("Run CarrierScore", type="primary")

    st.info(
        "Demo mode uses synthetic operational files only. CarrierScore creates a local SLA review board; "
        "it does not create penalty invoices, legal claims, vendor messages, or procurement records."
    )

    if not run_button:
        st.stop()

    trips_df = _read_uploaded_or_demo(trips_file, DEMO_DIR / "trips.csv")
    if trips_df is None:
        st.error("Upload trips.csv, or keep the synthetic demo file available.")
        st.stop()

    result = run_carrier_score(
        trips_df,
        _read_uploaded_or_demo(delay_file, DEMO_DIR / "delay_classification_report.csv"),
        _read_uploaded_or_demo(pod_file, DEMO_DIR / "pod_aging_report.csv"),
        _read_uploaded_or_demo(detention_file, DEMO_DIR / "detention_report.csv"),
        _read_uploaded_or_demo(update_file, DEMO_DIR / "update_discipline_report.csv"),
        _read_uploaded_or_demo(fuel_file, DEMO_DIR / "fuel_exceptions.csv"),
        _read_uploaded_or_demo(gate_file, DEMO_DIR / "gate_truth_report.csv"),
        _read_uploaded_or_demo(ban_file, DEMO_DIR / "ban_risk_board.csv"),
        _read_uploaded_or_demo(rules_file, DEMO_DIR / "carrier_score_rules.csv"),
        settings=settings,
    )
    scorecard_path, summary_path = write_outputs(result, OUTPUT_DIR)

    if result.config_warnings:
        st.warning("Scoring rule warnings: " + " | ".join(result.config_warnings))

    metric_cols = st.columns(7)
    _metric_card(metric_cols[0], "Carriers", result.kpis["total_carriers"])
    _metric_card(metric_cols[1], "Trips", result.kpis["total_trips"])
    _metric_card(metric_cols[2], "At risk", result.kpis["at_risk_carriers"])
    _metric_card(metric_cols[3], "Watch", result.kpis["watch_carriers"])
    _metric_card(metric_cols[4], "Avg score", result.kpis["average_carrier_score"])
    _metric_card(metric_cols[5], "Lowest score", result.kpis["lowest_carrier_score"])
    _metric_card(metric_cols[6], "Insufficient", result.kpis["insufficient_data_carriers"])

    if chart_by == "score":
        chart = px.bar(
            result.carrier_scorecard,
            x="carrier_name",
            y="score",
            color="risk_bucket",
            color_discrete_map=STATUS_COLORS,
            text_auto=".1f",
        )
    else:
        chart_data = result.carrier_scorecard.groupby(chart_by, dropna=False, as_index=False).size()
        chart_data = chart_data.rename(columns={"size": "carriers"})
        chart = px.bar(
            chart_data,
            x=chart_by,
            y="carriers",
            color=chart_by,
            color_discrete_map=STATUS_COLORS,
            text_auto=".0f",
        )
    chart.update_layout(showlegend=False, height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(chart, use_container_width=True)

    tab_scorecard, tab_summary, tab_exports, tab_read, tab_notes = st.tabs(
        ["Scorecard", "Exception summary", "Exports", "How to read this", "Limitations"]
    )
    with tab_scorecard:
        styled = result.carrier_scorecard.style.map(_style_status, subset=["risk_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    with tab_summary:
        st.dataframe(result.carrier_exception_summary, use_container_width=True, hide_index=True)
    with tab_exports:
        st.write(f"Wrote `{scorecard_path}` and `{summary_path}`.")
        st.download_button(
            "Download carrier_scorecard.csv",
            result.carrier_scorecard.to_csv(index=False),
            "carrier_scorecard.csv",
            "text/csv",
        )
        st.download_button(
            "Download carrier_exception_summary.csv",
            result.carrier_exception_summary.to_csv(index=False),
            "carrier_exception_summary.csv",
            "text/csv",
        )
    with tab_read:
        st.write(
            "Start with the confidence bucket, then read the score, top issue, evidence, and exception summary. "
            "A low score with limited data should be treated as a review prompt, not a final vendor judgment."
        )
    with tab_notes:
        st.write(
            "CarrierScore is deterministic and file-based. It does not contact carriers, change procurement "
            "systems, calculate penalties, create legal claims, or use live integrations."
        )


if __name__ == "__main__":
    main()
