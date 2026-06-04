"""Unit tests for ETA Watch risk classification and exports."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from eta_watch.engine import build_eta_risk_board, run_eta_watch, write_outputs


CURRENT_TIME = "2026-06-04T07:00:00Z"


def _trips() -> pd.DataFrame:
    """Build a mixed ETA-risk trip fixture."""
    return pd.DataFrame(
        [
            {
                "trip_id": "T-ON",
                "vehicle_id": "VH-1",
                "origin": "Riyadh DC",
                "destination": "Dammam",
                "lane_id": "RUH-DMM",
                "planned_departure": "2026-06-04T02:00:00Z",
                "promised_arrival": "2026-06-04T10:00:00Z",
            },
            {
                "trip_id": "T-WATCH",
                "vehicle_id": "VH-2",
                "origin": "Riyadh DC",
                "destination": "Qassim",
                "lane_id": "RUH-QSM",
                "planned_departure": "2026-06-04T02:00:00Z",
                "promised_arrival": "2026-06-04T09:00:00Z",
            },
            {
                "trip_id": "T-RISK",
                "vehicle_id": "VH-3",
                "origin": "Riyadh DC",
                "destination": "Jeddah",
                "lane_id": "RUH-JED",
                "planned_departure": "2026-06-04T01:00:00Z",
                "promised_arrival": "2026-06-04T10:00:00Z",
            },
            {
                "trip_id": "T-LATE",
                "vehicle_id": "VH-4",
                "origin": "Jeddah DC",
                "destination": "Mecca",
                "lane_id": "JED-MAK",
                "planned_departure": "2026-06-04T01:00:00Z",
                "promised_arrival": "2026-06-04T06:30:00Z",
            },
            {
                "trip_id": "T-NOSIGNAL",
                "vehicle_id": "VH-5",
                "origin": "Riyadh DC",
                "destination": "Khobar",
                "lane_id": "RUH-KHB",
                "planned_departure": "2026-06-04T03:00:00Z",
                "promised_arrival": "2026-06-04T12:00:00Z",
            },
        ]
    )


def _visit_events() -> pd.DataFrame:
    """Build latest GeoReplay event fixtures for four vehicles."""
    return pd.DataFrame(
        [
            {
                "vehicle_id": "VH-1",
                "geofence_id": "RUH_GATE",
                "geofence_name": "Riyadh Exit Gate",
                "entry_time": "2026-06-04T04:00:00+03:00",
                "exit_time": "2026-06-04T05:00:00+03:00",
                "dwell_minutes": 60,
            },
            {
                "vehicle_id": "VH-2",
                "geofence_id": "RUH_GATE",
                "geofence_name": "Riyadh Exit Gate",
                "entry_time": "2026-06-04T04:00:00Z",
                "exit_time": "2026-06-04T06:30:00Z",
                "dwell_minutes": 15,
            },
            {
                "vehicle_id": "VH-3",
                "geofence_id": "RUH_GATE",
                "geofence_name": "Riyadh Exit Gate",
                "entry_time": "2026-06-04T03:00:00Z",
                "exit_time": "2026-06-04T04:00:00Z",
                "dwell_minutes": 20,
            },
            {
                "vehicle_id": "VH-4",
                "geofence_id": "JED_GATE",
                "geofence_name": "Jeddah Exit Gate",
                "entry_time": "2026-06-04T04:00:00Z",
                "exit_time": "2026-06-04T05:00:00Z",
                "dwell_minutes": 20,
            },
        ]
    )


def _baselines() -> pd.DataFrame:
    """Build baseline fixtures that produce distinct risk buckets."""
    return pd.DataFrame(
        [
            {
                "lane_id": "RUH-DMM",
                "from_geofence_id": "RUH_GATE",
                "to_destination": "Dammam",
                "remaining_minutes_after_geofence": 120,
            },
            {
                "lane_id": "RUH-QSM",
                "from_geofence_id": "RUH_GATE",
                "to_destination": "Qassim",
                "remaining_minutes_after_geofence": 170,
            },
            {
                "lane_id": "RUH-JED",
                "from_geofence_id": "RUH_GATE",
                "to_destination": "Jeddah",
                "remaining_minutes_after_geofence": 450,
            },
            {
                "lane_id": "JED-MAK",
                "from_geofence_id": "JED_GATE",
                "to_destination": "Mecca",
                "remaining_minutes_after_geofence": 90,
            },
        ]
    )


def test_eta_watch_assigns_expected_risk_buckets() -> None:
    """ETA Watch should classify every deterministic risk bucket."""
    board = build_eta_risk_board(_trips(), _visit_events(), _baselines(), CURRENT_TIME)

    buckets = dict(zip(board["trip_id"], board["risk_bucket"], strict=False))
    assert buckets["T-ON"] == "ON TRACK"
    assert buckets["T-WATCH"] == "WATCH"
    assert buckets["T-RISK"] == "AT RISK"
    assert buckets["T-LATE"] == "LATE"
    assert buckets["T-NOSIGNAL"] == "NO SIGNAL"


def test_no_signal_trip_has_no_predicted_eta() -> None:
    """Trips without a matching latest event should stay in no-signal state."""
    board = build_eta_risk_board(_trips(), _visit_events(), _baselines(), CURRENT_TIME)
    no_signal = board[board["trip_id"] == "T-NOSIGNAL"].iloc[0]

    assert no_signal["risk_bucket"] == "NO SIGNAL"
    assert pd.isna(no_signal["predicted_eta"])


def test_late_trip_uses_current_time_against_promised_arrival() -> None:
    """Already expired promised arrivals should become late."""
    board = build_eta_risk_board(_trips(), _visit_events(), _baselines(), CURRENT_TIME)
    late = board[board["trip_id"] == "T-LATE"].iloc[0]

    assert late["risk_bucket"] == "LATE"
    assert late["minutes_until_promised"] < 0


def test_uploaded_timestamps_are_standardized_to_utc() -> None:
    """Mixed timezone offsets should be standardized before ETA math."""
    board = build_eta_risk_board(_trips(), _visit_events(), _baselines(), CURRENT_TIME)
    on_track = board[board["trip_id"] == "T-ON"].iloc[0]

    assert str(on_track["latest_event_time"]) == "2026-06-04 02:00:00+00:00"
    assert str(on_track["promised_arrival"]) == "2026-06-04 10:00:00+00:00"


def test_eta_watch_exports_smoke(tmp_path: Path) -> None:
    """ETA Watch should write risk-board and late-trip CSV exports."""
    result = run_eta_watch(_trips(), _visit_events(), _baselines(), CURRENT_TIME)
    risk_path, late_path = write_outputs(result, tmp_path)

    assert risk_path.exists()
    assert late_path.exists()
    assert "eta_risk_board" in risk_path.name
    assert not pd.read_csv(late_path).empty
