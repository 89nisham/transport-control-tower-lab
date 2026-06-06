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
PRIORITY_COLORS = {
    "CRITICAL": "#b91c1c",
    "HIGH": "#ea580c",
    "MEDIUM": "#ca8a04",
    "LOW": "#2563eb",
    "DATA GAP": "#64748b",
}


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame | None:
    if uploaded_file is None:
        return pd.read_csv(demo_path) if demo_path.exists() else None
    return pd.read_csv(uploaded_file)


def _metric_card(column, label: str, value: object) -> None:
    column.metric(label, value)


def _style_priority(value: str) -> str:
    color = PRIORITY_COLORS.get(value, "#334155")
    return f"background-color: {color}; color: white; font-weight: 700"


def _chart(data: pd.DataFrame, column: str, title: str) -> None:
    if data.empty or column not in data.columns:
        return
    chart_data = data.groupby(column, dropna=False, as_index=False).size()
    chart = px.bar(chart_data, x=column, y="size", color=column, title=title, text_auto=".0f")
    chart.update_layout(height=300, margin=dict(l=10, r=10, t=44, b=10), showlegend=False, yaxis_title="Rows")
    st.plotly_chart(chart, use_container_width=True)


def main() -> None:
    """Run the TowerBrief Streamlit app."""
    st.set_page_config(page_title="TowerBrief", layout="wide")
    st.title("TowerBrief")
    st.caption("Daily control-tower management brief from local product-output CSVs.")

    with st.sidebar:
        st.header("Inputs")
        uploaded = {
            source_file: st.file_uploader(f"{source_file} ({product_name})", type=["csv"])
            for source_file, product_name in SOURCE_FILES.items()
        }
        st.header("Thresholds")
        settings = TowerBriefSettings(
            brief_date=st.text_input("Brief date", value="2026-06-06"),
            critical_detention_exposure=st.number_input("Critical detention exposure", min_value=0.0, value=1000.0),
            high_detention_exposure=st.number_input("High detention exposure", min_value=0.0, value=500.0),
            critical_ban_overlap_minutes=st.number_input("Critical ban overlap minutes", min_value=0.0, value=120.0),
            critical_pod_age_hours=st.number_input("Critical POD age hours", min_value=0.0, value=168.0),
            max_critical_rows=st.number_input("Max critical rows in brief", min_value=1, value=20),
            max_high_priority_rows=st.number_input("Max high priority rows in brief", min_value=1, value=20),
        )
        run_button = st.button("Run TowerBrief", type="primary")

    st.info(
        "Demo mode uses synthetic product-output files only. TowerBrief creates local markdown, HTML, and CSV exports; "
        "it does not send email, WhatsApp, Telegram, tasks, carrier messages, or automated escalations."
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
    _metric_card(metric_cols[0], "Critical", metrics["critical_actions"])
    _metric_card(metric_cols[1], "High", metrics["high_priority_actions"])
    _metric_card(metric_cols[2], "Detention exposure", metrics["estimated_detention_exposure"])
    _metric_card(metric_cols[3], "POD blockers", metrics["pod_invoice_blockers"])
    _metric_card(metric_cols[4], "Ban conflicts", metrics["ban_conflicts"])
    _metric_card(metric_cols[5], "Carrier watchlist", metrics["carrier_watchlist_count"])
    _metric_card(metric_cols[6], "Data gaps", metrics["data_gaps"])

    chart_cols = st.columns(2)
    with chart_cols[0]:
        _chart(result.action_table, "priority", "Actions by priority")
        _chart(result.action_table, "source_product", "Actions by source product")
    with chart_cols[1]:
        _chart(result.action_table, "owner", "Actions by owner")
        _chart(result.action_table[result.action_table["carrier_name"] != ""], "carrier_name", "Actions by carrier")
    _chart(result.action_table[result.action_table["customer_name"] != ""], "customer_name", "Actions by customer")

    tab_brief, tab_actions, tab_sources, tab_gaps, tab_read, tab_limits, tab_exports = st.tabs(
        ["Brief preview", "Action table", "Source coverage", "Data gaps", "How to read this", "Limitations", "Exports"]
    )
    with tab_brief:
        st.markdown(result.brief_markdown)
    with tab_actions:
        styled = result.action_table.style.map(_style_priority, subset=["priority"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    with tab_sources:
        st.dataframe(result.source_status, use_container_width=True, hide_index=True)
        st.dataframe(result.kpi_snapshot, use_container_width=True, hide_index=True)
    with tab_gaps:
        st.dataframe(result.data_gaps, use_container_width=True, hide_index=True)
    with tab_read:
        st.write(
            "Start with Critical Actions and High Priority Actions, then use owner and source-product views to assign the "
            "daily follow-up. Data gaps explain what is missing before anyone treats the brief as complete."
        )
    with tab_limits:
        st.write(
            "TowerBrief is deterministic and file-based. It does not use AI-generated narrative, paid APIs, live "
            "integrations, email, WhatsApp, Telegram, workflow engines, login systems, BI servers, or databases."
        )
    with tab_exports:
        st.write(f"Wrote `{markdown_path}`, `{html_path}`, and `{csv_path}`.")
        st.download_button("Download daily_control_tower_brief.md", result.brief_markdown, "daily_control_tower_brief.md")
        st.download_button("Download daily_control_tower_brief.html", result.brief_html, "daily_control_tower_brief.html")
        st.download_button(
            "Download daily_control_tower_brief.csv",
            result.action_table.to_csv(index=False),
            "daily_control_tower_brief.csv",
            "text/csv",
        )


if __name__ == "__main__":
    main()
