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
ACTION_COLUMNS = [
    "priority_rank",
    "priority_bucket",
    "owner",
    "source_product",
    "source_file",
    "trip_id",
    "vehicle_id",
    "customer_name",
    "carrier_name",
    "exception_type",
    "risk_bucket",
    "severity",
    "evidence",
    "suggested_action",
    "financial_exposure",
    "status",
]
KPI_COLUMNS = ["metric", "value"]
SEVERITY_SCORE = {"OK": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
RISK_SCORE = {
    "ON TIME": 0,
    "OK": 0,
    "EXCELLENT": 0,
    "GOOD": 1,
    "WATCH": 2,
    "DELAYED": 3,
    "HIGH": 3,
    "AT RISK": 4,
    "CRITICAL": 4,
    "BAN CONFLICT": 4,
    "INSUFFICIENT DATA": 2,
}


@dataclass(frozen=True)
class TowerBriefResult:
    """Structured outputs from a TowerBrief run."""

    action_table: pd.DataFrame
    kpi_snapshot: pd.DataFrame
    source_status: pd.DataFrame
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


def _first_present(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if name in row and _normalize_text(row.get(name)) is not None:
            return row.get(name)
    return None


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_csv(path)


def _is_exception(source_file: str, row: dict[str, Any]) -> bool:
    risk = _normalize_key(_first_present(row, ["risk_bucket", "eta_status", "score_risk_bucket"]))
    severity = _normalize_key(row.get("severity"))
    kind = _normalize_key(_first_present(row, ["exception_type", "pod_gap_type", "update_gap_type", "primary_delay_reason"]))
    status = _normalize_key(_first_present(row, ["gate_truth_status", "pod_status", "status"]))
    if source_file == "trips.csv":
        return False
    if source_file == "carrier_scorecard.csv":
        return risk in {"WATCH", "AT RISK", "INSUFFICIENT DATA"} or pd.to_numeric(row.get("score"), errors="coerce") < 75
    if source_file == "fuel_exceptions.csv":
        return bool(kind and kind != "OK")
    if source_file == "detention_report.csv":
        return risk == "DETENTION" or pd.to_numeric(row.get("chargeable_minutes"), errors="coerce") > 0
    if source_file == "gate_truth_report.csv":
        return (status and status != "OK") or bool(kind and kind != "OK")
    if source_file == "update_discipline_report.csv":
        return bool(kind and kind != "OK") or bool(risk and risk != "OK")
    if source_file == "delay_classification_report.csv":
        return risk in {"DELAYED", "CRITICAL"} or kind in {"LATE DEPARTURE", "LATE ARRIVAL", "ENROUTE DELAY", "HUB DWELL"}
    if source_file == "pod_aging_report.csv":
        return kind in {"POD MISSING", "POD OVERDUE", "POD OVERDOW", "POD REJECTED"} or risk not in {"", "OK"}
    if source_file == "ban_risk_board.csv":
        return risk == "BAN CONFLICT"
    return risk not in {"", "OK", "ON TIME", "EXCELLENT", "GOOD"} or severity in {"MEDIUM", "HIGH", "CRITICAL"}


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
        ],
    )
    text = _normalize_text(value)
    if text:
        return _normalize_key(text)
    return "REVIEW REQUIRED" if source_file != "carrier_scorecard.csv" else "CARRIER PERFORMANCE REVIEW"


def _severity(source_file: str, row: dict[str, Any], settings: TowerBriefSettings) -> str:
    explicit = _normalize_key(row.get("severity"))
    if explicit in SEVERITY_SCORE:
        return explicit
    risk = _normalize_key(row.get("risk_bucket"))
    kind = _exception_type(source_file, row)
    score = pd.to_numeric(row.get("score"), errors="coerce")
    exposure = _financial_exposure(source_file, row)
    liters = pd.to_numeric(row.get("liters"), errors="coerce")
    if source_file == "carrier_scorecard.csv" and pd.notna(score):
        if score < 50:
            return "CRITICAL"
        if score < 60:
            return "HIGH"
        if score < 75:
            return "MEDIUM"
    if kind == "POD REJECTED" and _truthy(row.get("invoice_blocked")):
        return "CRITICAL"
    if risk in {"CRITICAL", "AT RISK", "BAN CONFLICT"}:
        return "CRITICAL" if risk in {"CRITICAL", "BAN CONFLICT"} else "HIGH"
    if exposure >= settings.detention_exposure_threshold:
        return "HIGH"
    if pd.notna(liters) and liters >= settings.fuel_liter_threshold:
        return "HIGH"
    if kind in {"POD OVERDUE", "POD OVERDOW", "LATE ARRIVAL", "LATE DEPARTURE"}:
        return "HIGH"
    if risk in {"DELAYED", "WATCH", "INSUFFICIENT DATA"}:
        return "MEDIUM"
    return "LOW"


