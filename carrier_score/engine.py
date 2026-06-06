"""Deterministic carrier SLA scorecard engine for CarrierScore."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from carrier_score.models import CarrierScoreRule, CarrierScoreSettings, TripRecord


REQUIRED_TRIP_COLUMNS = {"trip_id", "carrier_name"}
RISK_BUCKETS = {"STRONG", "STABLE", "WATCHLIST", "NEEDS REVIEW", "DATA GAP"}
CONFIDENCE_BUCKETS = {"HIGH", "MEDIUM", "LOW", "DATA GAP"}
SCORECARD_COLUMNS = [
    "carrier_name",
    "total_trips",
    "late_trip_count",
    "late_trip_rate",
    "missing_pod_count",
    "missing_pod_rate",
    "detention_review_count",
    "detention_review_rate",
    "update_gap_count",
    "update_gap_rate",
    "fuel_exception_count",
    "fuel_exception_rate",
    "gate_gap_count",
    "gate_gap_rate",
    "ban_watch_count",
    "ban_watch_rate",
    "exception_count",
    "exception_rate",
    "sla_score",
    "risk_bucket",
    "confidence_bucket",
    "top_issue",
    "evidence",
    "suggested_action",
]
EXCEPTION_SUMMARY_COLUMNS = [
    "carrier_name",
    "exception_area",
    "source_file",
    "affected_trips",
    "exception_rate",
    "average_severity_score",
    "top_risk_bucket",
    "evidence",
    "suggested_action",
]
DEFAULT_RULE_WEIGHTS = {
    "late_trip_rate": 0.25,
    "missing_pod_rate": 0.20,
    "detention_review_rate": 0.15,
    "update_gap_rate": 0.15,
    "fuel_exception_rate": 0.10,
    "gate_gap_rate": 0.10,
    "ban_watch_rate": 0.05,
}
REPORT_SPECS = {
    "delay": {
        "source_file": "delay_classification_report.csv",
        "metric": "late_trip_rate",
        "count": "late_trip_count",
        "rate": "late_trip_rate",
        "area": "Delay performance",
        "required": {"trip_id", "primary_delay_reason", "risk_bucket"},
        "review_buckets": {"AT RISK", "LATE", "CRITICAL", "DELAYED", "NEEDS REVIEW"},
        "suggested_action": "Review delay patterns and recurring lane causes.",
    },
    "pod": {
        "source_file": "pod_aging_report.csv",
        "metric": "missing_pod_rate",
        "count": "missing_pod_count",
        "rate": "missing_pod_rate",
        "area": "POD discipline",
        "required": {"trip_id", "pod_gap_type", "risk_bucket"},
        "review_buckets": {"POD MISSING", "POD OVERDUE", "POD REJECTED", "INVOICE BLOCKED", "NEEDS REVIEW"},
        "suggested_action": "Review POD aging and document follow-up process.",
    },
    "detention": {
        "source_file": "detention_report.csv",
        "metric": "detention_review_rate",
        "count": "detention_review_count",
        "rate": "detention_review_rate",
        "area": "Detention exposure",
        "required": {"trip_id", "risk_bucket"},
        "review_buckets": {"CHARGEABLE", "APPROACHING FREE TIME", "MISSING EXIT", "NEEDS REVIEW"},
        "suggested_action": "Review detention exposure and site dwell evidence.",
    },
    "update": {
        "source_file": "update_discipline_report.csv",
        "metric": "update_gap_rate",
        "count": "update_gap_count",
        "rate": "update_gap_rate",
        "area": "Update discipline",
        "required": {"trip_id", "risk_bucket"},
        "review_buckets": {"MISSING UPDATE", "LATE UPDATE", "SEQUENCE ISSUE", "NO ACTUAL EVENT EVIDENCE", "NEEDS REVIEW"},
        "suggested_action": "Review status-update timeliness and milestone support.",
    },
    "fuel": {
        "source_file": "fuel_exceptions.csv",
        "metric": "fuel_exception_rate",
        "count": "fuel_exception_count",
        "rate": "fuel_exception_rate",
        "area": "Fuel exceptions",
        "required": {"trip_id", "risk_bucket"},
        "review_buckets": {"REVIEW", "NO GPS EVIDENCE", "NO STOP NEAR FUEL", "UNKNOWN STATION", "HIGH LITERS", "NEEDS REVIEW"},
        "suggested_action": "Review exception rate and supporting location evidence.",
    },
    "gate": {
        "source_file": "gate_truth_report.csv",
        "metric": "gate_gap_rate",
        "count": "gate_gap_count",
        "rate": "gate_gap_rate",
        "area": "Gate-truth gaps",
        "required": {"trip_id", "risk_bucket"},
        "review_buckets": {"MISSING ORIGIN EXIT", "MISSING DESTINATION ENTRY", "AMBIGUOUS MATCH", "NO VISIT EVIDENCE", "NEEDS REVIEW"},
        "suggested_action": "Review gate evidence gaps before service discussion.",
    },
    "ban": {
        "source_file": "ban_risk_board.csv",
        "metric": "ban_watch_rate",
        "count": "ban_watch_count",
        "rate": "ban_watch_rate",
        "area": "Restriction-window risk",
        "required": {"trip_id", "risk_bucket"},
        "review_buckets": {"WATCH", "BAN CONFLICT", "VEHICLE CLASS UNKNOWN", "DATA MISSING"},
        "suggested_action": "Review restriction-window planning cases with dispatch.",
    },
}
SEVERITY_SCORES = {
    "OK": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


@dataclass(frozen=True)
class CarrierScoreResult:
    """Structured outputs from a CarrierScore run."""

    carrier_scorecard: pd.DataFrame
    carrier_exception_summary: pd.DataFrame
    kpis: dict[str, float]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return normalized


def _normalize_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return " ".join(text.split())


def _normalize_key(value: Any) -> str | None:
    text = _normalize_text(value)
    return None if text is None else " ".join(text.upper().replace("_", " ").split())


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize required trip rows."""
    source = _normalize_columns(df).dropna(how="all").copy()
    for column in [
        "vehicle_id",
        "customer_name",
        "origin",
        "destination",
        "lane_id",
        "planned_departure",
        "promised_arrival",
        "delivered_time",
    ]:
        if column not in source.columns:
            source[column] = pd.NA
    _require_columns(source, REQUIRED_TRIP_COLUMNS, "trips")
    for column in ["trip_id", "carrier_name", "vehicle_id", "customer_name", "origin", "destination", "lane_id"]:
        source[column] = source[column].map(_normalize_text)
    for column in ["planned_departure", "promised_arrival", "delivered_time"]:
        source[column] = _to_utc(source[column])
    source = source.dropna(subset=["trip_id", "carrier_name"]).copy()

    errors: list[str] = []
    for row in source.itertuples(index=False):
        try:
            TripRecord(
                trip_id=str(row.trip_id),
                carrier_name=str(row.carrier_name),
                vehicle_id=None if pd.isna(row.vehicle_id) else row.vehicle_id,
                customer_name=None if pd.isna(row.customer_name) else row.customer_name,
                origin=None if pd.isna(row.origin) else row.origin,
                destination=None if pd.isna(row.destination) else row.destination,
                lane_id=None if pd.isna(row.lane_id) else row.lane_id,
                planned_departure=None
                if pd.isna(row.planned_departure)
                else row.planned_departure.to_pydatetime(),
                promised_arrival=None if pd.isna(row.promised_arrival) else row.promised_arrival.to_pydatetime(),
                delivered_time=None if pd.isna(row.delivered_time) else row.delivered_time.to_pydatetime(),
            )
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"trips contains invalid rows: {errors[0]}")

    return source[
        [
            "trip_id",
            "carrier_name",
            "vehicle_id",
            "customer_name",
            "origin",
            "destination",
            "lane_id",
            "planned_departure",
            "promised_arrival",
            "delivered_time",
        ]
    ].drop_duplicates("trip_id").reset_index(drop=True)


