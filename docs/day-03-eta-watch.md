# Day 3: ETA Watch

## Problem Card

Control tower teams can clean trip sheets and reconstruct geofence visit events, but they still need a daily answer to the question managers ask first:

- Which trips are likely to miss planned ETA?
- Which trips need a dispatcher check now?
- Which trips have no usable signal?
- Which late trips need a customer-facing update?

## Stakeholder

- Control tower analyst
- Dispatch manager
- Fleet operations manager
- Transport manager
- Customer-service escalation owner

## Input Contract

ETA Watch accepts:

- `trips.csv`: `trip_id`, `vehicle_id`, `origin`, `destination`, optional `lane_id`, optional `planned_departure`, `promised_arrival`
- `visit_events.csv`: GeoReplay output with `vehicle_id`, optional `geofence_id`, optional `geofence_name`, optional `entry_time`, `exit_time`
- `lane_baselines.csv`: optional baseline with `lane_id`, optional `from_geofence_id`, optional `to_destination`, optional `remaining_minutes_after_geofence`, optional `default_remaining_minutes`

## Core Logic

The app uses deterministic ETA rules:

- Standardize uploaded timestamps to UTC immediately after CSV load.
- Match each trip to the latest GeoReplay visit event by vehicle.
- Estimate remaining time from lane/geofence baselines when available.
- Use a simple fallback remaining time when no baseline exists.
- Calculate predicted ETA and ETA delta against promised arrival.
- Classify each trip into `ON TRACK`, `WATCH`, `AT RISK`, `LATE`, or `NO SIGNAL`.

## Output

ETA Watch writes:

- `eta_watch/output/eta_risk_board.csv`
- `eta_watch/output/late_trips.csv`

The Streamlit app also shows:

- KPI cards
- Plotly risk distribution chart
- Color-coded ETA risk board
- Trip detail panel
- Download buttons for both CSV exports

## Limitations

- V1 is local-first and file-based.
- No live GPS feed, traffic API, route optimization, SMS/email notification, driver app, enterprise login, or database backend is included.
- Remaining-time estimates depend on lane baselines when provided.
- Sparse or delayed GeoReplay events can create false `NO SIGNAL` or outdated ETA risk.
- Deterministic buckets are designed for operational triage, not customer promise automation.

## Public Learning

ETA visibility becomes useful when it is framed as a risk board: a manager can scan the fleet, focus on `WATCH`, `AT RISK`, `LATE`, and `NO SIGNAL`, and avoid manually checking trip rows one by one.

