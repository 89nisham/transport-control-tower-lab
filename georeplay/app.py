"""Streamlit interface for GeoReplay geofence visit reconstruction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from georeplay.engine import create_map, reverse_geocode_locations, run_georeplay


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR / "demo_data"
OUTPUT_DIR = APP_DIR / "output"


def _read_uploaded_or_demo(uploaded_file, demo_path: Path) -> pd.DataFrame:
    """Read an uploaded CSV or fall back to the bundled demo data."""
    if uploaded_file is None:
        return pd.read_csv(demo_path)
    return pd.read_csv(uploaded_file)


def _download_csv(label: str, df: pd.DataFrame, filename: str) -> None:
    """Render a Streamlit CSV download button for an output dataframe."""
    st.download_button(
        label=label,
        data=df.to_csv(index=False),
        file_name=filename,
        mime="text/csv",
    )


def main() -> None:
    """Run the GeoReplay Streamlit application."""
    st.set_page_config(page_title="GeoReplay", page_icon="🛰️", layout="wide")
    st.title("GeoReplay")
    st.caption("Reconstruct geofence visit events from GPS pings for transport control towers.")

    with st.sidebar:
        st.header("Inputs")
        gps_file = st.file_uploader("gps_points.csv", type=["csv"])
        geofence_file = st.file_uploader("geofences.csv", type=["csv"])
        planned_stops_file = st.file_uploader("planned_stops.csv (optional)", type=["csv"])
        long_dwell_minutes = st.number_input("Long dwell threshold minutes", 15, 240, 45, step=5)
        enrich_locations = st.checkbox(
            "Reverse-geocode geofences/events only",
            value=False,
            help="Uses Nominatim with a 1-second delay. Raw GPS pings are never reverse-geocoded.",
        )
        run_button = st.button("Run GeoReplay", type="primary")

    st.info(
        "No upload needed for the demo: GeoReplay loads synthetic GPS pings, geofences, "
        "and planned stops from `georeplay/demo_data/`."
    )

    if not run_button:
        st.stop()

    gps_df = _read_uploaded_or_demo(gps_file, DEMO_DIR / "gps_points.csv")
    geofence_df = _read_uploaded_or_demo(geofence_file, DEMO_DIR / "geofences.csv")
    planned_df = _read_uploaded_or_demo(planned_stops_file, DEMO_DIR / "planned_stops.csv")

    result = run_georeplay(
        gps_df,
        geofence_df,
        planned_df,
        long_dwell_minutes=float(long_dwell_minutes),
    )
    geofences = result.geofences
    visit_events = result.visit_events
    exceptions = result.exceptions

    if enrich_locations:
        with st.spinner("Reverse-geocoding geofences and final events only..."):
            geofences = reverse_geocode_locations(
                geofences,
                "center_lat",
                "center_lon",
                "reverse_geocoded_name",
            )
            visit_events = reverse_geocode_locations(
                visit_events,
                "event_lat",
                "event_lon",
                "reverse_geocoded_location",
            )
            exceptions = reverse_geocode_locations(
                exceptions,
                "event_lat",
                "event_lon",
                "reverse_geocoded_location",
            )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    visit_path = OUTPUT_DIR / "visit_events.csv"
    exceptions_path = OUTPUT_DIR / "exceptions.csv"
    visit_events.to_csv(visit_path, index=False)
    exceptions.to_csv(exceptions_path, index=False)

    metric_cols = st.columns(4)
    metric_cols[0].metric("GPS pings", len(result.gps_points))
    metric_cols[1].metric("Geofences", len(result.geofences))
    metric_cols[2].metric("Visit events", len(visit_events))
    metric_cols[3].metric("Exceptions", len(exceptions))

    tab_events, tab_exceptions, tab_map, tab_exports = st.tabs(
        ["Visit Events", "Exceptions", "Map", "Exports"]
    )

    with tab_events:
        st.dataframe(visit_events, use_container_width=True)

    with tab_exceptions:
        st.dataframe(exceptions, use_container_width=True)

    with tab_map:
        fmap = create_map(result.gps_points, result.geofences, visit_events)
        components.html(fmap.get_root().render(), height=650)

    with tab_exports:
        st.write(f"Wrote `{visit_path}` and `{exceptions_path}`.")
        _download_csv("Download visit_events.csv", visit_events, "visit_events.csv")
        _download_csv("Download exceptions.csv", exceptions, "exceptions.csv")


if __name__ == "__main__":
    main()
