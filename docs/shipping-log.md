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
