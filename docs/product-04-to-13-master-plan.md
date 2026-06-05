# Product 04-13 Master Plan

This plan extends the public Transport Control Tower Lab repo from three shipped products to thirteen local-first logistics micro-products.

The scope is deliberately practical:

- local files only;
- no paid APIs;
- no secrets;
- no AI in v1;
- deterministic rules first;
- Streamlit + Python + Pandas for product apps;
- flat top-level product folders for future products.

## Observed Repo Pattern

The current repo has two patterns:

1. Product 1 lives inside the shared CLI package:
   - `src/control_tower_lab/cli.py`
   - `src/control_tower_lab/trip_sheet_doctor.py`
   - sample data under `data/samples/` and `demo_data/`
   - tests under `tests/test_trip_sheet_doctor.py`
   - Day 1 docs under `docs/day-01-trip-sheet-doctor.md`
   - visual under `docs/assets/trip-sheet-doctor-terminal.svg`
   - release entry under `docs/shipping-log.md`

2. Products 2 and 3 use a flat top-level product folder:
   - `georeplay/app.py`
   - `georeplay/engine.py`
   - `georeplay/models.py`
   - `georeplay/__init__.py`
   - `georeplay/demo_data/*.csv`
   - optional `georeplay/output/.gitkeep`
   - `eta_watch/app.py`
   - `eta_watch/engine.py`
   - `eta_watch/models.py`
   - `eta_watch/__init__.py`
   - `eta_watch/demo_data/*.csv`
   - `eta_watch/output/.gitkeep`

Future products should follow the Product 2 and Product 3 pattern, not a new `src/` layout.

Expected product folder shape:

```text
product_name/
  __init__.py
  app.py
  engine.py
  models.py
  demo_data/
    input_1.csv
    input_2.csv
  output/
    .gitkeep
```

Expected supporting repo changes per product:

```text
tests/test_product_name.py
docs/day-XX-product-name.md
docs/assets/product-name-streamlit.svg
README.md
docs/shipping-log.md
pyproject.toml
```

Observed implementation conventions:

- Keep deterministic business logic in `engine.py`.
- Keep Streamlit upload, display, chart, and download behavior in `app.py`.
- Keep Pydantic row contracts in `models.py` when useful.
- Normalize uploaded CSV column names to snake_case.
- Validate required columns with readable `ValueError` messages.
- Use Pandas DataFrames as the main data contract between engine functions.
- Standardize timestamps immediately after upload and before time math.
- Export review-ready CSV files into each product's `output/` folder.
- Add focused pytest coverage for the core rules and export smoke behavior.
- Add a product-specific README section, docs page, SVG visual, shipping-log entry, release tag, and public demo data.

## Product Sequence

### P4: DetentionClock

Folder: `detention_clock/`

Purpose: convert GeoReplay visit events and user-supplied detention rules into chargeable detention time.

Inputs:

- `visit_events.csv` from GeoReplay
- `detention_rules.csv`
- optional `trips.csv` for trip, carrier, origin, destination, and customer context

Core logic:

- Match each visit to a detention rule by geofence, site type, customer, lane, or default rule.
- Calculate free time, chargeable minutes, and detention status.
- Classify visits into `NO DETENTION`, `WATCH`, `CHARGEABLE`, and `RULE MISSING`.
- Keep rules user-supplied; no hardcoded contract terms.

Outputs:

- `detention_clock/output/detention_board.csv`
- `detention_clock/output/chargeable_detention.csv`

Tests:

- free-time logic
- chargeable time logic
- missing-rule logic
- timestamp/dwell handling
- export smoke

### P5: GateTruth

Folder: `gate_truth/`

Purpose: compare trip plans with GeoReplay visit events to verify whether origin and destination truth matches operational reality.

Inputs:

- `trips.csv`
- `visit_events.csv` from GeoReplay
- optional `site_aliases.csv`

Core logic:

- Determine whether a trip's vehicle visited the planned origin and destination.
- Compare origin gate events, destination gate events, and promised trip sequence.
- Flag missing origin, missing destination, wrong origin, wrong destination, and ambiguous matches.
- Keep the output evidence-first, with event IDs and timestamps.

Outputs:

- `gate_truth/output/gate_truth_board.csv`
- `gate_truth/output/gate_exceptions.csv`

Tests:

- origin verified
- destination verified
- missing origin
- wrong destination
- alias matching
- export smoke

### P6: FuelGuard

Folder: `fuel_guard/`

Purpose: reconcile fuel events with trips and GPS or visit evidence to highlight fuel exceptions.

Inputs:

- `fuel_events.csv`
- `trips.csv`
- optional `visit_events.csv` from GeoReplay
- optional `fuel_sites.csv`

Core logic:

- Normalize fuel timestamps, vehicles, liters, cost, odometer, and station fields.
- Match fuel events to active trips by vehicle and timestamp.
- Flag fuel outside trip window, unexpected station, duplicate fuel event, high liters, missing vehicle, and missing trip match.
- Use deterministic thresholds supplied by CSV or app controls.