def _truthy(value: Any) -> bool:
    return _normalize_key(value) in {"TRUE", "YES", "Y", "1", "BLOCKED", "ON HOLD", "NOT READY"}


def _financial_exposure(source_file: str, row: dict[str, Any]) -> float:
    values = []
    if source_file == "detention_report.csv":
        values.append(row.get("estimated_charge"))
    if source_file == "carrier_scorecard.csv":
        values.append(row.get("estimated_detention_exposure"))
    for name in ["estimated_charge", "financial_exposure", "amount"]:
        values.append(row.get(name))
    for value in values:
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number):
            return round(float(number), 2)
    return 0.0


def _owner(source_file: str, row: dict[str, Any], severity: str) -> str:
    kind = _exception_type(source_file, row)
    if severity == "CRITICAL":
        return "Control Tower Manager"
    if source_file in {"eta_risk_board.csv", "delay_classification_report.csv", "update_discipline_report.csv"}:
        return "Dispatch Lead"
    if source_file in {"pod_aging_report.csv", "detention_report.csv"}:
        return "Billing Review"
    if source_file in {"fuel_exceptions.csv", "gate_truth_report.csv", "ban_risk_board.csv"}:
        return "Fleet Supervisor"
    if source_file == "carrier_scorecard.csv" or "CARRIER" in kind:
        return "Carrier Manager"
    return "Control Tower Analyst"


def _suggested_action(source_file: str, row: dict[str, Any], severity: str) -> str:
    explicit = _normalize_text(row.get("suggested_action"))
    if explicit:
        return explicit
    owner = _owner(source_file, row, severity)
    kind = _exception_type(source_file, row).lower()
    if severity == "CRITICAL":
        return f"Escalate to {owner} and confirm recovery owner today."
    if "pod" in kind:
        return "Confirm POD evidence and invoice readiness."
    if source_file == "detention_report.csv":
        return "Review dwell evidence and charge estimate before billing."
    if source_file == "carrier_scorecard.csv":
        return "Review carrier trend and agree corrective follow-up."
    return "Review evidence and update the action owner."