def prepare_rules(df: pd.DataFrame | None) -> dict[str, float]:
    """Normalize optional score rules and return metric weights."""
    if df is None or df.empty:
        return DEFAULT_RULE_WEIGHTS.copy()
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, {"metric", "weight"}, "carrier_score_rules")
    source["metric"] = source["metric"].map(_normalize_text)
    source["weight"] = pd.to_numeric(source["weight"], errors="coerce")
    weights: dict[str, float] = {}
    errors: list[str] = []
    for row in source.dropna(subset=["metric", "weight"]).itertuples(index=False):
        metric = str(row.metric)
        if metric not in DEFAULT_RULE_WEIGHTS:
            continue
        try:
            rule = CarrierScoreRule(metric=metric, weight=float(row.weight))
            weights[rule.metric] = rule.weight
        except ValidationError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError(f"carrier_score_rules contains invalid rows: {errors[0]}")
    return _normalize_weights(weights or DEFAULT_RULE_WEIGHTS)


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return DEFAULT_RULE_WEIGHTS.copy()
    return {metric: weight / total for metric, weight in weights.items()}


def prepare_report(df: pd.DataFrame | None, report_name: str) -> pd.DataFrame:
    """Normalize one optional report into trip-level review flags."""
    spec = REPORT_SPECS[report_name]
    columns = ["trip_id", "carrier_name", "risk_bucket", "severity", "evidence", "is_exception", "severity_score"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, spec["required"], spec["source_file"])
    for column in ["carrier_name", "severity", "evidence"]:
        if column not in source.columns:
            source[column] = pd.NA
    source["trip_id"] = source["trip_id"].map(_normalize_text)
    source["carrier_name"] = source["carrier_name"].map(_normalize_text)
    source["risk_bucket"] = source["risk_bucket"].map(_normalize_key)
    source["severity"] = source["severity"].map(_normalize_key)
    source["evidence"] = source["evidence"].map(_normalize_text)
    review_buckets = set(spec["review_buckets"])
    source["is_exception"] = source["risk_bucket"].isin(review_buckets)
    source["severity_score"] = source["severity"].map(SEVERITY_SCORES).fillna(0).astype(float)
    if report_name == "delay" and "arrival_delay_minutes" in source.columns:
        delay_minutes = pd.to_numeric(source["arrival_delay_minutes"], errors="coerce").fillna(0)
        source["is_exception"] = source["is_exception"] | (delay_minutes > 0)
        source["severity_score"] = source["severity_score"].where(
            source["severity_score"] > 0,
            delay_minutes.apply(lambda value: 3 if value >= 120 else 2 if value >= 60 else 1 if value > 0 else 0),
        )
    return (
        source[columns]
        .dropna(subset=["trip_id"])
        .sort_values(["trip_id", "is_exception", "severity_score"])
        .drop_duplicates("trip_id", keep="last")
        .reset_index(drop=True)
    )


