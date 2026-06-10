import json
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
    assert "App ID is required." in result.output


def test_list_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["env", "list", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "App ID is required.",
            "hint": "Pass --app-id or run `fastapi cloud apps create --link` first.",
        }
    }
    assert result.stderr == ""


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
def test_lists_environment_variables_as_json_with_app_id(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    variables = [
        {
            "name": "DATABASE_URL",
            "is_secret": True,
            "updated_at": "2026-05-22T10:00:00Z",
        },
        {
            "name": "LOG_LEVEL",
            "value": "info",
            "is_secret": False,
            "updated_at": "2026-05-22T10:00:00Z",
        },
    ]
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": variables})
    )

    result = runner.invoke(app, ["env", "list", "--app-id", app_id, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "variables": [
                {
                    "name": "DATABASE_URL",
                    "value": None,
                    "is_secret": True,
                    "updated_at": "2026-05-22T10:00:00Z",
                },
                {
                    "name": "LOG_LEVEL",
                    "value": "info",
                    "is_secret": False,
                    "updated_at": "2026-05-22T10:00:00Z",
                },
            ],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_environment_variables_as_json_with_path(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    result = runner.invoke(
        app, ["env", "list", "--path", str(configured_app.path), "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": configured_app.app_id,
            "variables": [],
        }
    }
    assert result.stderr == ""


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
                        "value": "https://fastapicloud.com",
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
    output = _normalize_output(result.output)

    assert "APP_URL" in output
    assert "https://fastapicloud.com" in output
    assert "12 days ago" in output
    assert "SENTRY_ENVIRONMENT" in output
    assert "production" in output
    assert "2 months ago" in output


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
    output = _normalize_output(result.output)
    assert "LONG_VALUE" in output
    assert "1234567890123456789012345678901234567..." in output
    assert "2 months ago" in output
    assert "SECRET_KEY" in output
    assert "[secret]" in output
    assert "1 month ago" in output
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
