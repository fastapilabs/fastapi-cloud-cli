from datetime import datetime, timezone
from pathlib import Path

import pytest
import respx
import time_machine
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


def _normalize_output(output: str) -> str:
    return "\n".join(line.rstrip() for line in output.strip("\n").splitlines())


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert "No app found" in result.output


@pytest.mark.respx
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(500)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx
def test_shows_a_message_if_no_env_variables(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert "No environment variables found." in result.output


@pytest.mark.respx
def test_shows_environment_variables_names(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"name": "SECRET_KEY", "value": "123"},
                    {"name": "API_KEY", "value": "456"},
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert "SECRET_KEY" in result.output
    assert "API_KEY" in result.output


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_shows_environment_variables_in_compact_table(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "APP_URL",
                        "value": "https://tryshot.app",
                        "updated_at": "2026-05-10T12:00:00Z",
                    },
                    {
                        "name": "SENTRY_ENVIRONMENT",
                        "value": "production",
                        "updated_at": "2026-03-22T12:00:00Z",
                    },
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert _normalize_output(result.output) == (
        "Key                  Value                 Last updated\n"
        "───────────────────────────────────────────────────────\n"
        "APP_URL              https://tryshot.app   12 days ago\n"
        "SENTRY_ENVIRONMENT   production            2 months ago"
    )


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_truncates_values_and_marks_secrets_in_compact_table(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    long_value = "12345678901234567890123456789012345678901234567890"

    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "LONG_VALUE",
                        "value": long_value,
                        "updated_at": "2026-03-22T12:00:00Z",
                    },
                    {
                        "name": "SECRET_KEY",
                        "is_secret": True,
                        "updated_at": "2026-04-22T12:00:00Z",
                    },
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert _normalize_output(result.output) == (
        "Key          Value                                      Last updated\n"
        "────────────────────────────────────────────────────────────────────\n"
        "LONG_VALUE   1234567890123456789012345678901234567...   2 months ago\n"
        "SECRET_KEY   [secret]                                   1 month ago"
    )
    assert long_value not in result.output


@pytest.mark.respx
def test_shows_secret_environment_variables_without_value(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    """Test that secret env vars without a value field are handled correctly."""
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "SECRET_KEY",
                        "is_secret": True,
                        "created_at": "2026-01-13T19:01:07.408378Z",
                        "updated_at": "2026-01-13T19:01:07.408389Z",
                        "connected_resource": None,
                    },
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert "SECRET_KEY" in result.output
