# Day 7: UpdatePulse

UpdatePulse is Product 7 in the Transport Control Tower Lab.

It audits TMS and driver update discipline against planned trip milestones and optional GeoReplay visit evidence. The output is a neutral review pack for control-tower teams checking whether operational updates are missing, late, early, duplicated, out of sequence, or unsupported by actual event evidence.

## User

- Control tower teams
- Dispatch teams
- Fleet operations managers
- Customer-service escalation teams

## Problem

A trip can be physically moving, waiting, delivered, or delayed while the TMS status remains outdated. Teams often compare trip plans, driver messages, TMS updates, and GPS visit evidence manually.

## Inputs

- `trips.csv`: required `trip_id`, `vehicle_id`, `origin`, `destination`, `planned_departure`, and `promised_arrival`; optional driver, carrier, and customer fields
- `tms_updates.csv` or `driver_updates.csv`: required `vehicle_id`, `update_time`, and `status`; optional trip, source, update ID, and note fields
- `visit_events.csv`: optional GeoReplay actual event evidence

## Outputs

- `update_pulse/output/update_discipline_report.csv`
- `update_pulse/output/update_exceptions.csv`

The report keeps expected milestone, planned time, matched update time, delay minutes, actual event evidence, update count, review status, exception type, evidence text, and suggested action.

## Rules

- Reconstruct expected origin departure and destination arrival milestones from each trip.
- Match departure-like updates against planned departure.
- Match arrival or delivery-like updates against promised arrival.
- Flag `missing update` when a milestone has no matching update.
- Flag `late update` when a matched update is after the configured grace.
- Flag `early update` when a matched update is too early for review.
- Flag `duplicate update` when multiple updates match the same milestone.
- Flag `sequence issue` when trip updates move backward in operational order.
- Flag `no actual event evidence` when visit evidence was supplied but no matching event supports the milestone.

## Review Language

UpdatePulse deliberately uses neutral language such as update gap, needs review, sequence issue, and no actual event evidence. It does not frame exceptions as driver punishment or make disciplinary decisions.

## Run

```bash
uv sync
uv run streamlit run update_pulse/app.py
```

The app loads synthetic GCC demo data from `update_pulse/demo_data/` when no files are uploaded.

Screenshot reference: `docs/assets/update-pulse-streamlit.svg`.

## Validation

```bash
uv run pytest
uv run ruff check .
uv run python -m py_compile update_pulse/app.py update_pulse/engine.py update_pulse/models.py
```

## Limitations

- No live TMS, driver app, WhatsApp, or telematics integration.
- Status matching is deterministic and based on common update labels.
- Sparse visit evidence can create review cases that need human context.
- Outputs are operational review flags, not performance penalties.

## Future Ideas

- Add configurable milestone templates per customer or carrier.
- Add SLA-specific escalation aging.
- Add weekly update-discipline summary packs for dispatch standups.
