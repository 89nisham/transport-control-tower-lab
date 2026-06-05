# Day 5: GateTruth

## Problem Card

Control tower teams often need operational proof before they can trust TMS milestone timestamps:

- Did the truck actually enter the origin hub?
- Did it actually exit the origin before the planned departure?
- Did it enter the destination customer site?
- Was the destination entry late against the promised arrival?
- Are there multiple plausible gate events that need human review?

## Stakeholder

- Control tower analyst
- Dispatch manager
- Fleet operations manager
- Transport manager
- Customer-service escalation teams

## Input Contract

GateTruth accepts:

- `trips.csv`: `trip_id`, `vehicle_id`, optional `customer_name`, optional `carrier_name`, `origin`, `destination`, optional `origin_geofence_id`, optional `destination_geofence_id`, `planned_departure`, `promised_arrival`
- `visit_events.csv`: GeoReplay output with optional `trip_id`, `vehicle_id`, `geofence_id`, `geofence_name`, `geofence_type`, `enter_time`, `exit_time`, `dwell_minutes`
- `planned_stops.csv`: optional `trip_id`, `vehicle_id`, `geofence_id`, `stop_sequence`, `stop_type`, optional `planned_arrival`, optional `planned_departure`

## Core Logic

The app uses deterministic evidence rules:

- Standardize trip, visit, and planned-stop timestamps to UTC immediately after CSV load.
- Match origin and destination visits by vehicle and trip context.
- Prefer explicit trip geofence IDs.
- Fall back to planned-stop geofence IDs when trip geofence IDs are missing.
- Fall back to geofence type and site-name hints when no explicit geofence IDs exist.
- Select the visit closest to planned departure for origin exit evidence.
- Select the visit closest to promised arrival for destination entry evidence.
- Flag missing origin exits, missing destination entries, late starts, late arrivals, early arrivals, no visit evidence, and ambiguous matches.
- Default tolerances are 15 minutes for late start, 15 minutes for late arrival, and 60 minutes for early-arrival review.

## Output

GateTruth writes:

- `gate_truth/output/gate_truth_report.csv`
- `gate_truth/output/gate_exceptions.csv`

The Streamlit app also shows:

- KPI cards
- Plotly gate-truth-status chart
- Full gate truth report table
- Exceptions-only table
- Download buttons for both CSV exports

## Limitations

- V1 is local-first and file-based.
- No live GPS polling, TMS integration, customer notification workflow, route optimization, legal proof engine, enterprise login, or database backend is included.
- Ambiguous matches are flagged for review instead of auto-resolved with hidden assumptions.
- Late start, late arrival, and early-arrival review thresholds are configurable in the app.

## Public Learning

Gate evidence becomes useful when it is shown as timestamps, status, exception type, evidence text, and confidence bucket instead of scattered GPS events. GateTruth gives managers a local evidence pack for start and arrival truth without turning the product into a legal or enterprise workflow system.
