import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.utils.cli import (
    FastAPIRichToolkit,
    FastAPIStyle,
    get_rich_toolkit,
)
from fastapi_cloud_cli.utils.version_check import (
    VERSION_CHECK_CACHE_FILENAME,
    write_latest_version_cache,
)

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


def test_tag_style_metadata_uses_dedicated_color() -> None:
    toolkit = get_rich_toolkit()
    assert isinstance(toolkit, FastAPIRichToolkit)
    assert isinstance(toolkit.style, FastAPIStyle)

    segments, _ = toolkit.style._get_tag_segments(
        {"tag": "notice", "tag_style": "tag.update"}
    )

    assert segments[0].style == toolkit.style.console.get_style("tag.update")
    assert segments[0].style != toolkit.style.console.get_style("tag")


def test_embedded_fastapi_cli_prints_forced_update_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_app = typer.Typer()
    parent_app.add_typer(app)
    monkeypatch.setattr(sys, "argv", ["fastapi", "cloud", "whoami"])
    write_latest_version_cache(
        Path(os.environ["FASTAPI_CLOUD_CLI_CONFIG_DIR"]) / VERSION_CHECK_CACHE_FILENAME,
        latest_version="999.0.0",
        now=datetime.now(timezone.utc),
    )

    result = runner.invoke(
        parent_app,
        ["cloud", "whoami"],
        env={"FASTAPI_CLOUD_DISABLE_VERSION_CHECK": ""},
    )

    assert result.exit_code == 0, result.output
    assert "No credentials found" in result.output
    assert "A newer FastAPI Cloud CLI version is available" in result.output
    assert "0.17.1 → 999.0.0" in result.output
