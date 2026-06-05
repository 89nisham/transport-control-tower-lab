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
- `tms_updates.csv` or `driver_updates.csv`: required `trip_id`, `update_time`, and `status`; optional vehicle, updater, and source fields
- `visit_events.csv`: optional GeoReplay actual event evidence

## Outputs

- `update_pulse/output/update_discipline_report.csv`
- `update_pulse/output/update_exceptions.csv`

The report keeps expected status, expected time, matched update time, actual status, source, updater, delay minutes, update gap type, sequence status, evidence status, risk bucket, severity, evidence text, and suggested action.

## Rules

- Reconstruct `ASSIGNED`, `ARRIVED_ORIGIN`, `DEPARTED_ORIGIN`, `ARRIVED_DESTINATION`, `DELIVERED`, and optional `POD_COLLECTED` milestones from each trip.
- Match TMS or driver updates by trip and expected status.
- Use origin enter, origin exit, destination enter, and destination exit from visit evidence where available.
- Flag `MISSING UPDATE` when a milestone has no matching update.
- Flag `LATE UPDATE` when a matched update is after the comparison time by more than tolerance.
- Flag `EARLY UPDATE` when a matched update is too early, especially before supported actual event evidence.
- Flag `DUPLICATE UPDATE` when repeated same-status updates create timeline noise.
- Flag `OUT OF SEQUENCE` when trip updates move backward in operational order.
- Flag `NO ACTUAL EVENT EVIDENCE` when visit evidence was supplied but no matching event supports the milestone.

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
- Status matching is deterministic and expects the UpdatePulse status contract; unusual TMS codes need mapping before upload.
- Sparse visit evidence can create review cases that need human context.
- Outputs are operational review flags, not performance penalties.

## Future Ideas

- Add configurable milestone templates per customer or carrier.
- Add SLA-specific escalation aging.
- Add weekly update-discipline summary packs for dispatch standups.