Outputs:

- `fuel_guard/output/fuel_exception_board.csv`
- `fuel_guard/output/fuel_events_cleaned.csv`

Tests:

- trip-window matching
- duplicate event detection
- high-liter threshold
- no-trip-match logic
- export smoke

### P7: UpdatePulse

Folder: `update_pulse/`

Purpose: measure TMS update discipline by comparing planned trip milestones with actual user or system updates.

Inputs:

- `trips.csv`
- `tms_updates.csv`
- optional `update_rules.csv`

Core logic:

- Normalize update timestamps, trip IDs, update types, users, and notes.
- Calculate time since last update and milestone coverage.
- Classify trips as `CURRENT`, `STALE`, `MISSING UPDATE`, or `BAD SEQUENCE`.
- Identify teams, carriers, or lanes with poor update discipline.

Outputs:

- `update_pulse/output/update_discipline_board.csv`
- `update_pulse/output/stale_updates.csv`

Tests:

- stale update threshold
- missing update logic
- bad sequence logic
- user/team aggregation
- export smoke

### P8: DelayLens

Folder: `delay_lens/`

Purpose: classify operational delay reasons using trips, visit events, and lane or site baselines.

Inputs:

- `trips.csv`
- `visit_events.csv`
- `lane_baselines.csv`
- optional `delay_rules.csv`

Core logic:

- Compare actual dwell, departure, and arrival timing to baselines.
- Classify likely delay source as origin dwell, transit delay, destination dwell, late departure, no signal, or baseline missing.
- Keep labels deterministic and evidence-based.
- Avoid root-cause claims that the data cannot support.

Outputs:

- `delay_lens/output/delay_classification_board.csv`
- `delay_lens/output/delay_exceptions.csv`

Tests:

- origin dwell delay
- destination dwell delay
- transit delay
- baseline missing
- no-signal handling
- export smoke

### P9: PODPulse

Folder: `pod_pulse/`

Purpose: track proof-of-delivery aging and missing POD risk after trip completion.

Inputs:

- `trips.csv`
- `pod_status.csv`
- optional `pod_rules.csv`

Core logic:

- Normalize delivery, completion, POD received, and POD uploaded timestamps.
- Calculate POD age in hours or days.
- Classify as `RECEIVED`, `DUE SOON`, `OVERDUE`, `MISSING`, or `DATA GAP`.
- Surface carrier, customer, lane, and aging bucket summaries.

Outputs:

- `pod_pulse/output/pod_aging_board.csv`
- `pod_pulse/output/missing_pods.csv`

Tests:

- received POD
- overdue POD
- missing POD
- data-gap classification
- export smoke

### P10: LaneLab

Folder: `lane_lab/`

Purpose: build lane and milestone baselines from historical trips and visit events.

Inputs:

- `historical_trips.csv`
- `historical_visit_events.csv`
- optional `baseline_config.csv`

Core logic:

- Calculate historical transit and dwell durations by lane, origin, destination, carrier, and milestone.
- Produce p50, p75, and p90 baselines.
- Flag thin-sample baselines so downstream products do not overtrust weak history.
- Export baseline files usable by ETA Watch and DelayLens.

Outputs:

- `lane_lab/output/lane_baselines.csv`
- `lane_lab/output/site_dwell_baselines.csv`
- `lane_lab/output/baseline_quality_report.csv`

Tests:

- percentile calculation
- thin-sample flagging
- lane grouping
- timestamp normalization
- export smoke

### P11: BanWindow

Folder: `ban_window/`

Purpose: identify trips that may overlap user-supplied road, city, customer, or site ban windows.

Inputs:

- `trips.csv`
- `ban_windows.csv`
- optional `visit_events.csv`

Core logic:

- Use only user-supplied ban windows.
- Do not hardcode legal rules, country rules, city rules, holiday rules, or prayer-time assumptions.
- Normalize ban-window start and end timestamps to a single timezone.
- Match trips by lane, city, site, customer, carrier, or free-text scope fields.
- Classify as `CLEAR`, `WATCH`, `BAN OVERLAP`, or `RULE AMBIGUOUS`.

Outputs:

- `ban_window/output/ban_risk_board.csv`
- `ban_window/output/ban_overlap_trips.csv`

Tests:

- clear trip
- direct ban overlap
- ambiguous rule match
- timezone handling
- export smoke

### P12: CarrierScore

Folder: `carrier_score/`

Purpose: combine outputs from prior products into a carrier and lane SLA scorecard.

Inputs:

- `trips.csv`
- `eta_risk_board.csv`
- `detention_board.csv`
- `gate_exceptions.csv`
- `fuel_exception_board.csv`
- `pod_aging_board.csv`
- optional `score_weights.csv`

Core logic:

