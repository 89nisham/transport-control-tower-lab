from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


CANONICAL_COLUMNS = {
    "trip_id": {
        "trip_id",
        "trip_no",
        "trip_number",
        "trip_ref",
        "trip_reference",
        "shipment_id",
        "shipment_no",
        "order_no",
        "waybill",
        "awb",
    },
    "vehicle_id": {
        "vehicle",
        "vehicle_id",
        "truck",
        "truck_id",
        "door_no",
        "door_number",
        "asset",
        "asset_id",
        "plate",
        "plate_no",
        "plate_number",
    },
    "driver_name": {
        "driver",
        "driver_name",
        "driver_id",
        "captain",
        "operator",
    },
    "origin": {
        "origin",
        "from",
        "source",
        "pickup",
        "pickup_location",
        "loading_point",
        "branch",
        "origin_branch",
    },
    "destination": {
        "destination",
        "to",
        "drop",
        "dropoff",
        "delivery",
        "delivery_location",
        "unloading_point",
        "dest_branch",
    },
    "planned_start": {
        "planned_start",
        "plan_start",
        "planned_pickup",
        "pickup_time",
        "pickup_datetime",
        "dispatch_time",
        "trip_start",
        "start_time",
    },
    "planned_end": {
        "planned_end",
        "plan_end",
        "planned_delivery",
        "delivery_time",
        "delivery_datetime",
        "eta",
        "trip_end",
        "end_time",
    },
    "status": {
        "status",
        "trip_status",
        "shipment_status",
        "state",
    },
}

REQUIRED_COLUMNS = ("trip_id", "vehicle_id", "origin", "destination", "planned_start", "planned_end")
DATE_COLUMNS = ("planned_start", "planned_end")


@dataclass(frozen=True)
class TripSheetDoctorResult:
    cleaned_trips: pd.DataFrame
    exceptions: pd.DataFrame
    correction_suggestions: pd.DataFrame
    summary: pd.DataFrame
    column_map: dict[str, str]


def _simple_column_name(value: Any) -> str:
    name = str(value).strip().lower()
    for char in ("-", "/", "\\", ".", "(", ")", "[", "]"):
        name = name.replace(char, " ")
    return "_".join(name.split())


