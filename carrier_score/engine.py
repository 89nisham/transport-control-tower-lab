"""Deterministic carrier SLA scorecard engine for CarrierScore."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import ValidationError

from carrier_score.models import CarrierScoreRule, CarrierScoreSettings


REQUIRED_TRIP_COLUMNS = {"trip_id", "carrier_name"}
RISK_BUCKETS = {"EXCELLENT", "GOOD", "WATCH", "AT RISK", "INSUFFICIENT DATA"}
CONFIDENCE_BUCKETS = {"HIGH", "MEDIUM", "LOW SAMPLE", "DATA LIMITED", "DATA MISSING"}
SCORECARD_COLUMNS = [
    "carrier_name",
    "total_trips",
    "customer_count",
    "lane_count",
    "source_files_used",
    "data_completeness_rate",
    "on_time_rate",
    "late_trip_rate",
    "missing_pod_rate",
    "overdue_pod_rate",
    "rejected_pod_rate",
    "detention_case_rate",
    "update_exception_rate",
    "fuel_exception_rate",
    "gate_exception_rate",
    "ban_conflict_rate",
    "invoice_blocker_rate",
    "estimated_detention_exposure",
    "total_fuel_exception_liters",
    "score",
    "score_penalty",
    "risk_bucket",
    "confidence_bucket",
    "top_issue",
    "evidence",
    "suggested_action",
]
EXCEPTION_SUMMARY_COLUMNS = [
    "carrier_name",
    "exception_source",
    "exception_type",
    "affected_trips",
    "affected_rate",
    "severity",
    "evidence",
    "suggested_action",
]
DEFAULT_RULES = {
    "late_trip_rate": {"weight": 20.0, "direction": "lower_is_better"},
    "missing_pod_rate": {"weight": 15.0, "direction": "lower_is_better"},
    "overdue_pod_rate": {"weight": 15.0, "direction": "lower_is_better"},
    "rejected_pod_rate": {"weight": 10.0, "direction": "lower_is_better"},
    "detention_case_rate": {"weight": 10.0, "direction": "lower_is_better"},
    "update_exception_rate": {"weight": 10.0, "direction": "lower_is_better"},
    "fuel_exception_rate": {"weight": 8.0, "direction": "lower_is_better"},
    "gate_exception_rate": {"weight": 7.0, "direction": "lower_is_better"},
    "ban_conflict_rate": {"weight": 5.0, "direction": "lower_is_better"},
    "invoice_blocker_rate": {"weight": 10.0, "direction": "lower_is_better"},
    "data_completeness_rate": {"weight": 5.0, "direction": "higher_is_better"},
}
DEFAULT_WEIGHT_TOTAL = sum(rule["weight"] for rule in DEFAULT_RULES.values())
OPTIONAL_SOURCES = {
    "delay": "delay_classification_report.csv",
    "pod": "pod_aging_report.csv",
    "detention": "detention_report.csv",
    "update": "update_discipline_report.csv",
    "fuel": "fuel_exceptions.csv",
    "gate": "gate_truth_report.csv",
    "ban": "ban_risk_board.csv",
}
SOURCE_REQUIRED_COLUMNS = {
    "delay": {"trip_id", "primary_delay_reason", "risk_bucket"},
    "pod": {"trip_id", "pod_gap_type", "risk_bucket"},
    "detention": {"trip_id", "risk_bucket"},
    "update": {"trip_id", "update_gap_type", "risk_bucket"},
    "fuel": {"fuel_event_id", "vehicle_id", "exception_type", "severity"},
    "gate": {"trip_id", "gate_truth_status", "exception_type"},
    "ban": {"trip_id", "risk_bucket"},
}
SOURCE_OPTIONAL_COLUMNS = {
    "delay": ["carrier_name", "arrival_delay_minutes", "severity", "evidence"],
    "pod": ["carrier_name", "pod_age_hours", "aging_bucket", "invoice_blocked", "invoice_status", "severity", "evidence"],
    "detention": ["carrier_name", "chargeable_minutes", "estimated_charge", "currency", "severity", "evidence"],
    "update": ["carrier_name", "update_delay_minutes", "severity", "evidence"],
    "fuel": ["trip_id", "carrier_name", "liters", "evidence"],
    "gate": ["carrier_name", "severity", "evidence"],
    "ban": ["carrier_name", "city", "overlap_minutes", "severity", "evidence"],
}
METRIC_LABELS = {
    "late_trip_rate": "late trips",
    "missing_pod_rate": "missing POD",
    "overdue_pod_rate": "overdue POD",
    "rejected_pod_rate": "rejected POD",
    "detention_case_rate": "detention exposure",
    "update_exception_rate": "update discipline",
    "fuel_exception_rate": "fuel exceptions",
    "gate_exception_rate": "gate-truth gaps",
    "ban_conflict_rate": "ban-window conflicts",
    "invoice_blocker_rate": "invoice blockers",
    "data_completeness_rate": "data completeness",
}
SEVERITY_RANK = {"OK": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class CarrierScoreResult:
    """Structured outputs from a CarrierScore run."""

    carrier_scorecard: pd.DataFrame
    carrier_exception_summary: pd.DataFrame
    kpis: dict[str, float]
    config_warnings: list[str]


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


def _truthy(value: Any) -> bool:
    key = _normalize_key(value)
    return key in {"TRUE", "YES", "Y", "1", "BLOCKED", "ON HOLD", "NOT READY"}


def _enabled(value: Any) -> bool:
    key = _normalize_key(value)
    return key not in {"FALSE", "NO", "N", "0", "DISABLED"}


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def _to_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def prepare_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize required trip rows while preserving missing carrier cases."""
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
    source = source.dropna(subset=["trip_id"]).copy()
    source["carrier_name"] = source["carrier_name"].fillna("MISSING CARRIER")
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


