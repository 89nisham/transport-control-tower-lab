# Day 9: PODPulse

PODPulse is a local-first Streamlit app for tracking proof-of-delivery aging, POD gaps, rejected PODs, approval pending cases, and invoice blockers.

## Business Problem

Delivery is not financially complete until the POD is received, usable, and approved. Billing and operations teams often review delivery files, POD portals, and invoice status separately.

PODPulse creates a neutral POD aging board for:

- POD gaps;
- missing documents;
- rejected PODs;
- approval pending cases;
- late POD receipt;
- invoice blockers.
- data-missing delivery records.

## Inputs

`deliveries.csv` requires:

- `trip_id`
- `customer_name`
- `delivered_time`
- `vehicle_id` optional
- `carrier_name` optional
- `origin` optional
- `destination` optional
- `promised_arrival` optional

`pod_status.csv` requires:

- `trip_id`
- `pod_status`
- `pod_received_time` optional
- `pod_rejected_time` optional
- `rejection_reason` optional
- `uploaded_by` optional
- `approved_time` optional
- `resubmitted_time` optional

`invoice_status.csv` is optional:

- `trip_id`
- `invoice_status`
- `invoice_no` optional
- `invoice_date` optional
- `blocked_reason` optional

## Logic

Default thresholds:

- POD SLA: 48 hours
- warning threshold: 24 hours
- critical threshold: 168 hours / 7 days

Aging buckets:

- `0-24H`
- `24-48H`
- `48-72H`
- `72H+`
- `7D+`

Accepted POD statuses are `NOT_REQUIRED`, `MISSING`, `RECEIVED`, `REJECTED`, `RESUBMITTED`, and `APPROVED`.

Accepted invoice statuses are `NOT READY`, `READY`, `BLOCKED`, `INVOICED`, `PAID`, and `ON HOLD`.

## Outputs

`pod_aging_report.csv` includes:

- trip, vehicle, customer, carrier, origin, and destination context
- delivered time and promised arrival
- POD status, received time, rejected time, rejection reason, and uploader
- invoice status, invoice number, and blocked reason
- POD age hours and days
- aging bucket and POD gap type
- invoice blocker flag
- risk bucket, severity, evidence, and suggested action

`overdue_pods.csv` includes focused POD gaps and invoice blockers for review.

## Demo Data

The demo pack uses GCC-style logistics scenarios:

- approved POD received inside SLA;
- missing POD inside the warning threshold;
- overdue POD beyond SLA;
- 7D+ critical missing POD;
- rejected POD with rejection reason;
- resubmitted POD awaiting approval;
- late POD receipt;
- invoice blocker because POD is not approved;
- not-delivered / missing delivery timestamp case;
- data-missing required field case.

## Run

```bash
uv sync
uv run streamlit run pod_pulse/app.py
```

## Before And After

Before PODPulse, POD follow-up depends on manual checks across delivery files, document status, and invoice status.

After PODPulse, the same files produce a neutral aging report with POD gap type, aging bucket, evidence, invoice blocker status, and suggested next action.

## Limitations

- PODPulse is deterministic and file-based.
- It uses synthetic demo data only.
- It does not perform OCR, ERP posting, automated emails, or live integrations.
- It does not decide commercial liability.
- Results depend on delivered time, POD status, and invoice status data quality.
