# Day 12: CarrierScore

CarrierScore is a local-first Streamlit app for creating a neutral carrier performance view from simple trip files and optional product outputs.

## Business Problem

Carrier reviews often become emotional when performance evidence is scattered across late trips, missing PODs, detention exposure, fuel exceptions, update discipline, ban-window risks, and gate-truth gaps.

CarrierScore creates a deterministic SLA scorecard for:

- carrier-level KPI review;
- configurable weighted scoring;
- watch and at-risk buckets;
- insufficient-data visibility;
- top-issue explanation per carrier;
- exception summary rows for review meetings.

## Inputs

`trips.csv` requires `trip_id` and `carrier_name`. Optional trip fields are `vehicle_id`, `customer_name`, `origin`, `destination`, `lane_id`, `planned_departure`, `promised_arrival`, and `delivered_time`.

Optional supporting files:

- `delay_classification_report.csv`: `trip_id`, `primary_delay_reason`, `risk_bucket`, optional `carrier_name`, `arrival_delay_minutes`, `severity`, `evidence`
- `pod_aging_report.csv`: `trip_id`, `pod_gap_type`, `risk_bucket`, optional `carrier_name`, `pod_age_hours`, `aging_bucket`, `invoice_blocked`, `invoice_status`, `severity`, `evidence`
- `detention_report.csv`: `trip_id`, `risk_bucket`, optional `carrier_name`, `chargeable_minutes`, `estimated_charge`, `currency`, `severity`, `evidence`
- `update_discipline_report.csv`: `trip_id`, `update_gap_type`, `risk_bucket`, optional `carrier_name`, `update_delay_minutes`, `severity`, `evidence`
- `fuel_exceptions.csv`: `fuel_event_id`, `vehicle_id`, `exception_type`, `severity`, optional `trip_id`, `carrier_name`, `liters`, `evidence`
- `gate_truth_report.csv`: `trip_id`, `gate_truth_status`, `exception_type`, optional `carrier_name`, `severity`, `evidence`
- `ban_risk_board.csv`: `trip_id`, `risk_bucket`, optional `carrier_name`, `city`, `overlap_minutes`, `severity`, `evidence`
- `carrier_score_rules.csv`: `metric_name`, `weight`, `direction`, `enabled`, `good_threshold`, `bad_threshold`

## Logic

CarrierScore joins optional report rows back to trip ownership by `trip_id`. Report-level `carrier_name` is used as fallback context when a row cannot be matched to the trip file.

The score starts at 100 and subtracts weighted penalties. Lower-is-better metrics penalize by `weight * metric_rate`. Higher-is-better metrics, such as data completeness, penalize by `weight * (1 - metric_rate)`. Uploaded scoring rules can override default weights and directions; disabled rows are ignored, and invalid rows become config warnings rather than crashes.

Risk buckets:

- `EXCELLENT`
- `GOOD`
- `WATCH`
- `AT RISK`
- `INSUFFICIENT DATA`

Confidence buckets:

- `HIGH`
- `MEDIUM`
- `LOW SAMPLE`
- `DATA LIMITED`
- `DATA MISSING`

## Outputs

`carrier_scorecard.csv` includes exactly the contract fields for carrier name, trip/customer/lane counts, source completeness, all exception rates, detention exposure, fuel liters, score, penalty, risk bucket, confidence bucket, top issue, evidence, and suggested action.

`carrier_exception_summary.csv` includes exactly carrier name, exception source, exception type, affected trips, affected rate, severity, evidence, and suggested action.

## Demo Data

The demo pack uses GCC-style synthetic operational rows covering:

- excellent carrier with clean performance;
- good carrier with minor delay rate;
- watch carrier with repeated late trips;
- at-risk carrier with overdue PODs;
- rejected POD and invoice blocker;
- detention exposure;
- update discipline exceptions;
- fuel exceptions;
- ban-window conflicts;
- low-sample insufficient-data carrier.

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
