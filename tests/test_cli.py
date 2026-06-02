import json
import subprocess
import sys
from datetime import datetime, timezone

import pytest
import typer
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import app
from fastapi_cloud_cli.utils.cli import (
    FastAPIRichToolkit,
    FastAPIStyle,
    get_rich_toolkit,
)
from fastapi_cloud_cli.utils.config import get_version_check_cache_path
from fastapi_cloud_cli.utils.version_check import write_latest_version_cache

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


def test_toolkit_success_prints_json_envelope() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command() -> None:
        with get_rich_toolkit(minimal=True) as toolkit:
            toolkit.success({"authenticated": True}, hint="next step")

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
        "hint": "next step",
    }


def test_toolkit_success_omits_empty_json_envelope_fields() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command() -> None:
        with get_rich_toolkit(minimal=True) as toolkit:
            toolkit.success({"authenticated": True})

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
    }


def test_toolkit_success_includes_non_empty_warnings() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command() -> None:
        with get_rich_toolkit(minimal=True) as toolkit:
            toolkit.success(
                {"authenticated": True},
                warnings=[{"code": "not_validated", "message": "Token not validated."}],
            )

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"authenticated": True},
        "warnings": [{"code": "not_validated", "message": "Token not validated."}],
    }


def test_toolkit_uses_rich_toolkit_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FASTAPI_CLOUD_JSON", "1")
    monkeypatch.setenv("FASTAPI_CLOUD_DISABLE_VERSION_CHECK", "1")

    toolkit = get_rich_toolkit(minimal=True)

    assert toolkit.mode == "json"


def test_toolkit_success_uses_strict_json_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FASTAPI_CLOUD_JSON", "1")
    monkeypatch.setenv("FASTAPI_CLOUD_DISABLE_VERSION_CHECK", "1")

    with get_rich_toolkit(minimal=True) as toolkit:
        with pytest.raises(ValueError, match="Out of range float values"):
            toolkit.success({"cpu": float("inf")})


def test_toolkit_fail_prints_json_error_and_exits() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command() -> None:
        with get_rich_toolkit(minimal=True) as toolkit:
            toolkit.fail(
                "api_error",
                "A value is required.",
                hint="Pass --value.",
            )

    result = runner.invoke(test_app, env={"FASTAPI_CLOUD_JSON": "1"})

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "api_error",
            "message": "A value is required.",
            "hint": "Pass --value.",
        }
    }


def test_toolkit_error_prints_human_message() -> None:
    test_app = typer.Typer()

    @test_app.command()
    def command() -> None:
        with get_rich_toolkit(minimal=True) as toolkit:
            toolkit.error(
                "api_error",
                "A value is required.",
                hint="Pass --value.",
            )

    result = runner.invoke(test_app)

    assert result.exit_code == 0
    assert "A value is required." in result.output
    assert "Pass --value." in result.output


def test_embedded_fastapi_cli_prints_forced_update_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_app = typer.Typer()
    parent_app.add_typer(app)
    monkeypatch.setattr(sys, "argv", ["fastapi", "cloud", "whoami"])
    write_latest_version_cache(
        get_version_check_cache_path(),
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
    assert "→ 999.0.0" in result.output