- Aggregate deterministic metrics by carrier, lane, customer, and period.
- Score on-time risk, detention exposure, gate truth, fuel exceptions, POD discipline, and update discipline.
- Use user-supplied weights with safe defaults.
- Keep score calculations explainable and export the metric components.

Outputs:

- `carrier_score/output/carrier_scorecard.csv`
- `carrier_score/output/carrier_metric_components.csv`

Tests:

- weighted score calculation
- missing input handling
- carrier aggregation
- component transparency
- export smoke

### P13: TowerBrief

Folder: `tower_brief/`

Purpose: turn all previous product outputs into a deterministic daily management brief in Markdown and HTML.

Inputs:

- `eta_risk_board.csv`
- `detention_board.csv`
- `gate_exceptions.csv`
- `fuel_exception_board.csv`
- `update_discipline_board.csv`
- `delay_classification_board.csv`
- `pod_aging_board.csv`
- `carrier_scorecard.csv`
- optional `brief_config.csv`

Core logic:

- Summarize the most important exceptions by severity, carrier, lane, customer, and owner.
- Build a deterministic narrative using templates, not AI.
- Include KPI tables, top exceptions, and action lists.
- Export a manager-ready `daily_management_brief.md` and `daily_management_brief.html`.

Outputs:

- `tower_brief/output/daily_management_brief.md`
- `tower_brief/output/daily_management_brief.html`
- `tower_brief/output/brief_inputs_audit.csv`

Tests:

- deterministic summary sections
- missing input handling
- Markdown export
- HTML export
- input audit export smoke

## Shared Helper Opportunities

The next ten products will repeat some logic. Shared helpers are worth adding only when the duplication becomes real across two or more products.

Potential shared helpers:

- CSV column normalization: trim, lowercase, snake_case, alias mapping.
- Required-column validation with clear manager-readable errors.
- Timestamp parsing and standardization to UTC.
- Operational text normalization for vehicle IDs, trip IDs, lane IDs, carrier names, site names, and city names.
- Risk bucket ordering and color maps for Streamlit tables.
- CSV export helpers that create product `output/` folders and return file paths.
- Streamlit upload helper that falls back to demo data.
- KPI card rendering helper.
- Download button helper for generated CSV outputs.
- Synthetic GCC demo-data conventions for trip IDs, vehicle IDs, carrier names, and lane names.
- Test fixtures for trips, visit events, lane baselines, and current-time injection.

Suggested timing:

- Keep P4 simple and local to its folder.
- After P5 or P6, extract only proven repeated utilities.
- Prefer a small `control_tower_lab/shared.py` or `control_tower_lab/io_helpers.py` over a large framework.
- Do not move future product apps into `src/`.

## Demo Data Strategy

All demo data should be public-safe, synthetic, and realistic for GCC transport operations.

Use realistic geography and lane names:

- Riyadh
- Jeddah
- Dammam
- Khobar
- Jubail
- Mecca
- Medina
- Qassim
- Abha
- Taif
- Dubai
- Abu Dhabi
- Doha
- Manama
- Kuwait City
- Muscat

Use realistic logistics entities without copying real confidential customer data:

- synthetic carriers such as `Najd Express`, `Red Sea Logistics`, `Gulf Bridge Transport`, `Eastern Fleet`, and `Desert Line Haul`;
- synthetic depots, gates, DCs, fuel stations, and customer sites;
- synthetic trip IDs, vehicle IDs, driver names if needed, and customer names;
- plausible timestamps, dwell times, delays, POD ages, fuel quantities, and update gaps.

Rules:

- No real customer data.
- No secrets.
- No live API references.
- No hardcoded legal, city, or country rules for BanWindow.
- `ban_windows.csv` must be user-supplied demo data only.
- Every dataset should include clean rows, edge cases, and exception rows so the Streamlit app shows every risk bucket during a demo.
- Demo files should run out of the box when no upload is provided.

## Release Standard For Each Product

Every product from P4 to P13 needs:

- `app.py`
- `engine.py`
- `models.py` when row validation helps
- `demo_data/*.csv`
- `output/.gitkeep`
- focused tests under `tests/test_product_name.py`
- CSV exports
- README update
- `docs/day-XX-product-name.md`
- `docs/assets/product-name-streamlit.svg`
- `docs/shipping-log.md` update
- release tag

Validation target per product:

```bash
uv run pytest
uv run ruff check .
uv run python -m py_compile product_name/app.py product_name/engine.py product_name/models.py
uv run streamlit run product_name/app.py
```

Public release checklist:

- demo data works without uploads;
- Streamlit app shows the expected risk or exception buckets;
- CSV export buttons generate the promised files;
- README explains user, problem, inputs, outputs, run steps, limitations, and before/after;
- docs page and visual match the existing Day 1-3 style;
- shipping log includes shipped items, why it matters, and validation commands;
- release tag follows `v0.X.0-product-name`.