def _risk_bucket(score: float, confidence: str, settings: CarrierScoreSettings) -> str:
    if confidence == "DATA GAP":
        return "DATA GAP"
    if score >= settings.strong_threshold:
        return "STRONG"
    if score >= settings.stable_threshold:
        return "STABLE"
    if score >= settings.watchlist_threshold:
        return "WATCHLIST"
    return "NEEDS REVIEW"


def _confidence_bucket(total_trips: int, populated_sources: int, settings: CarrierScoreSettings) -> str:
    if populated_sources == 0:
        return "DATA GAP"
    if total_trips >= settings.minimum_high_confidence_trips and populated_sources >= 4:
        return "HIGH"
    if total_trips >= settings.minimum_medium_confidence_trips and populated_sources >= 2:
        return "MEDIUM"
    return "LOW"


def _top_issue(issue_rates: dict[str, float]) -> str:
    labels = {
        "late_trip_rate": "Delay performance",
        "missing_pod_rate": "POD discipline",
        "detention_review_rate": "Detention exposure",
        "update_gap_rate": "Update discipline",
        "fuel_exception_rate": "Fuel exceptions",
        "gate_gap_rate": "Gate-truth gaps",
        "ban_watch_rate": "Restriction-window risk",
    }
    metric, rate = max(issue_rates.items(), key=lambda item: item[1])
    if rate <= 0:
        return "No dominant issue"
    return labels[metric]


def _score_for_rates(issue_rates: dict[str, float], weights: dict[str, float], settings: CarrierScoreSettings) -> float:
    penalty = sum(issue_rates[metric] * weights.get(metric, 0) * 100 for metric in DEFAULT_RULE_WEIGHTS)
    return round(max(settings.score_floor, 100 - penalty), 1)


