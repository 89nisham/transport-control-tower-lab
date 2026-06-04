from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from control_tower_lab.cli import app
from control_tower_lab.trip_sheet_doctor import analyze_trip_sheet


def test_trip_sheet_doctor_detects_operational_exceptions():
    df = pd.DataFrame(
        [
            {
                "Trip No": "T001",
                "Door Number": " trk-101 ",
                "From": "Riyadh Hub",
                "To": "Jeddah Hub",
                "Pickup Time": "2026-06-01 08:00",
                "ETA": "2026-06-01 18:00",
            },
            {
                "Trip No": "T002",
                "Door Number": "",
                "From": "Riyadh Hub",
                "To": "Riyadh Hub",
                "Pickup Time": "2026-06-01 10:00",
                "ETA": "2026-06-01 09:00",
            },
            {
                "Trip No": "T001",
                "Door Number": "TRK102",
                "From": "",
                "To": "Dammam Hub",
                "Pickup Time": "bad date",
                "ETA": "2026-06-02 11:00",
            },
        ]
    )

    result = analyze_trip_sheet(df)

    assert len(result.cleaned_trips) == 3
    assert result.cleaned_trips.loc[0, "vehicle_id"] == "TRK101"
    assert set(result.exceptions["exception_type"]) >= {
        "missing_vehicle_id",
        "invalid_trip_time_sequence",
        "same_origin_destination",
        "duplicate_trip_id",
        "missing_origin",
        "missing_planned_start",
    }


def test_trip_sheet_doctor_cli_writes_workbook(tmp_path: Path):
    input_file = tmp_path / "trips.csv"
    output_file = tmp_path / "doctor.xlsx"
    pd.DataFrame(
        [
            {
                "Shipment ID": "S001",
                "Vehicle": "D-44",
                "Origin": "RUH",
                "Destination": "JED",
                "Dispatch Time": "2026-06-01 08:00",
                "Delivery Time": "2026-06-01 20:00",
            }
        ]
    ).to_csv(input_file, index=False)

    runner = CliRunner()
    result = runner.invoke(app, ["trip-sheet-doctor", str(input_file), str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()
    workbook = pd.ExcelFile(output_file)
    assert set(workbook.sheet_names) == {
        "summary",
        "exceptions",
        "correction_suggestions",
        "cleaned_trips",
        "column_map",
    }