def _context_lookup(trips: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if trips.empty or "trip_id" not in trips.columns:
        return {}
    context_columns = ["trip_id", "vehicle_id", "customer_name", "carrier_name"]
    for column in context_columns:
        if column not in trips.columns:
            trips[column] = pd.NA
    return trips[context_columns].drop_duplicates("trip_id").set_index("trip_id").to_dict("index")


def _normalize_source(
    source_file: str,
    df: pd.DataFrame | None,
    trip_context: dict[str, dict[str, Any]],
    settings: TowerBriefSettings,
) -> tuple[list[dict[str, Any]], str, str | None]:
    if df is None:
        return [], "MISSING", None
    source = _normalize_columns(df).dropna(how="all").copy()
    missing = sorted(REQUIRED_COLUMNS[source_file] - set(source.columns))
    if missing:
        warning = f"{source_file} DATA MISSING: missing required columns: {', '.join(missing)}"
        return [], "DATA MISSING", warning
    rows: list[dict[str, Any]] = []
    for raw in source.to_dict("records"):
        if not _is_exception(source_file, raw):
            continue
        trip_id = _normalize_text(raw.get("trip_id"))
        context = trip_context.get(trip_id or "", {})
        severity = _severity(source_file, raw, settings)
        rows.append(
            {
                "priority_rank": 0,
                "priority_bucket": "",
                "owner": _owner(source_file, raw, severity),
                "source_product": SOURCE_FILES[source_file],
                "source_file": source_file,
                "trip_id": trip_id or "",
                "vehicle_id": _normalize_text(raw.get("vehicle_id")) or _normalize_text(context.get("vehicle_id")) or "",
                "customer_name": _normalize_text(raw.get("customer_name")) or _normalize_text(context.get("customer_name")) or "",
                "carrier_name": _normalize_text(raw.get("carrier_name")) or _normalize_text(context.get("carrier_name")) or "",
                "exception_type": _exception_type(source_file, raw),
                "risk_bucket": _normalize_key(raw.get("risk_bucket")) or _normalize_key(raw.get("gate_truth_status")) or "REVIEW",
                "severity": severity,
                "evidence": _normalize_text(raw.get("evidence")) or "Source row requires review.",
                "suggested_action": _suggested_action(source_file, raw, severity),
                "financial_exposure": _financial_exposure(source_file, raw),
                "status": "OPEN",
            }
        )
    return rows, "USED", None


def _prioritize(actions: pd.DataFrame) -> pd.DataFrame:
    if actions.empty:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    prioritized = actions.copy()
    prioritized["_severity_score"] = prioritized["severity"].map(lambda value: SEVERITY_SCORE.get(_normalize_key(value), 1))
    prioritized["_risk_score"] = prioritized["risk_bucket"].map(lambda value: RISK_SCORE.get(_normalize_key(value), 1))
    prioritized = prioritized.sort_values(
        ["_severity_score", "_risk_score", "financial_exposure", "source_product", "trip_id"],
        ascending=[False, False, False, True, True],
    ).reset_index(drop=True)
    prioritized["priority_rank"] = range(1, len(prioritized) + 1)
    prioritized["priority_bucket"] = prioritized["_severity_score"].map(
        lambda score: "P1" if score >= 4 else "P2" if score == 3 else "P3" if score == 2 else "P4"
    )
    return prioritized[ACTION_COLUMNS]


def _kpis(actions: pd.DataFrame, source_status: pd.DataFrame, trips: pd.DataFrame) -> pd.DataFrame:
    metrics = {
        "total_trips": len(trips.drop_duplicates("trip_id")) if "trip_id" in trips.columns else 0,
        "open_actions": len(actions),
        "critical_actions": int((actions["severity"] == "CRITICAL").sum()) if not actions.empty else 0,
        "high_actions": int((actions["severity"] == "HIGH").sum()) if not actions.empty else 0,
        "customers_exposed": int(actions["customer_name"].replace("", pd.NA).dropna().nunique()) if not actions.empty else 0,
        "carriers_exposed": int(actions["carrier_name"].replace("", pd.NA).dropna().nunique()) if not actions.empty else 0,
        "financial_exposure": round(float(actions["financial_exposure"].sum()), 2) if not actions.empty else 0.0,
        "source_files_used": int((source_status["status"] == "USED").sum()),
        "source_files_missing": int((source_status["status"] == "MISSING").sum()),
        "source_files_data_missing": int((source_status["status"] == "DATA MISSING").sum()),
    }
    return pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()], columns=KPI_COLUMNS)


