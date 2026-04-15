import subprocess
import sys

from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app

runner = CliRunner()


def test_shows_help() -> None:
    result = runner.invoke(app, ["cloud", "--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_shows_help_without_args() -> None:
    result = runner.invoke(app, ["cloud"])

    assert result.exit_code == 2
    assert "Usage:" in result.output


def test_script() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "coverage", "run", "-m", "fastapi_cloud_cli", "--help"],
        capture_output=True,
        encoding="utf-8",
    )
    assert "Usage" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["cloud", "--version"])
    assert result.exit_code == 0, result.output
    assert "FastAPI Cloud CLI version:" in result.output
