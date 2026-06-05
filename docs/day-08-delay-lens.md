# Day 8: DelayLens

DelayLens is a local-first Streamlit app for classifying LTL and linehaul delay causes from trips, GeoReplay visit events, and optional lane baselines.

## Business Problem

Managers often know a trip is late, but not why. DelayLens separates likely delay locations without blame language:

- late departure;
- origin dwell;
- hub dwell;
- enroute delay;
- destination dwell;
- missing signal;
- baseline missing.

The output is a review board for operations teams, not a root-cause verdict.

## Inputs

`trips.csv` requires:

- `trip_id`
- `vehicle_id`
- `customer_name` optional
- `carrier_name` optional
- `lane_id` optional
- `origin`
- `destination`
- `planned_departure`
- `promised_arrival`

`visit_events.csv` requires:

- `trip_id` optional
- `vehicle_id`
- `geofence_id`
- `geofence_name`
- `geofence_type`
- `enter_time`
- `exit_time`
- `dwell_minutes`

`lane_baselines.csv` is optional:

- `lane_id`
- `origin`
- `destination`
- `baseline_minutes`
- `p50_minutes` optional
- `p75_minutes` optional
- `p90_minutes` optional
- `sample_size` optional

## Matching Logic

DelayLens prefers exact `trip_id` matches in `visit_events.csv`.

When `trip_id` is missing, it falls back to `vehicle_id` and a trip time window from 6 hours before planned departure to 24 hours after promised arrival.

Origin events match by geofence type `ORIGIN`, `HUB`, `PICKUP`, or origin name. Destination events match by geofence type `DESTINATION`, `CUSTOMER`, `DELIVERY`, or destination name. Hub dwell sums intermediate `HUB`, `CROSSDOCK`, `DEPOT`, `WAREHOUSE`, and `PORT` events.

## Outputs

`delay_classification_report.csv` includes:

- trip, vehicle, customer, carrier, lane, origin, and destination context
- planned departure and promised arrival
- actual origin exit and destination entry
- departure and arrival delay minutes
- origin, hub, and destination dwell minutes
- travel minutes
- baseline minutes and baseline delta
- primary delay reason and secondary delay flags
- risk bucket, severity, evidence, and suggested action

`critical_delays.csv` includes critical and high severity rows for focused review.

## Demo Data

The demo pack uses GCC-style logistics scenarios:

- clean Dubai to Riyadh linehaul;
- late departure from Jeddah;
- long origin dwell at Jeddah Port;
- hub dwell at Hofuf Crossdock;
- enroute delay from Dammam to Riyadh;
- destination dwell in Dubai;
- missing GeoReplay signal;
- missing lane baseline for Bahrain to Riyadh;
- critical late arrival from Muscat to Dubai.

## Run

```bash
uv sync
uv run streamlit run delay_lens/app.py
```

## Before And After

Before DelayLens, the control tower can see that a trip is late but must manually inspect trip plans, visit events, and baselines to understand where time was lost.

After DelayLens, the same files produce a neutral classification report with delay reason, secondary flags, evidence text, and suggested next action.

## Limitations

- DelayLens is deterministic and file-based.
- It does not assign blame, infer traffic, or prove root cause.
- It depends on trip timestamp quality, GeoReplay event coverage, and baseline coverage.
- Baseline missing is a review signal, not a final operating diagnosis.
