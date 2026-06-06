# Day 13: TowerBrief

TowerBrief is a local-first Streamlit app and CLI for generating a daily control-tower management brief from previous product-output CSVs.

## Business Problem

Managers do not want 12 separate CSV files every morning. They need one deterministic brief that shows what is critical, what needs action, who owns it, which customers and carriers are exposed, where financial risk exists, and what source data is missing.

TowerBrief creates:

- one unified action table;
- source-file coverage visibility;
- owner workload counts;
- daily KPI snapshot;
- markdown, HTML, and CSV exports.

## Inputs

All files are optional. Missing files are listed in source coverage and do not block brief generation.

- `trips.csv` maps to Trip Context
- `eta_risk_board.csv` maps to ETA Watch
- `detention_report.csv` maps to DetentionClock
- `gate_truth_report.csv` maps to GateTruth
- `fuel_exceptions.csv` maps to FuelGuard
- `update_discipline_report.csv` maps to UpdatePulse
- `delay_classification_report.csv` maps to DelayLens
- `pod_aging_report.csv` maps to PODPulse
- `ban_risk_board.csv` maps to BanWindow
- `carrier_scorecard.csv` maps to CarrierScore

TowerBrief normalizes common fields where present: `trip_id`, `vehicle_id`, `customer_name`, `carrier_name`, `exception_type`, `risk_bucket`, `severity`, `evidence`, and `suggested_action`.

## Logic

TowerBrief scans available files, validates minimal required columns for each uploaded file, and converts schema gaps into config warnings instead of raw tracebacks.

Each exception row becomes an action with:

- priority value: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `DATA GAP`;
- action owner;
- source product and source file;
- trip, vehicle, customer, and carrier context;
- exception type, risk bucket, and severity;
- evidence and suggested action;
- financial exposure where available.

Priority is deterministic. Critical severity, critical/high-risk buckets, detention exposure above the configured critical threshold, rejected POD with invoice blocking, POD missing for 7D+, ban conflict overlap above threshold, at-risk carrier score, and high-risk fuel evidence become `CRITICAL`. High severity, delayed/review buckets, POD overdue, invoice blockers, missing gate events, missing updates, and detention exposure above the high threshold become `HIGH`. Watchlist and unclear-impact rows become `MEDIUM`; clean informational rows become `LOW`; schema and context gaps become `DATA GAP`.

Owner buckets are deterministic:

- ETA Watch and DelayLens -> `control_tower`
- DetentionClock -> `billing_or_operations`
- GateTruth -> `control_tower`
- FuelGuard -> `fleet_audit`
- UpdatePulse -> `dispatcher_or_control_tower`
- PODPulse -> `documentation_or_billing`
- BanWindow -> `planning`
- CarrierScore -> `transport_manager`
- Data gaps -> `data_owner`

Trip context fills missing customer and carrier values when source rows include a matching `trip_id`.

## Outputs

- `daily_control_tower_brief.md`
- `daily_control_tower_brief.html`
- `daily_control_tower_brief.csv`

The CSV export includes exactly: `brief_date`, `section`, `priority`, `owner`, `source_file`, `source_product`, `trip_id`, `vehicle_id`, `customer_name`, `carrier_name`, `exception_type`, `risk_bucket`, `severity`, `financial_exposure`, `evidence`, and `suggested_action`.

The markdown and static HTML briefs include the same core management sections: executive summary, KPI snapshot, critical actions, high priority actions, financial exposure, customer risks, carrier watchlist, delay and ETA risks, POD and invoice blockers, detention exposure, fuel and update exceptions, ban-window risks, data gaps, files used, files missing, and limitations.

## Demo Data

The demo pack uses synthetic GCC-style rows covering:

- ETA critical delay;
- chargeable detention exposure;
- missing gate proof;
- high fuel liters;
- missing updates;
- critical late arrival;
- rejected POD and invoice blocker;
- ban-window conflict;
- carrier watch and at-risk rows;
- data gap from missing context fields;
- multiple exceptions on the same trip from different source products;
- duplicate issue rows deduplicated within the same source product.

## Run

Streamlit:

```bash
uv sync
uv run streamlit run tower_brief/app.py
```

CLI:

```bash
uv run tower-brief tower_brief/demo_data tower_brief/output
```

## Before And After

Before TowerBrief, a daily standup can start with multiple product exports and a manual conversation about which file matters most.

After TowerBrief, the control tower starts with one action-ranked brief, source coverage, and owner workload view.

## Limitations

- TowerBrief is deterministic and file-based.
- It uses synthetic demo data only.
- It does not use AI-generated narrative.
- It does not send emails, WhatsApp, Telegram, or automated escalations.
- It does not use paid APIs, live integrations, a BI server, login system, workflow engine, or database backend.
