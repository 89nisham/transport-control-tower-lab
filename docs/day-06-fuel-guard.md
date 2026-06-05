# Day 6: FuelGuard

FuelGuard is Product 6 in the Transport Control Tower Lab.

It reconciles uploaded fuel transactions against GPS point evidence, GeoReplay visit events, known fuel-site coordinates, and optional trip windows. The output is a first-pass review pack for control-tower and fleet teams.

## User

- Control tower teams
- Fleet operations managers
- Fuel desk analysts
- Carrier-management teams

## Problem

Fuel reports alone do not prove that a vehicle was near the fuel site, stopped long enough, or operating on the assigned trip. Teams often review receipt files, GPS exports, and trip rows in separate spreadsheets.

## Inputs

- `fuel_events.csv`: required `fuel_event_id`, `vehicle_id`, `fuel_time`, `liters`; optional station, receipt, amount, odometer, driver, carrier, trip, and location fields
- `visit_events.csv`: optional GeoReplay stop evidence
- `gps_points.csv`: optional GPS point evidence
- `fuel_sites.csv`: optional station master with coordinates and radius
- `trips.csv`: optional trip windows

## Outputs

- `fuel_guard/output/fuel_reconciliation_report.csv`
- `fuel_guard/output/fuel_exceptions.csv`

The report keeps matched evidence type, matched event time, matched geofence, GPS coordinates, station distance, stop evidence, trip-window status, exception flags, risk bucket, severity, evidence text, and suggested action.

## Rules

- Match fuel event to known site by station ID, then station name, then nearby coordinates.
- Find nearby GPS points for the same vehicle inside the configured time window.
- Find GeoReplay fuel-stop visits for the same vehicle around the fuel time.
- Flag `NO GPS EVIDENCE` when no visit event and no GPS point support the vehicle near the fuel time.
- Flag `NO STOP NEAR FUEL` when GPS or visit evidence exists but stop evidence is false.
- Flag `UNKNOWN STATION` when station details are missing or no fuel-site master match is found.
- Flag `DUPLICATE RECEIPT` for repeated receipt numbers on the same or different vehicle.
- Flag `ODOMETER DROP` when odometer readings move backward for a vehicle.
- Flag `HIGH LITERS` for unusually large fills.
- Flag `OUTSIDE TRIP WINDOW` when optional trip context shows the event is outside the assigned trip.

## Risk Buckets

- `OK`: supporting evidence is present and no exception flags were found.
- `REVIEW`: medium-severity review cases such as no stop near fuel, high liters, or unknown station.
- `HIGH RISK`: high-priority review cases such as duplicate receipt, odometer drop, or outside trip window.
- `DATA MISSING`: no usable GPS or visit evidence exists near the fuel time.

## Review Language

FuelGuard deliberately uses review-safe language. It does not accuse theft, post to ERP, contact drivers, or trigger disciplinary workflows. It creates evidence rows for human review.

## Run

```bash
uv sync
uv run streamlit run fuel_guard/app.py
```

The app loads synthetic GCC demo data from `fuel_guard/demo_data/` when no files are uploaded.

Screenshot reference: `docs/assets/fuel-guard-streamlit.svg`.

## Validation

```bash
uv run pytest
uv run ruff check .
uv run python -m py_compile fuel_guard/app.py fuel_guard/engine.py fuel_guard/models.py
```

## Limitations

- No fuel card integration.
- No payment reconciliation or ERP posting.
- No legal proof engine or theft accusation workflow.
- No live telematics integration.
- Sparse GPS data can create false review cases.

## Future Ideas

- Add tank-capacity reference data for better high-liter thresholds.
- Add vehicle-level rolling fuel baselines.
- Add a daily exception-pack summary for control-tower standups.
