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
