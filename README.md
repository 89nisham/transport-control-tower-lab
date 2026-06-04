# Transport Control Tower Lab

Open-source Python CLI for practical logistics control-tower automation.

The goal is not to replace a TMS. The goal is to turn messy operational files into clean events, explainable exceptions, and useful review packs that transport teams can act on.

## Day 1 Micro-Product: Trip Sheet Doctor

Trip Sheet Doctor diagnoses messy Excel/CSV trip sheets and creates an exception workbook for operations review.

It is built as the first micro-tool inside the shared Control Tower CLI.

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
data/samples/               Public-safe sample files
data/input/                 Operator-provided raw files, ignored by git
data/output/                Generated outputs, ignored by git
tests/                      Unit and CLI smoke tests
docs/                       Product notes and build logs
```

## Public Story

This repo is the start of an open-source Transport Control Tower toolkit.

Day 1 is Trip Sheet Doctor: a CLI tool that turns messy trip sheets into an explainable exception pack.
