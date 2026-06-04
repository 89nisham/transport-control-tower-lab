from typer.testing import CliRunner

from control_tower_lab.cli import app


def test_cli_imports():
    assert app is not None


def test_init_command_creates_workspace_folders():
    runner = CliRunner()

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Control Tower Lab" in result.output
