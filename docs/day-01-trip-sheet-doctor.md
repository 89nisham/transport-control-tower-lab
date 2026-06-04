# Day 1: Trip Sheet Doctor

## Problem Card

Transport teams often receive trip sheets from branches, planners, dispatchers, and subcontractors in messy Excel or CSV formats.

The operational pain is simple: before a control tower can track ETA, reconcile GPS, audit fuel, or report SLA performance, the trip sheet itself needs to be usable.

## Stakeholder

- Dispatch manager
- Control tower analyst
- Fleet operations manager
- Transport manager

## Input Contract

Trip Sheet Doctor accepts Excel or CSV files with common trip fields:

- Trip, shipment, order, or waybill reference
- Vehicle, truck, door number, asset ID, or plate
- Driver or captain
- Origin or pickup location
- Destination or delivery location
- Planned pickup, dispatch, ETA, or delivery timestamp
- Trip status

## Core Logic

The tool applies deterministic checks first:

- Map messy column names into canonical fields
- Normalize vehicle and text values
- Convert date fields safely
- Preserve source row numbers
- Detect missing required fields
- Detect duplicate trip IDs
- Detect invalid pickup/delivery sequence
- Detect same-origin/same-destination rows
- Detect very long planned trip durations

No data is silently fixed. Corrections are suggested for review.

## Output

The generated workbook contains:

- `summary`
- `exceptions`
- `correction_suggestions`
- `cleaned_trips`
- `column_map`

Each exception includes severity, confidence, evidence, suggested action, owner, and review status.

## Public Learning

Clean operational events are more valuable than a decorative dashboard. If the trip sheet is weak, every downstream ETA, GPS, fuel, and SLA workflow becomes weak too.
