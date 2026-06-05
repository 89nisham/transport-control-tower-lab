# Shipping Log

## v0.1.0-trip-sheet-doctor

Date: 2026-06-04

### Shipped

- Created the shared Transport Control Tower CLI.
- Added Trip Sheet Doctor as the first micro-product.
- Added deterministic checks for missing trip fields, duplicate trip IDs, invalid pickup/delivery times, same origin/destination, and long planned durations.
- Generated an Excel exception workbook with summary, exceptions, correction suggestions, cleaned trips, and column mapping sheets.
- Added public-safe sample data, tests, and Day 1 documentation.

### Why It Matters

Trip sheets are the base layer for ETA, GPS reconciliation, fuel checks, SLA reporting, and daily control-tower reviews. If the trip sheet is messy, every downstream workflow inherits that mess.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run control-tower trip-sheet-doctor data/samples/trip_sheet_doctor_sample.csv data/output/trip_sheet_doctor_demo.xlsx`

### Public Note

Day 1 is intentionally small: one painful operations file, one deterministic review workflow, one explainable output workbook.

## v0.2.0-georeplay

Date: 2026-06-04

### Shipped

- Added `georeplay/` as a separate Streamlit micro-product folder.
- Added deterministic geofence visit reconstruction from GPS pings and circular geofence master data.
- Added planned-stop exception detection for missed stops and unexpected geofence visits.
- Added long-dwell detection with a configurable threshold.
- Added Folium map rendering for pings, geofences, and reconstructed visits.
- Added optional Nominatim reverse geocoding for final geofence/event/exception records only, never raw GPS pings.
- Added synthetic demo data and tests.
- Added README GeoReplay visual and product-specific Before/After section.
- Tagged the public release as `v0.2.0-georeplay`.

### Why It Matters

GPS pings become useful when they are converted into control-tower events: entry, exit, dwell, missed stop, and unexpected visit.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile georeplay/app.py georeplay/engine.py georeplay/models.py`
- Demo smoke run writes `georeplay/output/visit_events.csv` and `georeplay/output/exceptions.csv`

## v0.3.0-eta-watch

Date: 2026-06-04

### Shipped

- Added `eta_watch/` as a separate Streamlit micro-product folder.
- Added deterministic ETA risk calculation from trip rows and GeoReplay visit events.
- Standardized all uploaded timestamps to UTC before ETA math.
- Added optional lane baseline support for remaining-time estimates.
- Added fallback remaining-time rules when no lane baseline is available.
- Added KPI cards, Plotly risk distribution chart, color-coded risk table, trip detail view, and CSV downloads.
- Added synthetic demo data and tests.
- Added README ETA Watch visual and product-specific Before/After section.
- Tagged the public release as `v0.3.0-eta-watch`.

### Why It Matters

Control towers need to move from manual ETA checking to a risk board that separates safe trips from watchlist, at-risk, late, and no-signal trips.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile eta_watch/app.py eta_watch/engine.py eta_watch/models.py`
- Demo smoke run writes `eta_watch/output/eta_risk_board.csv` and `eta_watch/output/late_trips.csv`

## v0.4.0-detention-clock

Date: 2026-06-05

### Shipped

- Added `detention_clock/` as a separate Streamlit micro-product folder.
- Added deterministic detention calculation from GeoReplay visit events and user-supplied detention rules.
- Standardized visit and trip timestamps to UTC before dwell and rule review.
- Added optional trip context for customer, carrier, origin, and destination fields.
- Added free-time, approaching-free-time, missing-exit, chargeable-minute, hourly-rate, and minimum-charge logic.
- Added KPI cards, Plotly charge chart, detention table, chargeable-only table, and CSV downloads.
- Added synthetic GCC demo data and tests.
- Added README DetentionClock visual and product-specific Before/After section.
- Tagged the public release as `v0.4.0-detention-clock`.

### Why It Matters

Detention billing disputes start when dwell evidence, free-time rules, and charge estimates are reviewed separately. DetentionClock gives the control tower a local evidence board before billing or customer escalation.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile detention_clock/app.py detention_clock/engine.py detention_clock/models.py`
- Demo smoke run writes `detention_clock/output/detention_report.csv` and `detention_clock/output/chargeable_detention.csv`