def _normalize_text(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return " ".join(text.split())


def _normalize_vehicle(value: Any) -> str | None:
    text = _normalize_text(value)
    if text is None:
        return None
    return text.upper().replace(" ", "").replace("-", "")


def _build_column_map(columns: list[str]) -> dict[str, str]:
    normalized_to_original = {_simple_column_name(column): column for column in columns}
    mapped: dict[str, str] = {}
    used_original: set[str] = set()

    for canonical, aliases in CANONICAL_COLUMNS.items():
        for alias in aliases:
            original = normalized_to_original.get(alias)
            if original and original not in used_original:
                mapped[canonical] = original
                used_original.add(original)
                break
    return mapped


def _base_cleaned_frame(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    cleaned = pd.DataFrame(index=df.index)
    for canonical in CANONICAL_COLUMNS:
        source = column_map.get(canonical)
        cleaned[canonical] = df[source] if source else pd.NA

    cleaned["vehicle_id"] = cleaned["vehicle_id"].map(_normalize_vehicle)
    for column in ("trip_id", "driver_name", "origin", "destination", "status"):
        cleaned[column] = cleaned[column].map(_normalize_text)
    for column in DATE_COLUMNS:
        cleaned[column] = pd.to_datetime(cleaned[column], errors="coerce")

    cleaned.insert(0, "source_row", df.index + 2)
    cleaned["duration_hours"] = (
        (cleaned["planned_end"] - cleaned["planned_start"]).dt.total_seconds() / 3600
    ).round(2)
    return cleaned


def _exception(
    row: pd.Series,
    exception_type: str,
    severity: str,
    evidence: str,
    suggested_action: str,
    confidence: str = "high",
) -> dict[str, Any]:
    return {
        "source_row": row.get("source_row"),
        "trip_id": row.get("trip_id"),
        "vehicle_id": row.get("vehicle_id"),
        "origin": row.get("origin"),
        "destination": row.get("destination"),
        "exception_type": exception_type,
        "severity": severity,
        "confidence": confidence,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "owner": _owner_for_exception(exception_type),
        "review_status": "open",
    }


def _owner_for_exception(exception_type: str) -> str:
    if exception_type in {"missing_vehicle_id", "duplicate_trip_id"}:
        return "fleet/control_tower"
    if exception_type in {"missing_planned_start", "missing_planned_end", "invalid_trip_time_sequence"}:
        return "operations"
    if exception_type in {"missing_origin", "missing_destination", "same_origin_destination"}:
        return "master_data"
    return "control_tower"


def _detect_exceptions(cleaned: pd.DataFrame) -> pd.DataFrame:
    exceptions: list[dict[str, Any]] = []

    for _, row in cleaned.iterrows():
        for column in REQUIRED_COLUMNS:
            value = row.get(column)
            if pd.isna(value) or value in {None, ""}:
                exceptions.append(
                    _exception(
                        row,
                        f"missing_{column}",
                        "high" if column in {"trip_id", "vehicle_id"} else "medium",
                        f"{column} is blank or could not be mapped from the source sheet.",
                        f"Review source row {row['source_row']} and complete {column}.",
                    )
                )

        if pd.notna(row.get("planned_start")) and pd.notna(row.get("planned_end")):
            if row["planned_end"] < row["planned_start"]:
                exceptions.append(
                    _exception(
                        row,
                        "invalid_trip_time_sequence",
                        "critical",
                        "planned_end is earlier than planned_start.",
                        "Correct pickup/delivery timestamps before ETA or SLA analysis.",
                    )
                )
            elif row.get("duration_hours") and row["duration_hours"] > 72:
                exceptions.append(
                    _exception(
                        row,
                        "very_long_planned_duration",
                        "medium",
                        f"Planned duration is {row['duration_hours']} hours.",
                        "Verify whether this is a real long-haul trip or a date-entry issue.",
                        confidence="medium",
                    )
                )

        if row.get("origin") and row.get("destination"):
            if str(row["origin"]).strip().lower() == str(row["destination"]).strip().lower():
                exceptions.append(
                    _exception(
                        row,
                        "same_origin_destination",
                        "medium",
                        "Origin and destination are the same after normalization.",
                        "Check lane entry or branch/customer mapping.",
                        confidence="medium",
                    )
                )

    duplicate_mask = cleaned["trip_id"].notna() & cleaned["trip_id"].duplicated(keep=False)
    for _, row in cleaned[duplicate_mask].iterrows():
        exceptions.append(
            _exception(
                row,
                "duplicate_trip_id",
                "high",
                f"Trip ID {row['trip_id']} appears more than once in the sheet.",
                "Confirm whether this is a duplicate row, split shipment, or reused reference.",
            )
        )

    columns = [
        "source_row",
        "trip_id",
        "vehicle_id",
        "origin",
        "destination",
        "exception_type",
        "severity",
        "confidence",
        "evidence",
        "suggested_action",
        "owner",
        "review_status",
    ]
    return pd.DataFrame(exceptions, columns=columns)


def _build_correction_suggestions(
    df: pd.DataFrame,
    cleaned: pd.DataFrame,
    column_map: dict[str, str],
) -> pd.DataFrame:
    suggestions: list[dict[str, Any]] = []

    for canonical in CANONICAL_COLUMNS:
        if canonical not in column_map:
            suggestions.append(
                {
                    "suggestion_type": "missing_column_mapping",
                    "field": canonical,
                    "source_row": None,
                    "current_value": None,
                    "suggested_value": None,
                    "evidence": f"No source column mapped to required field {canonical}.",
                    "review_status": "open",
                }
            )

    for _, row in cleaned.iterrows():
        raw_vehicle = row.get("vehicle_id")
        if isinstance(raw_vehicle, str) and raw_vehicle != _normalize_vehicle(raw_vehicle):
            suggestions.append(
                {
                    "suggestion_type": "vehicle_identity_normalization",
                    "field": "vehicle_id",
                    "source_row": row["source_row"],
                    "current_value": raw_vehicle,
                    "suggested_value": _normalize_vehicle(raw_vehicle),
                    "evidence": "Vehicle reference contains spacing or separators.",
                    "review_status": "open",
                }
            )

    unmapped_columns = [column for column in df.columns if column not in column_map.values()]
    for column in unmapped_columns:
        suggestions.append(
            {
                "suggestion_type": "unmapped_source_column",
                "field": column,
                "source_row": None,
                "current_value": column,
                "suggested_value": None,
                "evidence": "Source column preserved in raw input but not used by Trip Sheet Doctor v1.",
                "review_status": "open",
            }
        )

    return pd.DataFrame(
        suggestions,
        columns=[
            "suggestion_type",
            "field",
            "source_row",
            "current_value",
            "suggested_value",
            "evidence",
            "review_status",
        ],
    )


def _build_summary(cleaned: pd.DataFrame, exceptions: pd.DataFrame) -> pd.DataFrame:
    total_rows = len(cleaned)
    trips_with_exceptions = exceptions["source_row"].nunique() if not exceptions.empty else 0
    metrics = [
        ("total_rows_reviewed", total_rows),
        ("unique_trip_ids", int(cleaned["trip_id"].nunique(dropna=True))),
        ("trips_with_exceptions", int(trips_with_exceptions)),
        ("exception_count", len(exceptions)),
        (
            "exception_rate",
            round(trips_with_exceptions / total_rows, 4) if total_rows else 0,
        ),
    ]

    rows = [{"metric": metric, "value": value} for metric, value in metrics]
    if not exceptions.empty:
        by_type = exceptions.groupby(["exception_type", "severity"]).size().reset_index(name="count")
        rows.extend(
            {
                "metric": f"{item.exception_type}_{item.severity}",
                "value": int(item.count),
            }
            for item in by_type.itertuples(index=False)
        )
    return pd.DataFrame(rows)


def analyze_trip_sheet(df: pd.DataFrame) -> TripSheetDoctorResult:
    source = df.dropna(how="all").copy()
    column_map = _build_column_map(list(source.columns))
    cleaned = _base_cleaned_frame(source, column_map)
    exceptions = _detect_exceptions(cleaned)
    suggestions = _build_correction_suggestions(source, cleaned, column_map)
    summary = _build_summary(cleaned, exceptions)
    return TripSheetDoctorResult(
        cleaned_trips=cleaned,
        exceptions=exceptions,
        correction_suggestions=suggestions,
        summary=summary,
        column_map=column_map,
    )


def write_trip_sheet_doctor_workbook(result: TripSheetDoctorResult, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    column_map_df = pd.DataFrame(
        [{"canonical_field": key, "source_column": value} for key, value in result.column_map.items()]
    )
    with pd.ExcelWriter(output_file) as writer:
        result.summary.to_excel(writer, sheet_name="summary", index=False)
        result.exceptions.to_excel(writer, sheet_name="exceptions", index=False)
        result.correction_suggestions.to_excel(
            writer,
            sheet_name="correction_suggestions",
            index=False,
        )
        result.cleaned_trips.to_excel(writer, sheet_name="cleaned_trips", index=False)
        column_map_df.to_excel(writer, sheet_name="column_map", index=False)
