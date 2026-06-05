# Day 4: DetentionClock

## Problem Card

Control tower teams can reconstruct site visits, but detention billing still needs a careful local review layer:

- Which visits exceeded free time?
- Which visits are close to free-time expiry?
- Which visits are missing exit evidence?
- Which chargeable cases need customer, carrier, and site context?
- What is the estimated detention exposure before invoice review?

## Stakeholder

- Control tower analyst
- Dispatch manager
- Fleet operations manager
- Transport manager
- Billing and customer-service teams

## Input Contract

DetentionClock accepts:

- `visit_events.csv`: `trip_id`, `vehicle_id`, `geofence_id`, `geofence_name`, `geofence_type`, `enter_time`, `exit_time`, `dwell_minutes`
- `detention_rules.csv`: `rule_id`, `customer_name`, `geofence_type`, optional `geofence_id`, `free_minutes`, `rate_type`, `rate_per_hour`, optional `minimum_charge`, `currency`
- `trips.csv`: optional `trip_id`, `customer_name`, `carrier_name`, `origin`, `destination`, `planned_arrival`, `planned_departure`

## Core Logic

The app uses deterministic detention rules:

- Standardize visit and trip timestamps to UTC immediately after CSV load.
- Join visit events to optional trip context by `trip_id`.
- Match detention rules by customer, geofence ID, and geofence type, with more specific rules taking priority.
- Calculate chargeable minutes as dwell time after free time.
- Apply hourly rates and minimum charges only when chargeable minutes are greater than zero.
- Classify each visit into `MISSING EXIT`, `NO DETENTION`, `WITHIN FREE TIME`, `APPROACHING FREE TIME`, or `DETENTION`.

## Output

DetentionClock writes:

- `detention_clock/output/detention_report.csv`
- `detention_clock/output/chargeable_detention.csv`

The Streamlit app also shows:

- KPI cards
- Plotly detention charge chart by customer or geofence type
- Detention report table
- Chargeable-only table
- Download buttons for both CSV exports

## Limitations

- V1 is local-first and file-based.
- No billing-system integration, live GPS feed, notification workflow, enterprise login, or database backend is included.
- Detention rules must be supplied by the user; no contract terms or legal rules are hardcoded.
- Missing exits are flagged for evidence review and are not charged automatically.
- Estimated charges are for control-tower review, not final invoicing.

## Public Learning

Detention review becomes operationally useful when dwell evidence, customer rules, and charge estimates are shown together. The manager gets a clean split between missing evidence, watchlist dwell, and chargeable cases without turning the tool into a billing system.