def prepare_rules(
    df: pd.DataFrame | None,
    allow_uploaded: bool = True,
) -> tuple[dict[str, dict[str, float | str]], list[str]]:
    """Normalize optional score rules without crashing on invalid rows."""
    if df is None or df.empty or not allow_uploaded:
        return {metric: rule.copy() for metric, rule in DEFAULT_RULES.items()}, []
    source = _normalize_columns(df).dropna(how="all").copy()
    required = {"metric_name", "weight", "direction", "enabled", "good_threshold", "bad_threshold"}
    missing = sorted(required - set(source.columns))
    if missing:
        return {metric: rule.copy() for metric, rule in DEFAULT_RULES.items()}, [
            f"carrier_score_rules.csv missing columns: {', '.join(missing)}"
        ]

    warnings: list[str] = []
    rules: dict[str, dict[str, float | str]] = {}
    for row_number, row in enumerate(source.to_dict("records"), start=2):
        if not _enabled(row.get("enabled")):
            continue
        metric_name = _normalize_text(row.get("metric_name"))
        direction = _normalize_text(row.get("direction"))
        weight = pd.to_numeric(row.get("weight"), errors="coerce")
        if metric_name not in DEFAULT_RULES:
            warnings.append(f"row {row_number}: unknown metric_name {metric_name!r}")
            continue
        if direction not in {"lower_is_better", "higher_is_better"}:
            warnings.append(f"row {row_number}: invalid direction {direction!r}")
            continue
        if pd.isna(weight) or float(weight) <= 0:
            warnings.append(f"row {row_number}: invalid weight")
            continue
        try:
            rule = CarrierScoreRule(
                metric_name=metric_name,
                weight=float(weight),
                direction=direction,
                enabled=True,
                good_threshold=pd.to_numeric(row.get("good_threshold"), errors="coerce"),
                bad_threshold=pd.to_numeric(row.get("bad_threshold"), errors="coerce"),
            )
        except ValidationError as exc:
            warnings.append(f"row {row_number}: {exc.errors()[0]['msg']}")
            continue
        rules[rule.metric_name] = {"weight": rule.weight, "direction": rule.direction}

    if not rules:
        warnings.append("no valid enabled scoring rules; default rules used")
        return {metric: rule.copy() for metric, rule in DEFAULT_RULES.items()}, warnings

    total = sum(float(rule["weight"]) for rule in rules.values())
    scale = DEFAULT_WEIGHT_TOTAL / total if total else 1.0
    normalized = {
        metric: {"weight": round(float(rule["weight"]) * scale, 6), "direction": str(rule["direction"])}
        for metric, rule in rules.items()
    }
    return normalized, warnings


