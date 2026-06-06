"""Streamlit interface for TowerBrief."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from tower_brief.engine import SOURCE_FILES, read_input_directory, run_tower_brief, write_outputs
from tower_brief.models import TowerBriefSettings


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"
PRIORITY_COLORS = {"P1": "#b91c1c", "P2": "#ea580c", "P3": "#ca8a04", "P4": "#2563eb"}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame | None:
    if uploaded_file is None:
        return pd.read_csv(demo_path) if demo_path.exists() else None
    return pd.read_csv(uploaded_file)


def _metric_card(column, label: str, value: object) -> None:
    column.metric(label, value)


def _style_priority(value: str) -> str:
    color = PRIORITY_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def main() -> None:
    """Run the TowerBrief Streamlit app."""
    st.set_page_config(page_title="TowerBrief", layout="wide")
    st.title("TowerBrief")
    st.caption("Builds one deterministic daily management brief from local control-tower CSV outputs.")

    with st.sidebar:
        st.header("Inputs")
        uploaded = {
            source_file: st.file_uploader(
                f"{source_file} ({product_name})",
                type=["csv"],
            )
            for source_file, product_name in SOURCE_FILES.items()
        }
        st.header("Settings")
        settings = TowerBriefSettings(
            brief_date=st.text_input("Brief date", value="2026-06-06"),
            high_priority_limit=st.number_input("Top action limit", min_value=1, value=10),
            detention_exposure_threshold=st.number_input("High detention exposure threshold", min_value=0.0, value=500.0),
            fuel_liter_threshold=st.number_input("High fuel liters threshold", min_value=0.0, value=150.0),
        )
        run_button = st.button("Run TowerBrief", type="primary")

    st.info(
        "Demo mode uses synthetic product-output files only. TowerBrief creates local markdown, HTML, and CSV exports; "
        "it does not send emails, messages, tasks, carrier notices, or automated escalations."
    )

    if not run_button:
        st.stop()

    inputs = {
        source_file: _read_uploaded_or_demo(uploaded_file, DEMO_DIR / source_file)
        for source_file, uploaded_file in uploaded.items()
    }
    if not any(df is not None for df in inputs.values()):
        inputs = read_input_directory(DEMO_DIR)

    result = run_tower_brief(inputs, settings=settings)
    markdown_path, html_path, csv_path = write_outputs(result, OUTPUT_DIR)

    if result.config_warnings:
        st.warning("Config warnings: " + " | ".join(result.config_warnings))

    metrics = dict(zip(result.kpi_snapshot["metric"], result.kpi_snapshot["value"], strict=True))
    metric_cols = st.columns(7)
    _metric_card(metric_cols[0], "Trips", metrics["total_trips"])
    _metric_card(metric_cols[1], "Open actions", metrics["open_actions"])
    _metric_card(metric_cols[2], "Critical", metrics["critical_actions"])
    _metric_card(metric_cols[3], "High", metrics["high_actions"])
    _metric_card(metric_cols[4], "Customers", metrics["customers_exposed"])
    _metric_card(metric_cols[5], "Carriers", metrics["carriers_exposed"])
    _metric_card(metric_cols[6], "Exposure", metrics["financial_exposure"])

    if not result.action_table.empty:
        chart_data = result.action_table.groupby(["owner", "priority_bucket"], as_index=False).size()
        chart = px.bar(
            chart_data,
            x="owner",
            y="size",
            color="priority_bucket",
            color_discrete_map=PRIORITY_COLORS,
            text_auto=".0f",
        )
        chart.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Actions")
        st.plotly_chart(chart, use_container_width=True)

    tab_actions, tab_brief, tab_sources, tab_exports, tab_notes = st.tabs(
        ["Action table", "Brief", "Source coverage", "Exports", "Limitations"]
    )
    with tab_actions:
        styled = result.action_table.style.map(_style_priority, subset=["priority_bucket"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    with tab_brief:
        st.markdown(result.brief_markdown)
    with tab_sources:
        st.dataframe(result.source_status, use_container_width=True, hide_index=True)
        st.dataframe(result.kpi_snapshot, use_container_width=True, hide_index=True)
    with tab_exports:
        st.write(f"Wrote `{markdown_path}`, `{html_path}`, and `{csv_path}`.")
        st.download_button(
            "Download daily_control_tower_brief.md",
            result.brief_markdown,
            "daily_control_tower_brief.md",
            "text/markdown",
        )
        st.download_button(
            "Download daily_control_tower_brief.html",
            result.brief_html,
            "daily_control_tower_brief.html",
            "text/html",
        )
        st.download_button(
            "Download daily_control_tower_brief.csv",
            result.action_table.to_csv(index=False),
            "daily_control_tower_brief.csv",
            "text/csv",
        )
    with tab_notes:
        st.write(
            "TowerBrief is deterministic and file-based. It does not use AI-generated narrative, paid APIs, "
            "live integrations, automated emails, WhatsApp, Telegram, workflow engines, login systems, BI servers, "
            "or database backends."
        )


if __name__ == "__main__":
    main()
