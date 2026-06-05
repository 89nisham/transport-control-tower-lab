# Day 10: LaneLab

LaneLab is a local-first Streamlit app for building lane travel-time baselines from historical trips and GeoReplay visit events.

## Business Problem

ETA, delay, and SLA tools need realistic lane baselines. Many teams still rely on planner memory, old lane assumptions, or one-off spreadsheet averages.

LaneLab creates a neutral lane baseline board for:

- lane travel-time profiles;
- p50, p75, and p90 travel-time baselines;
- usable and invalid sample counts;
- low-sample lanes;
- unstable lanes;
- outlier trips;
- data-quality review cases.

## Inputs

`historical_trips.csv` requires:

- `trip_id`
- `vehicle_id`
- `origin`
- `destination`
- `lane_id` optional
- `customer_name` optional
- `carrier_name` optional
- `planned_departure` optional
- `promised_arrival` optional

`historical_visit_events.csv` requires:

- `vehicle_id`
- `geofence_id`
- `geofence_name`
- `geofence_type`
- `enter_time`
- `exit_time`
- `dwell_minutes`
- `trip_id` optional

## Logic

LaneLab matches trips to GeoReplay visits using exact `trip_id` first. When visit events do not include a trip ID, it falls back to vehicle ID and the planned trip time window.

Origin events use `ORIGIN`, `HUB`, `PICKUP`, or an origin name match. Destination events use `DESTINATION`, `CUSTOMER`, `DELIVERY`, or a destination name match.

The baseline duration is:

- `actual_destination_entry - actual_origin_exit`

Missing, zero, or negative durations are excluded from baseline percentiles but kept in each lane's invalid trip count.

Default settings:

- low sample threshold: 5 trips
- unstable p90/p50 ratio threshold: 1.5
- outlier IQR multiplier: 1.5
- extreme duration minimum: 30 minutes
- extreme duration maximum: 2880 minutes
- minimum usable trips for percentile calculation: 2

Confidence buckets:

- `GOOD`
- `LOW SAMPLE`
- `UNSTABLE`
- `CHECK DATA`
- `NO BASELINE`

## Outputs

`lane_baselines.csv` includes:

- lane, origin, destination, customer, and carrier context
- sample size, usable trip count, and invalid trip count
- p50, p75, p90, average, minimum, maximum, and standard deviation minutes
- outlier count
- confidence bucket
- evidence and suggested action

`lane_outliers.csv` includes trip-level duration outliers with event timestamps, severity, evidence, and suggested action.

## Demo Data

The demo pack uses GCC-style logistics lanes:

- Riyadh Dry Port to Dammam DC with enough consistent samples;
- Jeddah Port to Riyadh DC with low sample size and vehicle-window matching;
- Doha Hub to Muscat DC with an unstable p90/p50 ratio;
- Dubai JAFZA to Abu Dhabi Store with a clear high-duration outlier;
- Kuwait DC to Doha Retail Hub with missing origin and destination evidence;
- Bahrain Hub to Dammam DC with a negative duration;
- Medina DC to Tabuk Store with no usable baseline;
- customer-specific and carrier-specific lane groupings.

## Run

```bash
uv sync
uv run streamlit run lane_lab/app.py
```

## Before And After

Before LaneLab, ETA and SLA assumptions often depend on planner memory or outdated lane targets.

After LaneLab, historical trip files and GeoReplay visit events produce a deterministic lane baseline pack with percentile travel times, sample confidence, outlier evidence, and data-quality notes.

## Limitations

- LaneLab is deterministic and file-based.
- It uses synthetic demo data only.
- It does not call traffic APIs, optimize routes, train ML models, or connect to live systems.
- It does not decide commercial liability or root cause.
- Results depend on historical trip and GeoReplay visit-event quality.
