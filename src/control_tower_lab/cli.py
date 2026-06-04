"""Command-line entry points for the Transport Control Tower Lab toolkit."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from control_tower_lab.trip_sheet_doctor import analyze_trip_sheet, write_trip_sheet_doctor_workbook

app = typer.Typer(help="Open-source logistics control tower toolkit.")
console = Console()
ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "data" / "input"
OUTPUT_DIR = ROOT / "data" / "output"
LOG_DIR = ROOT / "logs"


def _read_table(path: Path) -> pd.DataFrame:
    """Read a supported CSV or Excel file into a dataframe."""
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise typer.BadParameter(f"Unsupported file type: {path.suffix}")


def _write_table(df: pd.DataFrame, path: Path) -> None:
    """Write a dataframe to CSV or Excel based on the output suffix."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize source column names for simple file-based workflows."""
    df = df.copy()
    df.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    return df


@app.command()
def init() -> None:
    """Create the standard input, output, and log folders."""
    for folder in (INPUT_DIR, OUTPUT_DIR, LOG_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    table = Table(title="Control Tower Lab")
    table.add_column("Path")
    table.add_column("Status")
    for folder in (INPUT_DIR, OUTPUT_DIR, LOG_DIR):
        table.add_row(str(folder.relative_to(ROOT)), "ready")
    console.print(table)


@app.command("clean-tms")
def clean_tms(input_file: Path, output_file: Path = OUTPUT_DIR / "tms_cleaned.xlsx") -> None:
    """Normalize a TMS report and write a cleaned workbook."""
    df = _normalize_columns(_read_table(input_file))
    df = df.dropna(how="all")
    _write_table(df, output_file)
    logger.info("Cleaned TMS rows={} output={}", len(df), output_file)
    console.print(f"Wrote {output_file}")


@app.command("clean-gps")
def clean_gps(input_file: Path, output_file: Path = OUTPUT_DIR / "gps_cleaned.xlsx") -> None:
    """Normalize a GPS report and write a cleaned workbook."""
    df = _normalize_columns(_read_table(input_file))
    df = df.dropna(how="all")
    _write_table(df, output_file)
    logger.info("Cleaned GPS rows={} output={}", len(df), output_file)
    console.print(f"Wrote {output_file}")


@app.command("trip-sheet-doctor")
def trip_sheet_doctor(
    input_file: Path,
    output_file: Path = typer.Argument(OUTPUT_DIR / "trip_sheet_doctor.xlsx"),
) -> None:
    """Diagnose trip sheet quality and create an explainable exception workbook."""
    df = _read_table(input_file)
    result = analyze_trip_sheet(df)
    write_trip_sheet_doctor_workbook(result, output_file)
    exception_count = len(result.exceptions)
    affected_rows = result.exceptions["source_row"].nunique() if exception_count else 0
    logger.info(
        "Trip Sheet Doctor rows={} exceptions={} output={}",
        len(result.cleaned_trips),
        exception_count,
        output_file,
    )
    console.print(f"Wrote {output_file}")
    console.print(f"Rows reviewed: {len(result.cleaned_trips)}")
    console.print(f"Exceptions: {exception_count} across {affected_rows} rows")


@app.command("exceptions")
def exceptions(input_file: Path, output_file: Path = OUTPUT_DIR / "exceptions.xlsx") -> None:
    """Create a basic exception report from normalized input."""
    df = _normalize_columns(_read_table(input_file))
    checks = []
    for column in ("shipment_id", "vehicle", "eta", "status"):
        if column in df.columns:
            missing = df[df[column].isna()].copy()
            if not missing.empty:
                missing["exception_type"] = f"missing_{column}"
                checks.append(missing)
    result = (
        pd.concat(checks, ignore_index=True)
        if checks
        else pd.DataFrame(columns=list(df.columns) + ["exception_type"])
    )
    _write_table(result, output_file)
    console.print(f"Wrote {len(result)} exceptions to {output_file}")


@app.command("weekly-output")
def weekly_output(output_file: Path = OUTPUT_DIR / "weekly_control_tower_summary.xlsx") -> None:
    """Create a starter weekly Excel workbook from available cleaned outputs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    summary = pd.DataFrame(
        [
            {"metric": "generated_at_utc", "value": generated_at},
            {"metric": "note", "value": "Add cleaned TMS/GPS and exception metrics here."},
        ]
    )
    with pd.ExcelWriter(output_file) as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
    console.print(f"Wrote {output_file}")


@app.command("telegram-summary")
def telegram_summary(input_file: Path | None = None) -> None:
    """Draft a Telegram-friendly summary message without sending it."""
    lines = ["Control Tower Summary", "- Status: draft", "- Next: connect real TMS/GPS inputs"]
    if input_file:
        df = _normalize_columns(_read_table(input_file))
        lines.append(f"- Rows reviewed: {len(df)}")
    message = "\n".join(lines)
    out = OUTPUT_DIR / "telegram_summary.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(message + "\n", encoding="utf-8")
    console.print(message)
    console.print(f"Draft saved to {out}")


if __name__ == "__main__":
    app()