## v0.5.0-gate-truth

Date: 2026-06-05

### Shipped

- Added `gate_truth/` as a separate Streamlit micro-product folder.
- Added deterministic origin and destination gate evidence matching from trips and GeoReplay visit events.
- Standardized trip, visit, and planned-stop timestamps to UTC before gate-time comparisons.
- Added optional planned-stop support for geofence matching when trip geofence IDs are missing.
- Added missing-origin-exit, missing-destination-entry, late-start, late-arrival, early-arrival, no-visit-evidence, and ambiguous-match flags.
- Added evidence text, confidence buckets, exception severity, KPI cards, Plotly gate-truth-status chart, gate truth table, exceptions table, and CSV downloads.
- Added synthetic GCC demo data and tests.
- Added README GateTruth visual and product-specific Before/After section.

### Why It Matters

Start and arrival disputes waste control-tower time when TMS timestamps, GPS visits, and planned stops are reviewed separately. GateTruth gives managers an evidence-first local board for actual origin exit and destination entry truth.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile gate_truth/app.py gate_truth/engine.py gate_truth/models.py`
- Demo smoke run writes `gate_truth/output/gate_truth_report.csv` and `gate_truth/output/gate_exceptions.csv`

## v0.6.0-fuel-guard

Date: 2026-06-05

### Shipped

- Added `fuel_guard/` as a separate Streamlit micro-product folder.
- Added deterministic fuel transaction reconciliation against GPS points, GeoReplay visit events, fuel-site masters, and optional trip windows.
- Standardized fuel, GPS, visit, and trip timestamps to UTC before matching.
- Added known-site matching by station ID, station name, and nearby coordinates.
- Added no-GPS-evidence, no-stop-near-fuel, unknown-station, duplicate-receipt, odometer-drop, high-liters, and outside-trip-window review flags.
- Added evidence text, risk buckets, exception severity, KPI cards, Plotly review chart, reconciliation table, exceptions table, and CSV downloads.
- Added synthetic GCC demo data and tests.
- Added README FuelGuard visual and product-specific Before/After section.

### Why It Matters

Fuel reports become useful control-tower evidence only when they are reviewed beside vehicle location, stop dwell, known station coordinates, and trip windows. FuelGuard creates that first-pass review pack without making accusations or touching payment workflows.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile fuel_guard/app.py fuel_guard/engine.py fuel_guard/models.py`
- Demo smoke run writes `fuel_guard/output/fuel_reconciliation_report.csv` and `fuel_guard/output/fuel_exceptions.csv`

## v0.7.0-update-pulse

Date: 2026-06-05

### Shipped

- Added `update_pulse/` as a separate Streamlit micro-product folder.
- Added deterministic update-discipline review from trip plans, TMS or driver updates, and optional GeoReplay visit evidence.
- Standardized trip, update, and visit timestamps to UTC before milestone matching.
- Added expected ASSIGNED, ARRIVED_ORIGIN, DEPARTED_ORIGIN, ARRIVED_DESTINATION, DELIVERED, and optional POD_COLLECTED milestone reconstruction.
- Added missing-update, late-update, early-update, duplicate-update, sequence-issue, and no-actual-event-evidence flags.
- Added neutral review language, risk buckets, evidence status, sequence status, KPI cards, Plotly charts, update report table, exceptions table, and CSV downloads.
- Added synthetic GCC demo data and tests.
- Added README UpdatePulse visual and product-specific Before/After section.

### Why It Matters

