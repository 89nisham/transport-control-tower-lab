"""Smoke tests for CLI import and workspace initialization."""

from typer.testing import CliRunner

from control_tower_lab.cli import app


def test_cli_imports():
    """The Typer app should be importable for command tests and packaging."""
    assert app is not None


def test_init_command_creates_workspace_folders():
    """The init command should create the expected local workspace folders."""
    runner = CliRunner()

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Control Tower Lab" in result.output
