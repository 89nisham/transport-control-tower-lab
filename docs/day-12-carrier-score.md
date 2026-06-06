# Day 12: CarrierScore

CarrierScore is a local-first Streamlit app for creating a neutral carrier performance view from simple trip files and optional product outputs.

## Business Problem

Carrier reviews often become emotional when performance evidence is scattered across late trips, POD gaps, detention exposure, update discipline, fuel exceptions, gate-truth gaps, and restriction-window risks.

CarrierScore creates a deterministic SLA scorecard for:

- carrier-level KPI review;
- configurable weighted scoring;
- watchlist and needs-review buckets;
- data-gap visibility;
- top-issue explanation per carrier;
- exception summary rows for review meetings.

## Inputs

`trips.csv` requires:

- `trip_id`
- `carrier_name`
- `vehicle_id` optional
- `customer_name` optional
- `origin` optional
- `destination` optional
- `lane_id` optional
- `planned_departure` optional
- `promised_arrival` optional
- `delivered_time` optional

Optional supporting files:

- `delay_classification_report.csv` with `trip_id`, `primary_delay_reason`, `risk_bucket`, optional `carrier_name`, `arrival_delay_minutes`, `severity`, and `evidence`
- `pod_aging_report.csv` with `trip_id`, `pod_gap_type`, `risk_bucket`, optional `carrier_name`, `pod_age_hours`, `aging_bucket`, `invoice_blocked`, `severity`, and `evidence`
- `detention_report.csv` with `trip_id`, `risk_bucket`, optional detention context, `severity`, and `evidence`
- `update_discipline_report.csv` with `trip_id`, `risk_bucket`, optional update counts, `severity`, and `evidence`
- `fuel_exceptions.csv` with `trip_id`, `risk_bucket`, optional exception type, `severity`, and `evidence`
- `gate_truth_report.csv` with `trip_id`, `risk_bucket`, optional gate status, confidence, and evidence
- `ban_risk_board.csv` with `trip_id`, `risk_bucket`, optional city, overlap, severity, and evidence
- `carrier_score_rules.csv` with `metric` and `weight`

## Logic

CarrierScore joins every optional report back to the required trip file by `trip_id`. The trip file is the source of carrier ownership, while report-level `carrier_name` is used only as a fallback.

Each source contributes a carrier-level exception rate:

- late trips;
- missing or blocked POD cases;
- detention rows needing review;
- update discipline gaps;
- fuel exceptions;
- gate-truth gaps;
- restriction-window watch or conflict cases.

The score starts at 100 and subtracts weighted exception-rate penalties. Weights can be changed with `carrier_score_rules.csv`; when no rules are uploaded, the demo defaults are used.

Risk buckets:

- `STRONG`
- `STABLE`
- `WATCHLIST`
- `NEEDS REVIEW`
- `DATA GAP`

Confidence buckets:

- `HIGH`
- `MEDIUM`
- `LOW`
- `DATA GAP`

## Outputs

`carrier_scorecard.csv` includes carrier KPIs, exception rates, weighted score, risk bucket, confidence bucket, top issue, evidence, and suggested action.

`carrier_exception_summary.csv` includes one row per carrier and exception area that has review flags.

## Demo Data

The demo pack uses GCC-style synthetic operational rows:

- Gulf Bridge with delay, POD, detention, update, fuel, gate, and ban-window review flags;
- Desert Line with smaller update, gate, fuel, and restriction-window watch cases;
- North Star Logistics with clean high-confidence source rows;
- One Trip Express with one trip and low-confidence review flags.

## Run

```bash
uv sync
uv run streamlit run carrier_score/app.py
```

## Before And After

Before CarrierScore, carrier review prep often means manually stitching together several operational files and debating scattered examples.

After CarrierScore, those files produce one transparent SLA scorecard and exception summary for a calmer review.

## Limitations

- CarrierScore is deterministic and file-based.
- It uses synthetic demo data only.
- It does not create penalty invoices, legal claims, procurement records, or vendor messages.
- It does not call live systems or paid APIs.
- Scores depend on uploaded report quality and the scoring weights supplied by the user.
