"""Deterministic detention calculation engine for DetentionClock."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from detention_clock.models import DetentionRuleRecord, TripRecord, VisitEventRecord


REQUIRED_VISIT_COLUMNS = {
    "trip_id",
    "vehicle_id",
    "geofence_id",
    "geofence_name",
    "geofence_type",
    "enter_time",
    "exit_time",
    "dwell_minutes",
}
REQUIRED_RULE_COLUMNS = {
    "rule_id",
    "customer_name",
    "geofence_type",
    "free_minutes",
    "rate_type",
    "rate_per_hour",
    "currency",
}
DETENTION_ORDER = [
    "MISSING EXIT",
    "DETENTION",
    "APPROACHING FREE TIME",
    "WITHIN FREE TIME",
    "NO DETENTION",
]


@dataclass(frozen=True)
class DetentionClockResult:
    """Structured outputs from a DetentionClock run."""

    detention_report: pd.DataFrame
    chargeable_detention: pd.DataFrame
    kpis: dict[str, float]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize uploaded CSV column names to matching-friendly snake_case."""
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return normalized


def _normalize_text(value: Any) -> str | None:
    """Normalize text values while preserving operational missing values."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return " ".join(text.split())


def _normalize_key(value: Any) -> str | None:
    """Normalize identifiers used for joins and rule lookup."""
    text = _normalize_text(value)
    return None if text is None else text.upper().replace(" ", "")


def _normalize_customer(value: Any) -> str | None:
    """Normalize customer names for deterministic rule matching."""
    text = _normalize_text(value)
    return None if text is None else text.upper()


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Raise a readable error when an input dataframe is missing required columns."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    """Parse a timestamp series and standardize it to timezone-aware UTC."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def prepare_visit_events(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize, timezone-standardize, and validate GeoReplay visit events."""
    source = _normalize_columns(df).dropna(how="all").copy()
    if "entry_time" in source.columns and "enter_time" not in source.columns:
        source["enter_time"] = source["entry_time"]
    _require_columns(source, REQUIRED_VISIT_COLUMNS, "visit_events")

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["vehicle_id"] = source["vehicle_id"].map(_normalize_key)
    source["geofence_id"] = source["geofence_id"].map(_normalize_key)
    source["geofence_name"] = source["geofence_name"].map(_normalize_text)
    source["geofence_type"] = source["geofence_type"].map(_normalize_key)
    source["enter_time"] = _to_utc(source["enter_time"])
    source["exit_time"] = _to_utc(source["exit_time"])
    source["dwell_minutes"] = pd.to_numeric(source["dwell_minutes"], errors="coerce")

    has_times = source["enter_time"].notna() & source["exit_time"].notna()
    missing_dwell = source["dwell_minutes"].isna() & has_times
    source.loc[missing_dwell, "dwell_minutes"] = (
        (source.loc[missing_dwell, "exit_time"] - source.loc[missing_dwell, "enter_time"])
        .dt.total_seconds()
        .div(60)
        .round(2)
    )
    source = source.dropna(subset=["vehicle_id", "geofence_type"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            VisitEventRecord(
                trip_id=row.trip_id,
                vehicle_id=str(row.vehicle_id),
                geofence_id=row.geofence_id,
                geofence_name=row.geofence_name,
                geofence_type=str(row.geofence_type),
                enter_time=None if pd.isna(row.enter_time) else row.enter_time.to_pydatetime(),
                exit_time=None if pd.isna(row.exit_time) else row.exit_time.to_pydatetime(),
                dwell_minutes=None if pd.isna(row.dwell_minutes) else float(row.dwell_minutes),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"visit_events contains invalid rows: {errors[0]}")

    columns = [
        "trip_id",
        "vehicle_id",
        "geofence_id",
        "geofence_name",
        "geofence_type",
        "enter_time",
        "exit_time",
        "dwell_minutes",
    ]
    return source[columns].reset_index(drop=True)


def prepare_detention_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate user-supplied detention rules."""
    source = _normalize_columns(df).dropna(how="all").copy()
    if "geofence_id" not in source.columns:
        source["geofence_id"] = pd.NA
    if "minimum_charge" not in source.columns:
        source["minimum_charge"] = pd.NA
    _require_columns(source, REQUIRED_RULE_COLUMNS, "detention_rules")

    source["rule_id"] = source["rule_id"].map(_normalize_text)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["customer_key"] = source["customer_name"].map(_normalize_customer)
    source["geofence_type"] = source["geofence_type"].map(_normalize_key)
    source["geofence_id"] = source["geofence_id"].map(_normalize_key)
    source["free_minutes"] = pd.to_numeric(source["free_minutes"], errors="coerce")
    source["rate_type"] = source["rate_type"].map(_normalize_text).fillna("hourly")
    source["rate_per_hour"] = pd.to_numeric(source["rate_per_hour"], errors="coerce")
    source["minimum_charge"] = pd.to_numeric(source["minimum_charge"], errors="coerce")
    source["currency"] = source["currency"].map(_normalize_text)
    source = source.dropna(subset=["rule_id", "free_minutes", "rate_per_hour", "currency"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            DetentionRuleRecord(
                rule_id=str(row.rule_id),
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                geofence_type=row.geofence_type,
                geofence_id=None if pd.isna(row.geofence_id) else row.geofence_id,
                free_minutes=float(row.free_minutes),
                rate_type=str(row.rate_type),
                rate_per_hour=float(row.rate_per_hour),
                minimum_charge=None if pd.isna(row.minimum_charge) else float(row.minimum_charge),
                currency=str(row.currency),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"detention_rules contains invalid rows: {errors[0]}")

    columns = [
        "rule_id",
        "customer_name",
        "customer_key",
        "geofence_type",
        "geofence_id",
        "free_minutes",
        "rate_type",
        "rate_per_hour",
        "minimum_charge",
        "currency",
    ]
    return source[columns].reset_index(drop=True)


def prepare_trips(df: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize optional trip context rows."""
    columns = [
        "trip_id",
        "customer_name",
        "customer_key",
        "carrier_name",
        "origin",
        "destination",
        "planned_arrival",
        "planned_departure",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    source = _normalize_columns(df).dropna(how="all").copy()
    if "trip_id" not in source.columns:
        raise ValueError("trips is missing required columns: trip_id")
    for column in columns:
        if column not in source.columns and column != "customer_key":
            source[column] = pd.NA

    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["customer_name"] = source["customer_name"].map(_normalize_text)
    source["customer_key"] = source["customer_name"].map(_normalize_customer)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["origin"] = source["origin"].map(_normalize_text)
    source["destination"] = source["destination"].map(_normalize_text)
    source["planned_arrival"] = _to_utc(source["planned_arrival"])
    source["planned_departure"] = _to_utc(source["planned_departure"])
    source = source.dropna(subset=["trip_id"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                customer_name=row.customer_name,
                carrier_name=row.carrier_name,
                origin=row.origin,
                destination=row.destination,
                planned_arrival=None
                if pd.isna(row.planned_arrival)
                else row.planned_arrival.to_pydatetime(),
                planned_departure=None
                if pd.isna(row.planned_departure)
                else row.planned_departure.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"trips contains invalid rows: {errors[0]}")

    return source[columns].drop_duplicates("trip_id").reset_index(drop=True)


def _rule_specificity(rule: pd.Series, customer_key: str | None) -> tuple[int, int, int]:
    """Rank rule matches by customer, geofence ID, then geofence type specificity."""
    customer_score = 1 if customer_key and rule.get("customer_key") == customer_key else 0
    geofence_score = 1 if pd.notna(rule.get("geofence_id")) else 0
    type_score = 1 if pd.notna(rule.get("geofence_type")) else 0
    return customer_score, geofence_score, type_score


def find_matching_rule(visit: pd.Series, rules: pd.DataFrame) -> pd.Series | None:
    """Find the best detention rule for one visit."""
    if rules.empty:
        return None

    customer_key = visit.get("customer_key")
    geofence_id = visit.get("geofence_id")
    geofence_type = visit.get("geofence_type")
    candidates = rules.copy()

    if customer_key:
        customer_or_default = candidates["customer_key"].isna() | (
            candidates["customer_key"] == customer_key
        )
        candidates = candidates[customer_or_default].copy()
    else:
        candidates = candidates[candidates["customer_key"].isna()].copy()

    id_or_default = candidates["geofence_id"].isna() | (candidates["geofence_id"] == geofence_id)
    type_or_default = candidates["geofence_type"].isna() | (
        candidates["geofence_type"] == geofence_type
    )
    candidates = candidates[id_or_default & type_or_default].copy()
    if candidates.empty:
        return None

    candidates["_specificity"] = candidates.apply(
        lambda row: _rule_specificity(row, customer_key),
        axis=1,
    )
    return candidates.sort_values("_specificity", ascending=False).iloc[0]


def classify_detention(
    enter_time: pd.Timestamp | pd.NaT,
    exit_time: pd.Timestamp | pd.NaT,
    dwell_minutes: float | None,
    free_minutes: float,
) -> str:
    """Classify one visit into DetentionClock risk buckets."""
    if pd.notna(enter_time) and pd.isna(exit_time):
        return "MISSING EXIT"
    if dwell_minutes is None or pd.isna(dwell_minutes) or dwell_minutes <= 0:
        return "NO DETENTION"
    if dwell_minutes > free_minutes:
        return "DETENTION"
    if free_minutes - dwell_minutes <= 15:
        return "APPROACHING FREE TIME"
    return "WITHIN FREE TIME"


def build_detention_report(
    visit_events: pd.DataFrame,
    detention_rules: pd.DataFrame,
    trips: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build the manager-ready detention report from visits, rules, and trips."""
    visits = prepare_visit_events(visit_events)
    rules = prepare_detention_rules(detention_rules)
    trip_context = prepare_trips(trips)

    report = visits.merge(trip_context, on="trip_id", how="left")
    rows: list[dict[str, Any]] = []
    for row in report.itertuples(index=False):
        visit = pd.Series(row._asdict())
        rule = find_matching_rule(visit, rules)
        if rule is None:
            rule_id = "NO_RULE"
            free_minutes = 0.0
            rate_type = "hourly"
            rate_per_hour = 0.0
            minimum_charge = pd.NA
            currency = "N/A"
        else:
            rule_id = rule["rule_id"]
            free_minutes = float(rule["free_minutes"])
            rate_type = rule["rate_type"]
            rate_per_hour = float(rule["rate_per_hour"])
            minimum_charge = rule["minimum_charge"]
            currency = rule["currency"]

        dwell = None if pd.isna(row.dwell_minutes) else float(row.dwell_minutes)
        risk_bucket = classify_detention(row.enter_time, row.exit_time, dwell, free_minutes)
        chargeable_minutes = max(0.0, (dwell or 0.0) - free_minutes)
        if risk_bucket in {"MISSING EXIT", "NO DETENTION"}:
            chargeable_minutes = 0.0
        chargeable_hours = round(chargeable_minutes / 60, 2)
        estimated_charge = chargeable_hours * rate_per_hour
        if chargeable_minutes > 0 and pd.notna(minimum_charge):
            estimated_charge = max(estimated_charge, float(minimum_charge))

        rows.append(
            {
                "trip_id": row.trip_id,
                "vehicle_id": row.vehicle_id,
                "customer_name": row.customer_name,
                "carrier_name": row.carrier_name,
                "origin": row.origin,
                "destination": row.destination,
                "geofence_id": row.geofence_id,
                "geofence_name": row.geofence_name,
                "geofence_type": row.geofence_type,
                "enter_time": row.enter_time,
                "exit_time": row.exit_time,
                "dwell_minutes": None if dwell is None else round(dwell, 2),
                "rule_id": rule_id,
                "free_minutes": free_minutes,
                "rate_type": rate_type,
                "rate_per_hour": rate_per_hour,
                "minimum_charge": minimum_charge,
                "currency": currency,
                "chargeable_minutes": round(chargeable_minutes, 2),
                "chargeable_hours": chargeable_hours,
                "estimated_charge": round(estimated_charge, 2),
                "risk_bucket": risk_bucket,
                "suggested_action": _suggested_action(risk_bucket, rule_id),
                "review_status": "open",
            }
        )

    output = pd.DataFrame(rows)
    order_map = {bucket: index for index, bucket in enumerate(DETENTION_ORDER)}
    return output.sort_values(
        by=["risk_bucket", "estimated_charge", "dwell_minutes"],
        key=lambda series: series.map(order_map) if series.name == "risk_bucket" else series,
        ascending=[True, False, False],
    ).reset_index(drop=True)


def _suggested_action(risk_bucket: str, rule_id: str) -> str:
    """Return an operator-friendly next action."""
    if rule_id == "NO_RULE":
        return "Review missing detention rule before billing."
    return {
        "MISSING EXIT": "Confirm exit time before calculating detention.",
        "NO DETENTION": "No dwell evidence to review.",
        "WITHIN FREE TIME": "Monitor only; no chargeable detention.",
        "APPROACHING FREE TIME": "Warn dispatcher before free time expires.",
        "DETENTION": "Review chargeable detention with trip evidence.",
    }[risk_bucket]


def run_detention_clock(
    visit_events: pd.DataFrame,
    detention_rules: pd.DataFrame,
    trips: pd.DataFrame | None = None,
) -> DetentionClockResult:
    """Run DetentionClock and return report, chargeable rows, and KPIs."""
    detention_report = build_detention_report(visit_events, detention_rules, trips)
    chargeable = detention_report[detention_report["chargeable_minutes"] > 0].copy()
    kpis = {
        "total_visits": int(len(detention_report)),
        "detention_cases": int((detention_report["risk_bucket"] == "DETENTION").sum()),
        "missing_exits": int((detention_report["risk_bucket"] == "MISSING EXIT").sum()),
        "total_chargeable_minutes": float(detention_report["chargeable_minutes"].sum()),
        "estimated_detention_amount": float(detention_report["estimated_charge"].sum()),
    }
    return DetentionClockResult(
        detention_report=detention_report,
        chargeable_detention=chargeable,
        kpis=kpis,
    )


def write_outputs(result: DetentionClockResult, output_dir: Path) -> tuple[Path, Path]:
    """Write DetentionClock CSV exports and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "detention_report.csv"
    chargeable_path = output_dir / "chargeable_detention.csv"
    result.detention_report.to_csv(report_path, index=False)
    result.chargeable_detention.to_csv(chargeable_path, index=False)
    return report_path, chargeable_path