Status discipline breaks down when planned milestones, TMS rows, driver updates, and actual visit evidence are reviewed separately. UpdatePulse gives the control tower a neutral local board for stale or unsupported updates before customer escalation.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile update_pulse/app.py update_pulse/engine.py update_pulse/models.py`
- Demo smoke run writes `update_pulse/output/update_discipline_report.csv` and `update_pulse/output/update_exceptions.csv`

## v0.8.0-delay-lens

Date: 2026-06-05

### Shipped

- Added `delay_lens/` as a separate Streamlit micro-product folder.
- Added deterministic delay classification from trip plans, GeoReplay visit events, and optional lane baselines.
- Standardized trip, visit, and baseline timestamps before delay math.
- Added exact trip matching first, then vehicle and trip-window matching when visit `trip_id` is missing.
- Added late departure, origin dwell, hub dwell, enroute delay, destination dwell, missing signal, baseline missing, and late arrival fallback classifications.
- Added critical arrival-delay escalation at the 120-minute threshold.
- Added neutral evidence text, secondary delay flags, risk buckets, severity, KPI cards, Plotly charts, classification table, critical table, and CSV downloads.
- Added synthetic GCC demo data and tests.
- Added README DelayLens visual and product-specific Before/After section.

### Why It Matters

Late trips are easier to act on when managers can see where time was lost. DelayLens turns trip plans, GeoReplay visits, and lane baselines into a neutral review board for departure, dwell, travel, signal, and baseline issues.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile delay_lens/app.py delay_lens/engine.py delay_lens/models.py`
- Demo smoke run writes `delay_lens/output/delay_classification_report.csv` and `delay_lens/output/critical_delays.csv`

## v0.9.0-pod-pulse

Date: 2026-06-05

### Shipped

- Added `pod_pulse/` as a separate Streamlit micro-product folder.
- Added deterministic POD aging from delivered trips, POD status rows, and optional invoice status rows.
- Standardized delivery, POD, approval, rejection, resubmission, and invoice timestamps to UTC before aging math.
- Added POD missing, POD overdue, POD late, POD rejected, POD resubmitted, invoice blocked, POD not required, OK, not delivered, and data missing classifications.
- Added 24-hour warning, 48-hour SLA, and 168-hour critical POD aging thresholds.
- Added neutral evidence text, aging buckets, invoice blocker flag, risk buckets, severity, KPI cards, Plotly charts, POD aging table, overdue POD table, and CSV downloads.
- Added 10-scenario synthetic GCC demo data and tests.
- Added README PODPulse visual and product-specific Before/After section.

### Why It Matters

Delivered trips are not financially complete until POD evidence is received, usable, and approved. PODPulse gives operations and billing teams a local review board for POD gaps, aging, rejected documents, approval pending cases, and invoice blockers.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile pod_pulse/app.py pod_pulse/engine.py pod_pulse/models.py`
- Demo smoke run writes `pod_pulse/output/pod_aging_report.csv` and `pod_pulse/output/overdue_pods.csv`

## v0.10.0-lane-lab

Date: 2026-06-05

### Shipped

- Added `lane_lab/` as a separate Streamlit micro-product folder.
- Added deterministic lane baseline generation from historical trips and GeoReplay visit events.
- Standardized trip and visit timestamps to UTC before travel-time math.
- Added exact trip-ID matching first, then vehicle and trip-window matching when visit `trip_id` is missing.
- Added origin event matching by `ORIGIN`, `HUB`, `PICKUP`, or origin name match.
- Added destination event matching by `DESTINATION`, `CUSTOMER`, `DELIVERY`, or destination name match.
- Added p50, p75, p90, average, minimum, maximum, standard deviation, sample-size, invalid-trip, and outlier calculations.
- Added confidence buckets for good, low-sample, unstable, check-data, and no-baseline lanes.
- Added neutral evidence text, suggested actions, KPI cards, Plotly charts, baseline table, outlier table, trip-duration table, and CSV downloads.
- Added synthetic GCC demo data and tests.
- Added README LaneLab visual and product-specific Before/After section.

### Why It Matters

ETA, delay, and SLA review workflows need realistic lane travel-time profiles. LaneLab turns historical trip files and GeoReplay visit events into local percentile baselines with confidence and data-quality context.

### Validation

- `uv run pytest`
- `uv run ruff check .`
- `uv run python -m py_compile lane_lab/app.py lane_lab/engine.py lane_lab/models.py`
- Demo smoke run writes `lane_lab/output/lane_baselines.csv` and `lane_lab/output/lane_outliers.csv`
