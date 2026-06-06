"""Deterministic daily management brief engine for TowerBrief."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from tower_brief.models import TowerBriefSettings


SOURCE_FILES = {
    "trips.csv": "Trip Context",
    "eta_risk_board.csv": "ETA Watch",
    "detention_report.csv": "DetentionClock",
    "gate_truth_report.csv": "GateTruth",
    "fuel_exceptions.csv": "FuelGuard",
    "update_discipline_report.csv": "UpdatePulse",
    "delay_classification_report.csv": "DelayLens",
    "pod_aging_report.csv": "PODPulse",
    "ban_risk_board.csv": "BanWindow",
    "carrier_scorecard.csv": "CarrierScore",
}
OWNER_BY_SOURCE = {
    "Trip Context": "data_owner",
    "ETA Watch": "control_tower",
    "DetentionClock": "billing_or_operations",
    "GateTruth": "control_tower",
    "FuelGuard": "fleet_audit",
    "UpdatePulse": "dispatcher_or_control_tower",
    "DelayLens": "control_tower",
    "PODPulse": "documentation_or_billing",
    "BanWindow": "planning",
    "CarrierScore": "transport_manager",
    "Data gaps": "data_owner",
}
REQUIRED_COLUMNS = {
    "trips.csv": {"trip_id"},
    "eta_risk_board.csv": {"trip_id"},
    "detention_report.csv": {"trip_id"},
    "gate_truth_report.csv": {"trip_id"},
    "fuel_exceptions.csv": {"fuel_event_id", "vehicle_id", "exception_type"},
    "update_discipline_report.csv": {"trip_id"},
    "delay_classification_report.csv": {"trip_id"},
    "pod_aging_report.csv": {"trip_id"},
    "ban_risk_board.csv": {"trip_id"},
    "carrier_scorecard.csv": {"carrier_name"},
}
BRIEF_COLUMNS = [
    "brief_date",
    "section",
    "priority",
    "owner",
    "source_file",
    "source_product",
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "exception_type",
    "risk_bucket",
    "severity",
    "financial_exposure",
    "evidence",
    "suggested_action",
]
KPI_METRICS = [
    "files_used_count",
    "files_missing_count",
    "total_action_rows",
    "critical_actions",
    "high_priority_actions",
    "medium_priority_actions",
    "data_gaps",
    "unique_trips_impacted",
    "unique_customers_impacted",
    "unique_carriers_impacted",
    "estimated_detention_exposure",
    "pod_invoice_blockers",
    "ban_conflicts",
    "fuel_exceptions",
    "update_exceptions",
    "delayed_or_late_trips",
    "carrier_watchlist_count",
]
REQUIRED_MARKDOWN_SECTIONS = [
    "Daily Control Tower Brief",
    "Executive Summary",
    "KPI Snapshot",
    "Critical Actions",
    "High Priority Actions",
    "Financial Exposure",
    "Customer Risks",
    "Carrier Watchlist",
    "Delay and ETA Risks",
    "POD and Invoice Blockers",
    "Detention Exposure",
    "Fuel and Update Exceptions",
    "Ban Window Risks",
    "Data Gaps",
    "Files Used",
    "Files Missing",
    "Limitations",
]
PRIORITY_ORDER = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "DATA GAP": 1}
SEVERITY_ORDER = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "OK": 1, "": 0}
OK_VALUES = {"", "OK", "ON TIME", "NO DETENTION", "EXCELLENT", "GOOD", "READY", "APPROVED", "NO ACTION NEEDED"}


@dataclass(frozen=True)
class TowerBriefResult:
    """Structured outputs from a TowerBrief run."""

    action_table: pd.DataFrame
    kpi_snapshot: pd.DataFrame
    source_status: pd.DataFrame
    data_gaps: pd.DataFrame
    brief_markdown: str
    brief_html: str
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


def _normalize_key(value: Any) -> str:
    text = _normalize_text(value)
    return "" if text is None else " ".join(text.upper().replace("_", " ").split())


def _truthy(value: Any) -> bool:
    return _normalize_key(value) in {"TRUE", "YES", "Y", "1", "BLOCKED", "ON HOLD", "NOT READY"}


def _number(value: Any) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(parsed) else float(parsed)


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and _normalize_text(row.get(name)) is not None:
            return row.get(name)
    return None


def _read_csv(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def _priority_sort_key(value: str) -> int:
    return PRIORITY_ORDER.get(_normalize_key(value), 0)


def _severity_sort_key(value: str) -> int:
    return SEVERITY_ORDER.get(_normalize_key(value), 0)


def _context_lookup(trips: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if trips.empty or "trip_id" not in trips.columns:
        return {}
    for column in ["trip_id", "vehicle_id", "customer_name", "carrier_name"]:
        if column not in trips.columns:
            trips[column] = pd.NA
    trips["trip_id"] = trips["trip_id"].map(_normalize_text)
    trips = trips.dropna(subset=["trip_id"])
    return trips[["trip_id", "vehicle_id", "customer_name", "carrier_name"]].drop_duplicates("trip_id").set_index(
        "trip_id"
    ).to_dict("index")


def _exception_type(source_file: str, row: dict[str, Any]) -> str:
    value = _first_present(
        row,
        [
            "exception_type",
            "pod_gap_type",
            "update_gap_type",
            "primary_delay_reason",
            "top_issue",
            "risk_bucket",
            "gate_truth_status",
            "eta_status",
        ],
    )
    return _normalize_key(value) or ("CARRIER PERFORMANCE REVIEW" if source_file == "carrier_scorecard.csv" else "REVIEW")


def _risk_bucket(source_file: str, row: dict[str, Any]) -> str:
    value = _first_present(row, ["risk_bucket", "eta_status", "gate_truth_status", "confidence_bucket"])
    if source_file == "trips.csv":
        return "INFO"
    return _normalize_key(value) or "REVIEW"


def _severity(row: dict[str, Any]) -> str:
    explicit = _normalize_key(row.get("severity"))
    return explicit if explicit in SEVERITY_ORDER else ""


def _financial_exposure(source_file: str, row: dict[str, Any]) -> float:
    names = ["financial_exposure", "estimated_charge", "invoice_amount", "amount"]
    if source_file == "carrier_scorecard.csv":
        names.insert(0, "estimated_detention_exposure")
    for name in names:
        if name in row:
            parsed = pd.to_numeric(row.get(name), errors="coerce")
            if pd.notna(parsed):
                return round(float(parsed), 2)
    return 0.0


def _is_usable_action(source_file: str, row: dict[str, Any]) -> bool:
    if source_file == "trips.csv":
        return _normalize_key(row.get("risk_bucket")) == "INFO"
    risk = _risk_bucket(source_file, row)
    kind = _exception_type(source_file, row)
    severity = _severity(row)
    status = _normalize_key(_first_present(row, ["status", "gate_truth_status", "pod_status"]))
    if source_file == "carrier_scorecard.csv":
        return risk in {"WATCH", "AT RISK", "INSUFFICIENT DATA"} or _number(row.get("score")) < 75
    if source_file == "fuel_exceptions.csv":
        return kind not in OK_VALUES
    if source_file == "detention_report.csv":
        return risk == "DETENTION" or _number(row.get("chargeable_minutes")) > 0 or _number(row.get("estimated_charge")) > 0
    if source_file == "gate_truth_report.csv":
        return status not in OK_VALUES or kind not in OK_VALUES
    if source_file == "update_discipline_report.csv":
        return kind not in OK_VALUES or risk not in OK_VALUES
    if source_file == "delay_classification_report.csv":
        return risk not in OK_VALUES or kind not in OK_VALUES
    if source_file == "pod_aging_report.csv":
        return kind not in OK_VALUES or risk not in OK_VALUES or _truthy(row.get("invoice_blocked"))
    if source_file == "ban_risk_board.csv":
        return risk not in OK_VALUES
    return risk not in OK_VALUES or severity in {"MEDIUM", "HIGH", "CRITICAL"}


def _classify_priority(source_file: str, row: dict[str, Any], settings: TowerBriefSettings) -> str:
    severity = _severity(row)
    risk = _risk_bucket(source_file, row)
    kind = _exception_type(source_file, row)
    exposure = _financial_exposure(source_file, row)
    pod_age = max(_number(row.get("pod_age_hours")), _number(row.get("age_hours")))
    overlap = _number(row.get("overlap_minutes"))
    score = pd.to_numeric(row.get("score"), errors="coerce")

    if severity == "CRITICAL":
        return "CRITICAL"
    if risk in {"CRITICAL", "HIGH RISK", "AT RISK"}:
        return "CRITICAL"
    if source_file in {"eta_risk_board.csv", "delay_classification_report.csv"}:
        if _number(row.get("arrival_delay_minutes")) > 0 and risk in {"CRITICAL", "LATE"}:
            return "CRITICAL"
    if source_file == "detention_report.csv" and exposure >= settings.critical_detention_exposure:
        return "CRITICAL"
    if source_file == "pod_aging_report.csv":
        if kind == "POD REJECTED" and _truthy(row.get("invoice_blocked")):
            return "CRITICAL"
        if kind == "POD MISSING" and pod_age >= settings.critical_pod_age_hours:
            return "CRITICAL"
    if source_file == "ban_risk_board.csv" and risk == "BAN CONFLICT" and overlap >= settings.critical_ban_overlap_minutes:
        return "CRITICAL"
    if source_file == "carrier_scorecard.csv" and risk == "AT RISK":
        return "CRITICAL"
    if source_file == "fuel_exceptions.csv" and severity == "HIGH" and kind in {
        "DUPLICATE RECEIPT",
        "ODOMETER DROP",
        "NO GPS EVIDENCE",
    }:
        return "CRITICAL"

    if severity == "HIGH":
        return "HIGH"
    if risk in {"DELAYED", "REVIEW", "BAN CONFLICT"}:
        return "HIGH"
    if kind in {"POD OVERDUE", "POD OVERDOW"}:
        return "HIGH"
    if _truthy(row.get("invoice_blocked")):
        return "HIGH"
    if kind in {"MISSING ORIGIN EXIT", "MISSING DESTINATION ENTRY", "MISSING UPDATE"}:
        return "HIGH"
    if source_file == "detention_report.csv" and settings.high_detention_exposure <= exposure < settings.critical_detention_exposure:
        return "HIGH"
    if pd.notna(score) and float(score) < 75:
        return "HIGH"

    if risk == "WATCH":
        return "MEDIUM"
    if kind in {"LATE UPDATE", "APPROACHING FREE TIME", "POD MISSING", "VEHICLE CLASS UNKNOWN"}:
        return "MEDIUM"
    if not _normalize_text(row.get("evidence")) and source_file != "trips.csv":
        return "MEDIUM"
    return "LOW"


def _owner(source_product: str, priority: str) -> str:
    if priority == "DATA GAP":
        return "data_owner"
    return OWNER_BY_SOURCE[source_product]


def _evidence(source_file: str, row: dict[str, Any]) -> str:
    explicit = _normalize_text(row.get("evidence"))
    if explicit:
        return explicit
    trip = _normalize_text(row.get("trip_id"))
    if trip:
        return f"{SOURCE_FILES[source_file]} flagged trip {trip}; source evidence was not provided."
    return f"{SOURCE_FILES[source_file]} row requires review; source evidence was not provided."


def _suggested_action(source_product: str, row: dict[str, Any], priority: str) -> str:
    explicit = _normalize_text(row.get("suggested_action"))
    if explicit:
        return explicit
    if priority == "CRITICAL":
        return "Escalate today and confirm accountable recovery owner."
    if priority == "HIGH":
        return "Review evidence and confirm same-day action plan."
    if source_product == "PODPulse":
        return "Confirm POD and invoice readiness."
    if source_product == "CarrierScore":
        return "Review carrier trend and corrective follow-up."
    return "Review source row and update action status."


def _section(source_file: str, row: dict[str, Any], priority: str) -> str:
    source_product = SOURCE_FILES.get(source_file, "Data gaps")
    kind = _exception_type(source_file, row)
    if priority == "DATA GAP":
        return "Data Gaps"
    if source_product in {"ETA Watch", "DelayLens"}:
        return "Delay and ETA Risks"
    if source_product == "PODPulse":
        return "POD and Invoice Blockers"
    if source_product == "DetentionClock":
        return "Detention Exposure"
    if source_product in {"FuelGuard", "UpdatePulse"}:
        return "Fuel and Update Exceptions"
    if source_product == "BanWindow":
        return "Ban Window Risks"
    if source_product == "CarrierScore":
        return "Carrier Watchlist"
    if "CUSTOMER" in kind:
        return "Customer Risks"
    if priority in {"CRITICAL", "HIGH"}:
        return "Critical Actions" if priority == "CRITICAL" else "High Priority Actions"
    return "Executive Summary"


def _action_row(
    source_file: str,
    raw: dict[str, Any],
    trip_context: dict[str, dict[str, Any]],
    settings: TowerBriefSettings,
) -> dict[str, Any]:
    source_product = SOURCE_FILES[source_file]
    trip_id = _normalize_text(raw.get("trip_id")) or ""
    context = trip_context.get(trip_id, {})
    priority = _classify_priority(source_file, raw, settings)
    severity = _severity(raw) or ("HIGH" if priority in {"CRITICAL", "HIGH"} else "LOW")
    row = {
        "brief_date": settings.brief_date,
        "section": "",
        "priority": priority,
        "owner": _owner(source_product, priority),
        "source_file": source_file,
        "source_product": source_product,
        "trip_id": trip_id,
        "vehicle_id": _normalize_text(raw.get("vehicle_id")) or _normalize_text(context.get("vehicle_id")) or "",
        "customer_name": _normalize_text(raw.get("customer_name")) or _normalize_text(context.get("customer_name")) or "",
        "carrier_name": _normalize_text(raw.get("carrier_name")) or _normalize_text(context.get("carrier_name")) or "",
        "exception_type": _exception_type(source_file, raw),
        "risk_bucket": _risk_bucket(source_file, raw),
        "severity": severity,
        "financial_exposure": _financial_exposure(source_file, raw),
        "evidence": _evidence(source_file, raw),
        "suggested_action": _suggested_action(source_product, raw, priority),
    }
    row["section"] = _section(source_file, raw, priority)
    return row


def _data_gap_row(
    settings: TowerBriefSettings,
    source_file: str,
    source_product: str,
    exception_type: str,
    evidence: str,
    suggested_action: str = "Fix the source file and rerun TowerBrief.",
) -> dict[str, Any]:
    return {
        "brief_date": settings.brief_date,
        "section": "Data Gaps",
        "priority": "DATA GAP",
        "owner": "data_owner",
        "source_file": source_file,
        "source_product": source_product,
        "trip_id": "",
        "vehicle_id": "",
        "customer_name": "",
        "carrier_name": "",
        "exception_type": exception_type,
        "risk_bucket": "DATA GAP",
        "severity": "LOW",
        "financial_exposure": 0.0,
        "evidence": evidence,
        "suggested_action": suggested_action,
    }


def _context_gap_rows(
    action: dict[str, Any],
    settings: TowerBriefSettings,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    missing = []
    if not action["trip_id"] and action["source_product"] != "CarrierScore":
        missing.append("trip_id")
    if not action["customer_name"] and action["source_product"] not in {"CarrierScore", "FuelGuard"}:
        missing.append("customer_name")
    if not action["carrier_name"] and action["source_product"] != "FuelGuard":
        missing.append("carrier_name")
    if missing:
        gaps.append(
            _data_gap_row(
                settings,
                action["source_file"],
                "Data gaps",
                "MISSING CONTEXT",
                f"{action['source_file']} row is missing context fields: {', '.join(missing)}.",
                "Add missing trip, customer, or carrier context where available.",
            )
        )
    return gaps


def _normalize_source(
    source_file: str,
    df: pd.DataFrame | None,
    trip_context: dict[str, dict[str, Any]],
    settings: TowerBriefSettings,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    if df is None:
        return [], "MISSING", []
    source_product = SOURCE_FILES[source_file]
    source = _normalize_columns(df).dropna(how="all").copy()
    if source.empty:
        return [
            _data_gap_row(settings, source_file, "Data gaps", "NO USABLE ROWS", f"{source_file} was provided but empty.")
        ], "DATA MISSING", [f"{source_file} DATA MISSING: source file provided but empty"]

    missing = sorted(REQUIRED_COLUMNS[source_file] - set(source.columns))
    if missing:
        warning = f"{source_file} DATA MISSING: missing required columns: {', '.join(missing)}"
        return [
            _data_gap_row(settings, source_file, "Data gaps", "MISSING REQUIRED COLUMNS", warning)
        ], "DATA MISSING", [warning]

    rows: list[dict[str, Any]] = []
    for raw in source.to_dict("records"):
        if _is_usable_action(source_file, raw):
            action = _action_row(source_file, raw, trip_context, settings)
            rows.append(action)
            rows.extend(_context_gap_rows(action, settings))

    if not rows:
        return [
            _data_gap_row(
                settings,
                source_file,
                "Data gaps",
                "NO USABLE ROWS",
                f"{source_product} file was provided but no actionable rows were found.",
                "Confirm the source product exported exception or OK rows as expected.",
            )
        ], "USED", []
    return rows, "USED", []


def _deduplicate(actions: pd.DataFrame) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame(columns=BRIEF_COLUMNS)
    deduped_rows: list[dict[str, Any]] = []
    for _, group in actions.groupby(["source_product", "trip_id", "exception_type", "risk_bucket"], dropna=False, sort=False):
        ranked = group.copy()
        ranked["_priority_score"] = ranked["priority"].map(_priority_sort_key)
        ranked["_severity_score"] = ranked["severity"].map(_severity_sort_key)
        ranked["_evidence_len"] = ranked["evidence"].map(lambda value: len(str(value)))
        ranked["_action_len"] = ranked["suggested_action"].map(lambda value: len(str(value)))
        best = ranked.sort_values(
            ["_priority_score", "_severity_score", "_evidence_len", "_action_len"],
            ascending=[False, False, False, False],
        ).iloc[0]
        deduped_rows.append({column: best[column] for column in BRIEF_COLUMNS})
    return pd.DataFrame(deduped_rows, columns=BRIEF_COLUMNS)


def _sort_actions(actions: pd.DataFrame) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame(columns=BRIEF_COLUMNS)
    sorted_actions = actions.copy()
    sorted_actions["_priority_score"] = sorted_actions["priority"].map(_priority_sort_key)
    sorted_actions["_severity_score"] = sorted_actions["severity"].map(_severity_sort_key)
    sorted_actions = sorted_actions.sort_values(
        ["_priority_score", "_severity_score", "financial_exposure", "source_product", "trip_id", "exception_type"],
        ascending=[False, False, False, True, True, True],
    )
    return sorted_actions[BRIEF_COLUMNS].reset_index(drop=True)


def _kpis(actions: pd.DataFrame, source_status: pd.DataFrame) -> pd.DataFrame:
    non_gap = actions[actions["priority"] != "DATA GAP"] if not actions.empty else actions
    metrics = {
        "files_used_count": int((source_status["status"] == "USED").sum()),
        "files_missing_count": int((source_status["status"] == "MISSING").sum()),
        "total_action_rows": len(actions),
        "critical_actions": int((actions["priority"] == "CRITICAL").sum()) if not actions.empty else 0,
        "high_priority_actions": int((actions["priority"] == "HIGH").sum()) if not actions.empty else 0,
        "medium_priority_actions": int((actions["priority"] == "MEDIUM").sum()) if not actions.empty else 0,
        "data_gaps": int((actions["priority"] == "DATA GAP").sum()) if not actions.empty else 0,
        "unique_trips_impacted": int(non_gap["trip_id"].replace("", pd.NA).dropna().nunique()) if not actions.empty else 0,
        "unique_customers_impacted": int(non_gap["customer_name"].replace("", pd.NA).dropna().nunique()) if not actions.empty else 0,
        "unique_carriers_impacted": int(non_gap["carrier_name"].replace("", pd.NA).dropna().nunique()) if not actions.empty else 0,
        "estimated_detention_exposure": round(float(actions[actions["source_product"] == "DetentionClock"]["financial_exposure"].sum()), 2)
        if not actions.empty
        else 0.0,
        "pod_invoice_blockers": int(
            (actions["source_product"].eq("PODPulse") & actions["exception_type"].str.contains("POD|INVOICE", na=False)).sum()
        )
        if not actions.empty
        else 0,
        "ban_conflicts": int(
            (actions["source_product"].eq("BanWindow") & actions["risk_bucket"].eq("BAN CONFLICT")).sum()
        )
        if not actions.empty
        else 0,
        "fuel_exceptions": int(actions["source_product"].eq("FuelGuard").sum()) if not actions.empty else 0,
        "update_exceptions": int(actions["source_product"].eq("UpdatePulse").sum()) if not actions.empty else 0,
        "delayed_or_late_trips": int(
            (actions["source_product"].isin(["ETA Watch", "DelayLens"]) & actions["priority"].isin(["CRITICAL", "HIGH", "MEDIUM"])).sum()
        )
        if not actions.empty
        else 0,
        "carrier_watchlist_count": int(
            (actions["source_product"].eq("CarrierScore") & actions["risk_bucket"].isin(["WATCH", "AT RISK"])).sum()
        )
        if not actions.empty
        else 0,
    }
    return pd.DataFrame([{"metric": metric, "value": metrics[metric]} for metric in KPI_METRICS])


def _format_number(value: Any) -> str:
    number = pd.to_numeric(value, errors="coerce")
    if pd.notna(number):
        return str(int(number)) if float(number).is_integer() else str(round(float(number), 2))
    return str(value)


def _bullets(rows: pd.DataFrame, limit: int | None = None) -> list[str]:
    if rows.empty:
        return ["- None."]
    subset = rows.head(limit) if limit else rows
    return [
        "- "
        f"{row['priority']} | {row['source_product']} | {row['exception_type']} | "
        f"owner: {row['owner']} | trip: {row['trip_id'] or 'n/a'} | "
        f"customer: {row['customer_name'] or 'n/a'} | carrier: {row['carrier_name'] or 'n/a'} | "
        f"exposure: {_format_number(row['financial_exposure'])} | {row['suggested_action']}"
        for row in subset.to_dict("records")
    ]


def _brief_markdown(
    actions: pd.DataFrame,
    kpis: pd.DataFrame,
    source_status: pd.DataFrame,
    settings: TowerBriefSettings,
) -> str:
    metric = dict(zip(kpis["metric"], kpis["value"], strict=True))
    sections: list[tuple[str, list[str]]] = [
        (
            "Daily Control Tower Brief",
            [
                f"Date: {settings.brief_date}",
                "TowerBrief consolidates local product-output files into one deterministic daily management brief.",
            ],
        ),
        (
            "Executive Summary",
            [
                f"- Open action rows: {_format_number(metric['total_action_rows'])}",
                f"- Critical actions: {_format_number(metric['critical_actions'])}",
                f"- High priority actions: {_format_number(metric['high_priority_actions'])}",
                f"- Data gaps: {_format_number(metric['data_gaps'])}",
            ],
        ),
        (
            "KPI Snapshot",
            [f"- {row['metric']}: {_format_number(row['value'])}" for row in kpis.to_dict("records")],
        ),
        (
            "Critical Actions",
            _bullets(actions[actions["priority"] == "CRITICAL"], settings.max_critical_rows),
        ),
        (
            "High Priority Actions",
            _bullets(actions[actions["priority"] == "HIGH"], settings.max_high_priority_rows),
        ),
        (
            "Financial Exposure",
            _bullets(actions[actions["financial_exposure"] > 0]),
        ),
        (
            "Customer Risks",
            _bullets(actions[(actions["customer_name"] != "") & (actions["source_product"] != "Trip Context")]),
        ),
        (
            "Carrier Watchlist",
            _bullets(actions[actions["source_product"] == "CarrierScore"]),
        ),
        (
            "Delay and ETA Risks",
            _bullets(actions[actions["source_product"].isin(["ETA Watch", "DelayLens"])]),
        ),
        (
            "POD and Invoice Blockers",
            _bullets(actions[actions["source_product"] == "PODPulse"]),
        ),
        (
            "Detention Exposure",
            _bullets(actions[actions["source_product"] == "DetentionClock"]),
        ),
        (
            "Fuel and Update Exceptions",
            _bullets(actions[actions["source_product"].isin(["FuelGuard", "UpdatePulse"])]),
        ),
        (
            "Ban Window Risks",
            _bullets(actions[actions["source_product"] == "BanWindow"]),
        ),
        (
            "Data Gaps",
            _bullets(actions[actions["priority"] == "DATA GAP"]),
        ),
        (
            "Files Used",
            [
                f"- {row['source_file']} ({row['source_product']})"
                for row in source_status[source_status["status"] == "USED"].to_dict("records")
            ]
            or ["- None."],
        ),
        (
            "Files Missing",
            [
                f"- {row['source_file']} ({row['source_product']})"
                for row in source_status[source_status["status"] == "MISSING"].to_dict("records")
            ]
            or ["- None."],
        ),
        (
            "Limitations",
            [
                "- Deterministic and file-based.",
                "- Synthetic demo data only.",
                "- No AI-generated narrative, paid APIs, live integrations, database backend, BI server, login system, workflow engine, email, WhatsApp, or Telegram automation.",
                "- Missing source files reduce coverage but do not block export generation.",
            ],
        ),
    ]
    lines: list[str] = []
    for index, (title, body) in enumerate(sections):
        lines.append(f"# {title}" if index == 0 else f"## {title}")
        lines.append("")
        lines.extend(body)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _brief_html(markdown: str) -> str:
    html_lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            html_lines.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("- "):
            html_lines.append(f"<p>{escape(line)}</p>")
        elif line:
            html_lines.append(f"<p>{escape(line)}</p>")
    body = "\n".join(html_lines)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Daily Control Tower Brief</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #172033; line-height: 1.35; }}
    h1 {{ font-size: 26px; border-bottom: 2px solid #172033; padding-bottom: 8px; }}
    h2 {{ font-size: 18px; margin-top: 22px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px; }}
    p {{ margin: 6px 0; font-size: 13px; }}
    @media print {{ body {{ margin: 16px; }} h2 {{ break-after: avoid; }} }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def run_tower_brief(
    inputs: dict[str, pd.DataFrame | None],
    settings: TowerBriefSettings | None = None,
) -> TowerBriefResult:
    """Build an exact-contract deterministic daily brief from available product outputs."""
    settings = settings or TowerBriefSettings()
    warnings: list[str] = []
    normalized_inputs = {
        name: (_normalize_columns(df).dropna(how="all").copy() if df is not None else None) for name, df in inputs.items()
    }
    provided_files = [name for name, df in normalized_inputs.items() if df is not None]
    trips = normalized_inputs.get("trips.csv")
    trip_context = _context_lookup(trips.copy()) if trips is not None else {}

    action_rows: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    if not provided_files:
        action_rows.append(
            _data_gap_row(
                settings,
                "ALL FILES",
                "Data gaps",
                "NO SOURCE FILES UPLOADED",
                "No recognized source files were uploaded or found in the input directory.",
                "Upload at least one source product output or use the demo data pack.",
            )
        )

    for source_file, source_product in SOURCE_FILES.items():
        rows, status, source_warnings = _normalize_source(source_file, normalized_inputs.get(source_file), trip_context, settings)
        action_rows.extend(rows)
        warnings.extend(source_warnings)
        statuses.append({"source_file": source_file, "source_product": source_product, "status": status})

    source_status = pd.DataFrame(statuses)
    action_table = _sort_actions(_deduplicate(pd.DataFrame(action_rows)))
    data_gaps = action_table[action_table["priority"] == "DATA GAP"].reset_index(drop=True)
    kpi_snapshot = _kpis(action_table, source_status)
    markdown = _brief_markdown(action_table, kpi_snapshot, source_status, settings)
    html = _brief_html(markdown)
    return TowerBriefResult(action_table, kpi_snapshot, source_status, data_gaps, markdown, html, warnings)


def read_input_directory(input_dir: Path) -> dict[str, pd.DataFrame | None]:
    """Read all recognized TowerBrief source files from a directory."""
    return {source_file: _read_csv(input_dir / source_file) for source_file in SOURCE_FILES}


def write_outputs(result: TowerBriefResult, output_dir: Path) -> tuple[Path, Path, Path]:
    """Write TowerBrief markdown, HTML, and CSV outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "daily_control_tower_brief.md"
    html_path = output_dir / "daily_control_tower_brief.html"
    csv_path = output_dir / "daily_control_tower_brief.csv"
    markdown_path.write_text(result.brief_markdown, encoding="utf-8")
    html_path.write_text(result.brief_html, encoding="utf-8")
    result.action_table.to_csv(csv_path, index=False)
    return markdown_path, html_path, csv_path


def main() -> None:
    """Run TowerBrief from the command line."""
    parser = argparse.ArgumentParser(description="Generate a deterministic daily control tower brief.")
    parser.add_argument("input_dir", nargs="?", default="tower_brief/demo_data")
    parser.add_argument("output_dir", nargs="?", default="tower_brief/output")
    parser.add_argument("--brief-date", default="2026-06-06")
    args = parser.parse_args()
    result = run_tower_brief(read_input_directory(Path(args.input_dir)), TowerBriefSettings(brief_date=args.brief_date))
    markdown_path, html_path, csv_path = write_outputs(result, Path(args.output_dir))
    print(f"Wrote {markdown_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote {csv_path}")
    print(f"Rows: {len(result.action_table)}")
    if result.config_warnings:
        print("Warnings:")
        for warning in result.config_warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
