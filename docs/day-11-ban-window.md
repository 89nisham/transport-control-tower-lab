# Day 11: BanWindow

BanWindow is a local-first Streamlit app for checking planned trips against user-uploaded restriction windows.

## Business Problem

Truck bans, city restrictions, port windows, mall receiving windows, and restricted access periods can break delivery plans before dispatch or before arrival.

BanWindow creates a neutral planning board for:

- restriction-window conflicts;
- watch cases near uploaded windows;
- missing timing;
- missing city;
- vehicle-class uncertainty;
- concrete conflict rows for planner review.

## Legal Boundary

BanWindow does not include hard-coded laws, scrape regulations, claim legal compliance, or provide legal advice. Every restriction window comes from the uploaded `ban_windows.csv` file or the synthetic demo file.

## Inputs

`trips.csv` requires:

- `trip_id`
- `vehicle_id`
- `origin`
- `destination`
- `planned_departure`
- `promised_arrival`
- `customer_name` optional
- `carrier_name` optional
- `city` optional
- `vehicle_class` optional
- `planned_city_entry` optional
- `planned_city_exit` optional

`ban_windows.csv` requires:

- `ban_id`
- `city`
- `start_time`
- `end_time`
- `location_name` optional
- `vehicle_class` optional
- `days_of_week` optional
- `effective_from` optional
- `effective_to` optional
- `rule_note` optional

Optional supporting files:

- `eta_risk_board.csv` with `trip_id`, optional `predicted_arrival`, `risk_status`, and `latest_event_time`
- `visit_events.csv` with optional GeoReplay-style visit evidence

## Logic

BanWindow builds a movement interval per trip in this order:

- planned city entry and exit when both exist;
- planned departure to predicted arrival when ETA data exists;
- earliest matching visit event to promised arrival when visit evidence exists;
- planned departure to promised arrival as the default.

It expands user-supplied restriction windows into concrete UTC intervals. Full datetime windows are used directly. Time-of-day windows are expanded across the trip date range, filtered by `days_of_week`, `effective_from`, and `effective_to`.

Matching is by city first. When a restriction window has a vehicle class, it applies only to matching trip classes. If the trip vehicle class is missing, BanWindow marks the row as `VEHICLE CLASS UNKNOWN`.

Risk statuses:

- `CLEAR`
- `CONFLICT`
- `WATCH`
- `MISSING TIMING`
- `MISSING CITY`
- `VEHICLE CLASS UNKNOWN`

## Outputs

`ban_risk_board.csv` includes trip context, movement interval, timing source, matched window count, conflict count, watch count, risk status, severity, evidence, and suggested action.

`ban_conflicts.csv` includes one row per trip and uploaded restriction-window overlap, with ban window details, overlap minutes, match type, evidence, and suggested action.

## Demo Data

The demo pack uses GCC-style synthetic planning rows:

- clear Riyadh trip outside the uploaded restriction window;
- Riyadh heavy-vehicle overlap;
- Jeddah watch case near a receiving window;
- missing timing;
- missing city;
- Doha vehicle-class uncertainty;
- Muscat ETA-based overlap;
- Kuwait planned city-window overlap;
- Abu Dhabi visit-event fallback overlap;
- Jeddah all-vehicle window overlap.

## Run

```bash
uv sync
uv run streamlit run ban_window/app.py
```

## Before And After

Before BanWindow, planners often notice city, port, or site restriction conflicts late in the planning cycle.

After BanWindow, uploaded trip plans and uploaded restriction windows produce a deterministic review board before dispatch or arrival.

## Limitations

- BanWindow is deterministic and file-based.
- It uses synthetic demo data only.
- It does not include legal rules or legal advice.
- It does not call live traffic, legal, permit, route-optimization, or messaging APIs.
- Results depend entirely on the quality and completeness of the uploaded files.