def _carrier_reports(
    reports: dict[str, pd.DataFrame],
    carrier_trips: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    trip_carriers = carrier_trips[["trip_id", "carrier_name"]]
    prepared: dict[str, pd.DataFrame] = {}
    for report_name, report in reports.items():
        if report.empty:
            prepared[report_name] = report
            continue
        merged = report.merge(trip_carriers, on="trip_id", how="left", suffixes=("_report", ""))
        if "carrier_name_report" in merged.columns:
            merged["carrier_name"] = merged["carrier_name"].combine_first(merged["carrier_name_report"])
            merged = merged.drop(columns=["carrier_name_report"])
        prepared[report_name] = merged.dropna(subset=["carrier_name"]).copy()
    return prepared


def run_carrier_score(
    trips_df: pd.DataFrame,
    delay_df: pd.DataFrame | None = None,
    pod_df: pd.DataFrame | None = None,
    detention_df: pd.DataFrame | None = None,
    update_df: pd.DataFrame | None = None,
    fuel_df: pd.DataFrame | None = None,
    gate_df: pd.DataFrame | None = None,
    ban_df: pd.DataFrame | None = None,
    rules_df: pd.DataFrame | None = None,
    settings: CarrierScoreSettings | None = None,
) -> CarrierScoreResult:
    """Build a carrier-level SLA scorecard from trip and exception files."""
    settings = settings or CarrierScoreSettings()
    trips = prepare_trips(trips_df)
    weights = prepare_rules(rules_df)
    reports = _carrier_reports(
        {
            "delay": prepare_report(delay_df, "delay"),
            "pod": prepare_report(pod_df, "pod"),
            "detention": prepare_report(detention_df, "detention"),
            "update": prepare_report(update_df, "update"),
            "fuel": prepare_report(fuel_df, "fuel"),
            "gate": prepare_report(gate_df, "gate"),
            "ban": prepare_report(ban_df, "ban"),
        },
        trips,
    )

    score_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for carrier_name, carrier_trips in trips.groupby("carrier_name", sort=True):
        total_trips = len(carrier_trips)
        issue_rates: dict[str, float] = {}
        count_values: dict[str, int] = {}
        populated_sources = 0
        exception_trip_ids: set[str] = set()
        for report_name, report in reports.items():
            spec = REPORT_SPECS[report_name]
            carrier_report = report[report["carrier_name"] == carrier_name]
            if not carrier_report.empty:
                populated_sources += 1
            affected = carrier_report[carrier_report["is_exception"].fillna(False).astype(bool)]
            affected_count = int(affected["trip_id"].nunique())
            count_values[spec["count"]] = affected_count
            issue_rates[spec["rate"]] = round(affected_count / total_trips, 4) if total_trips else 0.0
            exception_trip_ids.update(affected["trip_id"].dropna().astype(str).tolist())
            if affected_count:
                top_bucket = (
                    affected["risk_bucket"].dropna().mode().iloc[0]
                    if not affected["risk_bucket"].dropna().empty
                    else "NEEDS REVIEW"
                )
                evidence = f"{affected_count} of {total_trips} trips need review in {spec['area'].lower()}."
                summary_rows.append(
                    {
                        "carrier_name": carrier_name,
                        "exception_area": spec["area"],
                        "source_file": spec["source_file"],
                        "affected_trips": affected_count,
                        "exception_rate": round(affected_count / total_trips, 4),
                        "average_severity_score": round(float(affected["severity_score"].mean()), 2),
                        "top_risk_bucket": top_bucket,
                        "evidence": evidence,
                        "suggested_action": spec["suggested_action"],
                    }
                )

        for metric in DEFAULT_RULE_WEIGHTS:
            issue_rates.setdefault(metric, 0.0)
        for spec in REPORT_SPECS.values():
            count_values.setdefault(spec["count"], 0)

        exception_count = len(exception_trip_ids)
        exception_rate = round(exception_count / total_trips, 4) if total_trips else 0.0
        score = _score_for_rates(issue_rates, weights, settings)
        confidence = _confidence_bucket(total_trips, populated_sources, settings)
        risk = _risk_bucket(score, confidence, settings)
        top_issue = _top_issue(issue_rates)
        evidence = (
            f"{exception_count} of {total_trips} trips have at least one review flag across "
            f"{populated_sources} populated optional sources."
        )
        action = (
            "Keep current carrier performance review cadence."
            if risk in {"STRONG", "STABLE"}
            else "Review top issue and data gaps before the next carrier performance meeting."
        )
        score_rows.append(
            {
                "carrier_name": carrier_name,
                "total_trips": total_trips,
                **count_values,
                **issue_rates,
                "exception_count": exception_count,
                "exception_rate": exception_rate,
                "sla_score": score,
                "risk_bucket": risk,
                "confidence_bucket": confidence,
                "top_issue": top_issue,
                "evidence": evidence,
                "suggested_action": action,
            }
        )

    scorecard = pd.DataFrame(score_rows, columns=SCORECARD_COLUMNS)
    if not scorecard.empty:
        scorecard = scorecard.sort_values(["sla_score", "exception_rate", "carrier_name"], ascending=[True, False, True]).reset_index(drop=True)
    summary = pd.DataFrame(summary_rows, columns=EXCEPTION_SUMMARY_COLUMNS)
    if not summary.empty:
        summary = summary.sort_values(["carrier_name", "exception_rate"], ascending=[True, False]).reset_index(drop=True)

    kpis = {
        "total_carriers": float(len(scorecard)),
        "total_trips": float(len(trips)),
        "average_score": round(float(scorecard["sla_score"].mean()), 1) if not scorecard.empty else 0.0,
        "needs_review_carriers": float(scorecard["risk_bucket"].isin({"WATCHLIST", "NEEDS REVIEW", "DATA GAP"}).sum())
        if not scorecard.empty
        else 0.0,
        "summary_rows": float(len(summary)),
    }
    return CarrierScoreResult(scorecard, summary, kpis)


def write_outputs(result: CarrierScoreResult, output_dir: Path) -> tuple[Path, Path]:
    """Write CarrierScore CSV outputs and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scorecard_path = output_dir / "carrier_scorecard.csv"
    summary_path = output_dir / "carrier_exception_summary.csv"
    result.carrier_scorecard.to_csv(scorecard_path, index=False)
    result.carrier_exception_summary.to_csv(summary_path, index=False)
    return scorecard_path, summary_path