def _brief_markdown(
    actions: pd.DataFrame,
    kpis: pd.DataFrame,
    source_status: pd.DataFrame,
    warnings: list[str],
    settings: TowerBriefSettings,
) -> str:
    metric = dict(zip(kpis["metric"], kpis["value"], strict=True))

    def format_metric(value: object) -> str:
        number = pd.to_numeric(value, errors="coerce")
        if pd.notna(number):
            return str(int(number)) if float(number).is_integer() else str(round(float(number), 2))
        return str(value)

    lines = [
        "# Daily Control Tower Brief",
        "",
        f"Date: {settings.brief_date}",
        "",
        "## Executive Snapshot",
        "",
        f"- Open actions: {format_metric(metric['open_actions'])}",
        f"- Critical actions: {format_metric(metric['critical_actions'])}",
        f"- Customers exposed: {format_metric(metric['customers_exposed'])}",
        f"- Carriers exposed: {format_metric(metric['carriers_exposed'])}",
        f"- Financial exposure: {format_metric(metric['financial_exposure'])}",
        f"- Source files used: {format_metric(metric['source_files_used'])}",
        "",
        "## Top Actions",
        "",
    ]
    if actions.empty:
        lines.append("- No open exceptions found in the available files.")
    else:
        for row in actions.head(settings.high_priority_limit).to_dict("records"):
            lines.append(
                f"- P{row['priority_rank']} [{row['priority_bucket']}] {row['severity']} "
                f"{row['source_product']}: {row['exception_type']} | owner: {row['owner']} | "
                f"trip: {row['trip_id'] or 'n/a'} | carrier: {row['carrier_name'] or 'n/a'}"
            )
    lines.extend(["", "## Owner Workload", ""])
    if actions.empty:
        lines.append("- No owner workload.")
    else:
        workload = actions.groupby("owner", as_index=False).size().sort_values(["size", "owner"], ascending=[False, True])
        for row in workload.to_dict("records"):
            lines.append(f"- {row['owner']}: {row['size']} open action(s)")
    lines.extend(["", "## Source Coverage", ""])
    for row in source_status.to_dict("records"):
        lines.append(f"- {row['source_file']}: {row['status']}")
    if warnings:
        lines.extend(["", "## Config Warnings", ""])
        lines.extend([f"- {warning}" for warning in warnings])
    lines.extend(
        [
            "",
            "## Operating Notes",
            "",
            "- This brief is deterministic and file-based.",
            "- It does not send messages, create tasks, contact carriers, or use paid APIs.",
            "- Missing files reduce coverage but do not block brief generation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _brief_html(markdown: str, actions: pd.DataFrame, kpis: pd.DataFrame) -> str:
    action_rows = "\n".join(
        "<tr>"
        + "".join(f"<td>{escape(str(row[column]))}</td>" for column in ACTION_COLUMNS)
        + "</tr>"
        for row in actions.head(50).to_dict("records")
    )
    kpi_items = "\n".join(
        f"<li><strong>{escape(str(row['metric']))}</strong>: {escape(str(row['value']))}</li>"
        for row in kpis.to_dict("records")
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Daily Control Tower Brief</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
    th, td {{ border: 1px solid #d8dee9; padding: 6px; text-align: left; }}
    th {{ background: #edf2f7; }}
    pre {{ white-space: pre-wrap; background: #f8fafc; padding: 16px; }}
  </style>
</head>
<body>
  <h1>Daily Control Tower Brief</h1>
  <h2>KPI Snapshot</h2>
  <ul>{kpi_items}</ul>
  <h2>Open Actions</h2>
  <table>
    <thead><tr>{''.join(f'<th>{escape(column)}</th>' for column in ACTION_COLUMNS)}</tr></thead>
    <tbody>{action_rows}</tbody>
  </table>
  <h2>Markdown Brief</h2>
  <pre>{escape(markdown)}</pre>
</body>
</html>
"""


def run_tower_brief(
    inputs: dict[str, pd.DataFrame | None],
    settings: TowerBriefSettings | None = None,
) -> TowerBriefResult:
    """Build a deterministic daily brief from available product-output files."""
    settings = settings or TowerBriefSettings()
    normalized_inputs = {name: (_normalize_columns(df).dropna(how="all").copy() if df is not None else None) for name, df in inputs.items()}
    trips = normalized_inputs.get("trips.csv")
    trips = trips if trips is not None else pd.DataFrame()
    trip_context = _context_lookup(trips.copy())
    warnings: list[str] = []
    action_rows: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    for source_file, product_name in SOURCE_FILES.items():
        rows, status, warning = _normalize_source(source_file, normalized_inputs.get(source_file), trip_context, settings)
        action_rows.extend(rows)
        statuses.append({"source_file": source_file, "source_product": product_name, "status": status})
        if warning:
            warnings.append(warning)
    source_status = pd.DataFrame(statuses)
    action_table = _prioritize(pd.DataFrame(action_rows))
    kpi_snapshot = _kpis(action_table, source_status, trips)
    markdown = _brief_markdown(action_table, kpi_snapshot, source_status, warnings, settings)
    html = _brief_html(markdown, action_table, kpi_snapshot)
    return TowerBriefResult(action_table, kpi_snapshot, source_status, markdown, html, warnings)


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
    if result.config_warnings:
        print("Warnings:")
        for warning in result.config_warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