def prepare_optional_report(df: pd.DataFrame | None, source_name: str) -> pd.DataFrame:
    """Normalize one optional report and validate uploaded schema."""
    columns = [
        "trip_id",
        "carrier_name",
        "risk_bucket",
        "primary_delay_reason",
        "pod_gap_type",
        "aging_bucket",
        "invoice_blocked",
        "invoice_status",
        "chargeable_minutes",
        "estimated_charge",
        "update_gap_type",
        "fuel_event_id",
        "vehicle_id",
        "exception_type",
        "gate_truth_status",
        "overlap_minutes",
        "liters",
        "severity",
        "evidence",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    source = _normalize_columns(df).dropna(how="all").copy()
    _require_columns(source, SOURCE_REQUIRED_COLUMNS[source_name], OPTIONAL_SOURCES[source_name])
    for column in columns + SOURCE_OPTIONAL_COLUMNS[source_name]:
        if column not in source.columns:
            source[column] = pd.NA
    for column in [
        "trip_id",
        "carrier_name",
        "risk_bucket",
        "primary_delay_reason",
        "pod_gap_type",
        "aging_bucket",
        "invoice_status",
        "update_gap_type",
        "fuel_event_id",
        "vehicle_id",
        "exception_type",
        "gate_truth_status",
        "severity",
        "evidence",
    ]:
        source[column] = source[column].map(_normalize_text)
    for column in ["chargeable_minutes", "estimated_charge", "overlap_minutes", "liters"]:
        source[column] = pd.to_numeric(source[column], errors="coerce")
    source["invoice_blocked"] = source["invoice_blocked"].map(_truthy)
    source["severity"] = source["severity"].map(lambda value: _normalize_key(value) or "OK")
    return source[columns].reset_index(drop=True)


def _merge_carrier(report: pd.DataFrame, trips: pd.DataFrame) -> pd.DataFrame:
    if report.empty:
        return report
    merged = report.merge(trips[["trip_id", "carrier_name"]], on="trip_id", how="left", suffixes=("_report", ""))
    if "carrier_name_report" in merged.columns:
        merged["carrier_name"] = merged["carrier_name"].combine_first(merged["carrier_name_report"])
        merged = merged.drop(columns=["carrier_name_report"])
    if "carrier_name" not in merged.columns:
        merged["carrier_name"] = pd.NA
    merged["carrier_name"] = merged["carrier_name"].fillna("MISSING CARRIER")
    return merged


def _lane_count(carrier_trips: pd.DataFrame) -> int:
    lane_ids = carrier_trips["lane_id"].dropna()
    if not lane_ids.empty:
        return int(lane_ids.nunique())
    pairs = carrier_trips[["origin", "destination"]].dropna(how="any").drop_duplicates()
    return int(len(pairs))


def _delay_masks(delay: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if delay.empty:
        return pd.Series(dtype=bool), pd.Series(dtype=bool)
    reason = delay["primary_delay_reason"].map(_normalize_key)
    risk = delay["risk_bucket"].map(_normalize_key)
    on_time = (reason == "ON TIME") | (risk == "ON TIME")
    late_reasons = {"LATE DEPARTURE", "LATE ARRIVAL", "ENROUTE DELAY", "HUB DWELL"}
    late = risk.isin({"DELAYED", "CRITICAL"}) | reason.isin(late_reasons)
    return on_time, late


def _fallback_on_time_rate(carrier_trips: pd.DataFrame) -> float:
    timed = carrier_trips.dropna(subset=["delivered_time", "promised_arrival"])
    if timed.empty:
        return 0.0
    return round((timed["delivered_time"] <= timed["promised_arrival"]).mean(), 4)


def _summary_severity(
    source_name: str,
    exception_type: str,
    rows: pd.DataFrame,
    carrier_score: float,
    settings: CarrierScoreSettings,
) -> str:
    if carrier_score < 50:
        return "CRITICAL"
    exception_key = _normalize_key(exception_type)
    if source_name == "pod" and exception_key == "POD REJECTED" and rows["invoice_blocked"].any():
        return "CRITICAL"
    if source_name == "ban" and rows["overlap_minutes"].fillna(0).max() >= 120:
        return "CRITICAL"
    if source_name == "fuel" and len(rows) >= 3:
        return "CRITICAL"
    if source_name == "pod" and exception_key in {"POD OVERDUE", "OVERDUE POD"}:
        return "HIGH"
    if source_name == "detention" and rows["estimated_charge"].fillna(0).sum() >= settings.detention_exposure_high_threshold:
        return "HIGH"
    severity = rows["severity"].map(lambda value: SEVERITY_RANK.get(_normalize_key(value) or "OK", 0)).max()
    if severity >= 3:
        return "HIGH"
    if severity == 2 or len(rows) >= 2:
        return "MEDIUM"
    if severity == 1 or len(rows) == 1:
        return "LOW"
    return "OK"


def _risk_bucket(score: float, confidence: str, total_trips: int, usable_signals: bool, settings: CarrierScoreSettings) -> str:
    if total_trips < settings.minimum_trips_for_reliable_score or confidence == "DATA MISSING" or not usable_signals:
        return "INSUFFICIENT DATA"
    if score >= settings.excellent_threshold:
        return "EXCELLENT"
    if score >= settings.good_threshold:
        return "GOOD"
    if score >= settings.watch_threshold:
        return "WATCH"
    return "AT RISK"


def _confidence_bucket(total_trips: int, source_files_used: int, missing_carrier: bool) -> str:
    if missing_carrier:
        return "DATA MISSING"
    if total_trips >= 10 and source_files_used >= 4:
        return "HIGH"
    if total_trips >= 5 and source_files_used >= 2:
        return "MEDIUM"
    if source_files_used < 2:
        return "DATA LIMITED"
    return "LOW SAMPLE"


def _score(metrics: dict[str, float], rules: dict[str, dict[str, float | str]]) -> tuple[float, float]:
    penalty = 0.0
    for metric, rule in rules.items():
        value = metrics.get(metric, 0.0)
        if rule["direction"] == "higher_is_better":
            penalty += float(rule["weight"]) * max(0.0, 1 - value)
        else:
            penalty += float(rule["weight"]) * max(0.0, value)
    penalty = round(penalty, 2)
    return round(max(0.0, min(100.0, 100 - penalty)), 2), penalty


def _top_issue(metrics: dict[str, float], rules: dict[str, dict[str, float | str]]) -> str:
    impacts: dict[str, float] = {}
    for metric, rule in rules.items():
        value = metrics.get(metric, 0.0)
        impact = float(rule["weight"]) * (1 - value if rule["direction"] == "higher_is_better" else value)
        impacts[metric] = impact
    metric, impact = max(impacts.items(), key=lambda item: item[1])
    return "No dominant issue" if impact <= 0 else METRIC_LABELS.get(metric, metric)


def _issue_rows(source_name: str, report: pd.DataFrame) -> pd.DataFrame:
    if report.empty:
        return report
    if source_name == "delay":
        _, late = _delay_masks(report)
        rows = report[late].copy()
        rows["exception_type"] = "Late trip"
        return rows
    if source_name == "pod":
        pod_type = report["pod_gap_type"].map(_normalize_key)
        blocker = report["invoice_blocked"] | report["invoice_status"].map(_truthy)
        rows = report[pod_type.isin({"POD MISSING", "POD OVERDUE", "POD OVERDOW", "POD REJECTED"}) | blocker].copy()
        rows["exception_type"] = pod_type.loc[rows.index]
        return rows
    if source_name == "detention":
        risk = report["risk_bucket"].map(_normalize_key)
        rows = report[(risk == "DETENTION") | (report["chargeable_minutes"].fillna(0) > 0)].copy()
        rows["exception_type"] = "Detention case"
        return rows
    if source_name == "update":
        gap = report["update_gap_type"].map(_normalize_key)
        risk = report["risk_bucket"].map(_normalize_key)
        rows = report[(gap.notna() & (gap != "OK")) | (risk.notna() & (risk != "OK"))].copy()
        rows["exception_type"] = gap.loc[rows.index]
        return rows
    if source_name == "fuel":
        kind = report["exception_type"].map(_normalize_key)
        rows = report[kind.notna() & (kind != "OK")].copy()
        rows["exception_type"] = kind.loc[rows.index]
        return rows
    if source_name == "gate":
        status = report["gate_truth_status"].map(_normalize_key)
        kind = report["exception_type"].map(_normalize_key)
        rows = report[(status.notna() & (status != "OK")) | (kind.notna() & (kind != "OK"))].copy()
        rows["exception_type"] = kind.loc[rows.index].fillna(status.loc[rows.index])
        return rows
    if source_name == "ban":
        risk = report["risk_bucket"].map(_normalize_key)
        rows = report[risk == "BAN CONFLICT"].copy()
        rows["exception_type"] = "Ban conflict"
        return rows
    return report.iloc[0:0]


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
    """Build exact-contract carrier scorecard and exception summary outputs."""
    settings = settings or CarrierScoreSettings()
    trips = prepare_trips(trips_df)
    rules, warnings = prepare_rules(rules_df, settings.allow_uploaded_scoring_rules)
    optional_inputs = {
        "delay": delay_df,
        "pod": pod_df,
        "detention": detention_df,
        "update": update_df,
        "fuel": fuel_df,
        "gate": gate_df,
        "ban": ban_df,
    }
    uploaded_sources = [
        source_name
        for source_name, df in optional_inputs.items()
        if df is not None and not df.empty
    ]
    reports = {
        source_name: _merge_carrier(prepare_optional_report(df, source_name), trips)
        for source_name, df in optional_inputs.items()
    }

    score_rows: list[dict[str, Any]] = []
    pending_summary: list[dict[str, Any]] = []
    for carrier_name, carrier_trips in trips.groupby("carrier_name", sort=True):
        total_trips = len(carrier_trips)
        carrier_reports = {
            source_name: report[report["carrier_name"] == carrier_name].copy()
            for source_name, report in reports.items()
        }
        source_files_used = sum(
            1 for source_name in uploaded_sources if not carrier_reports[source_name].empty
        )
        expected_sources = len(uploaded_sources)
        data_completeness_rate = round(source_files_used / expected_sources, 4) if expected_sources else 0.0

        delay = carrier_reports["delay"]
        if not delay.empty:
            on_time_mask, late_mask = _delay_masks(delay)
            on_time_rate = _rate(int(delay[on_time_mask]["trip_id"].nunique()), total_trips)
            late_trip_ids = set(delay[late_mask]["trip_id"].dropna())
            late_trip_rate = _rate(len(late_trip_ids), total_trips)
        else:
            on_time_rate = _fallback_on_time_rate(carrier_trips) if delay_df is None else 0.0
            late_trip_rate = 0.0

        pod = carrier_reports["pod"]
        pod_type = pod["pod_gap_type"].map(_normalize_key) if not pod.empty else pd.Series(dtype=object)
        missing_pod = set(pod[pod_type == "POD MISSING"]["trip_id"].dropna()) if not pod.empty else set()
        overdue_pod = set(
            pod[
                (pod_type == "POD OVERDUE")
                | (pod_type == "POD OVERDOW")
                | (pod["aging_bucket"].map(_normalize_key).isin({"72H+", "7D+"}) & pod_type.isin({"POD MISSING", "POD OVERDUE", "POD OVERDOW"}))
            ]["trip_id"].dropna()
        ) if not pod.empty else set()
        rejected_pod = set(pod[pod_type == "POD REJECTED"]["trip_id"].dropna()) if not pod.empty else set()
        invoice_blockers = set(
            pod[(pod["invoice_blocked"]) | (pod["invoice_status"].map(_truthy))]["trip_id"].dropna()
        ) if not pod.empty else set()

        detention = carrier_reports["detention"]
        detention_cases = set(
            detention[
                (detention["risk_bucket"].map(_normalize_key) == "DETENTION")
                | (detention["chargeable_minutes"].fillna(0) > 0)
            ]["trip_id"].dropna()
        ) if not detention.empty else set()
        detention_exposure = round(float(detention["estimated_charge"].fillna(0).sum()), 2) if not detention.empty else 0.0

        update = carrier_reports["update"]
        update_cases = set(
            update[
                (update["update_gap_type"].map(_normalize_key) != "OK")
                | (update["risk_bucket"].map(_normalize_key) != "OK")
            ]["trip_id"].dropna()
        ) if not update.empty else set()

        fuel = carrier_reports["fuel"]
        fuel_cases = fuel[fuel["exception_type"].map(_normalize_key) != "OK"] if not fuel.empty else fuel
        fuel_trip_ids = set(fuel_cases["trip_id"].dropna()) if not fuel_cases.empty else set()
        fuel_denominator = total_trips
        fuel_liters = round(float(fuel_cases["liters"].fillna(0).sum()), 2) if not fuel_cases.empty else 0.0

        gate = carrier_reports["gate"]
        gate_cases = set(
            gate[
                (gate["gate_truth_status"].map(_normalize_key) != "OK")
                | (gate["exception_type"].map(_normalize_key).notna() & (gate["exception_type"].map(_normalize_key) != "OK"))
            ]["trip_id"].dropna()
        ) if not gate.empty else set()

        ban = carrier_reports["ban"]
        ban_conflicts = set(ban[ban["risk_bucket"].map(_normalize_key) == "BAN CONFLICT"]["trip_id"].dropna()) if not ban.empty else set()

        metrics = {
            "data_completeness_rate": data_completeness_rate,
            "on_time_rate": on_time_rate,
            "late_trip_rate": late_trip_rate,
            "missing_pod_rate": _rate(len(missing_pod), total_trips),
            "overdue_pod_rate": _rate(len(overdue_pod), total_trips),
            "rejected_pod_rate": _rate(len(rejected_pod), total_trips),
            "detention_case_rate": _rate(len(detention_cases), total_trips),
            "update_exception_rate": _rate(len(update_cases), total_trips),
            "fuel_exception_rate": _rate(len(fuel_trip_ids), fuel_denominator),
            "gate_exception_rate": _rate(len(gate_cases), total_trips),
            "ban_conflict_rate": _rate(len(ban_conflicts), total_trips),
            "invoice_blocker_rate": _rate(len(invoice_blockers), total_trips),
        }
        score, score_penalty = _score(metrics, rules)
        confidence = _confidence_bucket(total_trips, source_files_used, carrier_name == "MISSING CARRIER")
        usable_signals = source_files_used > 0 or (delay_df is None and on_time_rate > 0)
        risk = _risk_bucket(score, confidence, total_trips, usable_signals, settings)
        top_issue = _top_issue(metrics, rules)

        customer_count = int(carrier_trips["customer_name"].dropna().nunique())
        lane_count = _lane_count(carrier_trips)
        evidence = (
            f"{source_files_used} of {expected_sources} uploaded performance sources have usable rows; "
            f"score penalty is {score_penalty:.2f}."
        )
        suggested_action = (
            "Keep current carrier performance review cadence."
            if risk in {"EXCELLENT", "GOOD"}
            else "Review top issue and data gaps before the next carrier performance meeting."
        )
        score_rows.append(
            {
                "carrier_name": carrier_name,
                "total_trips": total_trips,
                "customer_count": customer_count,
                "lane_count": lane_count,
                "source_files_used": source_files_used,
                "data_completeness_rate": metrics["data_completeness_rate"],
                "on_time_rate": metrics["on_time_rate"],
                "late_trip_rate": metrics["late_trip_rate"],
                "missing_pod_rate": metrics["missing_pod_rate"],
                "overdue_pod_rate": metrics["overdue_pod_rate"],
                "rejected_pod_rate": metrics["rejected_pod_rate"],
                "detention_case_rate": metrics["detention_case_rate"],
                "update_exception_rate": metrics["update_exception_rate"],
                "fuel_exception_rate": metrics["fuel_exception_rate"],
                "gate_exception_rate": metrics["gate_exception_rate"],
                "ban_conflict_rate": metrics["ban_conflict_rate"],
                "invoice_blocker_rate": metrics["invoice_blocker_rate"],
                "estimated_detention_exposure": detention_exposure,
                "total_fuel_exception_liters": fuel_liters,
                "score": score,
                "score_penalty": score_penalty,
                "risk_bucket": risk,
                "confidence_bucket": confidence,
                "top_issue": top_issue,
                "evidence": evidence,
                "suggested_action": suggested_action,
            }
        )

        for source_name, report in carrier_reports.items():
            issues = _issue_rows(source_name, report)
            if issues.empty:
                continue
            for exception_type, rows in issues.groupby("exception_type", dropna=False):
                affected_trips = int(rows["trip_id"].dropna().nunique()) if source_name != "fuel" else int(
                    rows["trip_id"].dropna().nunique() or len(rows)
                )
                affected_rate = _rate(affected_trips, total_trips)
                pending_summary.append(
                    {
                        "carrier_name": carrier_name,
                        "exception_source": OPTIONAL_SOURCES[source_name],
                        "exception_type": _normalize_text(exception_type) or "Needs review",
                        "affected_trips": affected_trips,
                        "affected_rate": affected_rate,
                        "severity": _summary_severity(source_name, str(exception_type), rows, score, settings),
                        "evidence": f"{affected_trips} of {total_trips} trips affected.",
                        "suggested_action": "Review supporting evidence before the carrier performance discussion.",
                    }
                )

    scorecard = pd.DataFrame(score_rows, columns=SCORECARD_COLUMNS)
    if not scorecard.empty:
        scorecard = scorecard.sort_values(["score", "carrier_name"], ascending=[True, True]).reset_index(drop=True)
    summary = pd.DataFrame(pending_summary, columns=EXCEPTION_SUMMARY_COLUMNS)
    if not summary.empty:
        summary = summary.sort_values(["carrier_name", "exception_source", "exception_type"]).reset_index(drop=True)

    kpis = {
        "total_carriers": float(len(scorecard)),
        "total_trips": float(len(trips)),
        "at_risk_carriers": float((scorecard["risk_bucket"] == "AT RISK").sum()) if not scorecard.empty else 0.0,
        "watch_carriers": float((scorecard["risk_bucket"] == "WATCH").sum()) if not scorecard.empty else 0.0,
        "average_carrier_score": round(float(scorecard["score"].mean()), 1) if not scorecard.empty else 0.0,
        "lowest_carrier_score": round(float(scorecard["score"].min()), 1) if not scorecard.empty else 0.0,
        "insufficient_data_carriers": float((scorecard["risk_bucket"] == "INSUFFICIENT DATA").sum())
        if not scorecard.empty
        else 0.0,
    }
    return CarrierScoreResult(scorecard, summary, kpis, warnings)


def write_outputs(result: CarrierScoreResult, output_dir: Path) -> tuple[Path, Path]:
    """Write CarrierScore CSV outputs and return their paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scorecard_path = output_dir / "carrier_scorecard.csv"
    summary_path = output_dir / "carrier_exception_summary.csv"
    result.carrier_scorecard.to_csv(scorecard_path, index=False)
    result.carrier_exception_summary.to_csv(summary_path, index=False)
    return scorecard_path, summary_path
