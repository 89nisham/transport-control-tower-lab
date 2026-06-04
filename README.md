# Transport Control Tower Lab

Open-source Python CLI for practical logistics control-tower automation.

The goal is not to replace a TMS. The goal is to turn messy operational files into clean events, explainable exceptions, and useful review packs that transport teams can act on.

## Day 1 Micro-Product: Trip Sheet Doctor

Trip Sheet Doctor diagnoses messy Excel/CSV trip sheets and creates an exception workbook for operations review.

It is built as the first micro-tool inside the shared Control Tower CLI.

![Trip Sheet Doctor terminal screenshot](docs/assets/trip-sheet-doctor-terminal.svg)

### Who It Is For

- Control tower teams
- Dispatch teams
- Fleet operations managers
- Transport managers
- Anyone cleaning trip sheets before reporting, SLA checks, or GPS/fuel reconciliation

### What It Checks

- Missing trip IDs
- Missing vehicle or door numbers
- Missing origin/destination
- Missing pickup or delivery timestamps
- Delivery time earlier than pickup time
- Duplicate trip IDs
- Same origin and destination
- Very long planned trip duration

### Output Workbook

- `summary`: row count, exception count, exception rate, and exception mix
- `exceptions`: explainable exception cases with severity, evidence, owner, action, and review status
- `correction_suggestions`: source columns and mapping gaps to review
- `cleaned_trips`: normalized trip rows with source row numbers preserved
- `column_map`: source-to-canonical field mapping used by the run

## Day 2 Micro-Product: GeoReplay

GeoReplay is a local-first Streamlit app that reconstructs operational geofence visit events from GPS pings.

### Who It Is For

- Control tower teams
- Dispatch teams
- Fleet operations managers
- Transport managers
- Anyone checking whether vehicles entered planned depots, hubs, customer sites, or fuel stations

### Problem

Raw GPS pings are hard to review directly. A manager usually needs the event layer:

- Did the vehicle enter the site?
- When did it enter and exit?
- How long did it dwell?
- Which planned stops were missed?
- Which geofence visits were unexpected?

### Inputs

- `gps_points.csv`: `vehicle_id`, `timestamp`, `lat`, `lon`, optional `speed_kph`
- `geofences.csv`: `geofence_id`, `name`, `lat`, `lon`, `radius_m`, optional `geofence_type`
- `planned_stops.csv`: optional plan with `vehicle_id`, `geofence_id`, optional `planned_arrival`, `stop_sequence`

### Outputs

- `georeplay/output/visit_events.csv`
- `georeplay/output/exceptions.csv`
- Interactive Folium map inside Streamlit

### Run GeoReplay

```bash
uv sync
cd georeplay
uv run streamlit run app.py
```

The app loads synthetic demo data from `georeplay/demo_data/` when no files are uploaded.

### GeoReplay Limitations

- V1 supports circular geofences from latitude, longitude, and radius.
- It is local-first and file-based; no live GPS integrations are included.
- Sparse GPS data can understate dwell or miss short visits.
- Reverse geocoding is optional and only applies to geofence master rows, final visit events, and final exception locations. Raw GPS pings are never reverse-geocoded.

## Quick Start

Install dependencies:

```bash
uv sync
```

Run the demo:

```bash
uv run control-tower trip-sheet-doctor \
  data/samples/trip_sheet_doctor_sample.csv \
  data/output/trip_sheet_doctor_demo.xlsx
```

Try the intentionally messy demo files:

```bash
uv run control-tower trip-sheet-doctor \
  demo_data/messy_branch_trip_sheet.csv \
  data/output/messy_branch_trip_sheet.xlsx

uv run control-tower trip-sheet-doctor \
  demo_data/duplicate_and_bad_times.csv \
  data/output/duplicate_and_bad_times.xlsx

uv run control-tower trip-sheet-doctor \
  demo_data/column_mapping_gaps.csv \
  data/output/column_mapping_gaps.xlsx
```

Run tests:

```bash
uv run pytest
```

## CLI Commands

```bash
uv run control-tower init
uv run control-tower clean-tms input.csv data/output/tms_cleaned.xlsx
uv run control-tower clean-gps input.csv data/output/gps_cleaned.xlsx
uv run control-tower trip-sheet-doctor input.csv data/output/trip_sheet_doctor.xlsx
uv run control-tower exceptions input.csv data/output/exceptions.xlsx
uv run control-tower weekly-output data/output/weekly_control_tower_summary.xlsx
uv run control-tower telegram-summary input.csv
```

## Build-In-Public Framework

Each micro-product follows the same lean journey:

1. Problem card
2. Stakeholder
3. Input contract
4. Deterministic rule layer
5. Exception output
6. Demo data
7. Smoke test
8. Public learning note

## Project Shape

```text
src/control_tower_lab/      Python package and CLI
georeplay/                  Product 2 Streamlit app and geospatial engine
data/samples/               Public-safe sample files
demo_data/                  Intentionally messy public demo files
data/input/                 Operator-provided raw files, ignored by git
data/output/                Generated outputs, ignored by git
tests/                      Unit and CLI smoke tests
docs/                       Product notes and build logs
```

## Before / After

Before:

- Trip sheets arrive with inconsistent column names like `Trip No`, `shipment_no`, `Truck`, `door_number`, `Pickup Time`, and `eta`.
- Required fields may be blank.
- Duplicate trip IDs are easy to miss.
- Delivery time can be earlier than pickup time.
- Same-origin/same-destination rows hide in the sheet.
- Analysts spend review time finding basic data quality issues instead of acting on them.

After:

- The CLI maps common messy source columns into canonical trip fields.
- Each source row is preserved with a `source_row` reference.
- Exceptions are written into a review workbook with severity, evidence, owner, suggested action, and review status.
- The output workbook includes `summary`, `exceptions`, `correction_suggestions`, `cleaned_trips`, and `column_map`.
- Teams get a clear exception pack before ETA, GPS, fuel, SLA, or weekly reporting work begins.

## Python Libraries

- `pandas`: reads, normalizes, validates, groups, and exports operational tabular data.
- `openpyxl`: supports Excel workbook output for operations teams that still review in spreadsheets.
- `typer`: provides the command-line interface.
- `rich`: makes terminal output readable during demos and local runs.
- `loguru`: keeps lightweight operational logs.
- `pytest`: validates the core behavior.
- `ruff`: checks code quality before shipping.
- `streamlit`: runs the GeoReplay local app.
- `geopandas`: handles geospatial tables and coordinate reference systems.
- `shapely`: builds and checks geofence geometry.
- `geopy`: reverse-geocodes only geofence/event/exception locations when explicitly enabled.
- `folium`: renders the interactive map.
- `pydantic`: validates GeoReplay input records.

## Public Story

This repo is the start of an open-source Transport Control Tower toolkit.

Day 1 is Trip Sheet Doctor: a CLI tool that turns messy trip sheets into an explainable exception pack.

Day 2 is GeoReplay: a Streamlit app that turns GPS pings and geofence masters into visit events and exceptions.

See [docs/shipping-log.md](docs/shipping-log.md) for the build log.
