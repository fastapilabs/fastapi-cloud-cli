import json
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "get", "LOG_LEVEL"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


@pytest.mark.respx
def test_shows_message_if_no_environment_variables(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "get"])

    assert result.exit_code == 0
    assert "No environment variables found." in result.output


@pytest.mark.respx
def test_gets_environment_variable_in_human_output_with_environment_variables_tag(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "LOG_LEVEL",
                        "value": "info",
                        "is_secret": False,
                    }
                ]
            },
        )
    )

    result = runner.invoke(app, ["env", "get", "LOG_LEVEL", "--app-id", app_id])

    assert result.exit_code == 0
    assert "environment variables" in result.output
    assert "LOG_LEVEL" in result.output
    assert "info" in result.output


@pytest.mark.respx
def test_gets_secret_environment_variable_in_human_output(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "DATABASE_URL",
                        "is_secret": True,
                    }
                ]
            },
        )
    )

    result = runner.invoke(app, ["env", "get", "DATABASE_URL", "--app-id", app_id])

    assert result.exit_code == 0
    assert "environment variables" in result.output
    assert "DATABASE_URL" in result.output
    assert "[secret]" in result.output


@pytest.mark.respx
def test_get_prompts_for_environment_variable_name(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "DEMO",
                        "value": "VALUE",
                        "is_secret": False,
                    },
                    {
                        "name": "OTHER",
                        "value": "ignored",
                        "is_secret": False,
                    },
                ]
            },
        )
    )

    with patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]):
        result = runner.invoke(app, ["env", "get", "--app-id", app_id])

    assert result.exit_code == 0
    assert "environment variables" in result.output
    assert "Select the environment variable to get:" in result.output
    assert "DEMO" in result.output
    assert "VALUE" in result.output


def test_get_json_returns_missing_required_input_without_name(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "env",
            "get",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Environment variable name is required.",
            "hint": "Pass NAME to choose an environment variable.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_secret_environment_variable_as_json(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    variable = {
        "name": "DATABASE_URL",
        "is_secret": True,
        "updated_at": "2026-05-22T10:00:00Z",
    }
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": [variable]})
    )

    result = runner.invoke(
        app, ["env", "get", "DATABASE_URL", "--app-id", app_id, "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "variable": {
                "name": "DATABASE_URL",
                "value": None,
                "is_secret": True,
                "updated_at": "2026-05-22T10:00:00Z",
            },
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_non_secret_environment_variable_as_json(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    variable = {
        "name": "LOG_LEVEL",
        "value": "info",
        "is_secret": False,
        "updated_at": "2026-05-22T10:00:00Z",
    }
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": [variable]})
    )

    result = runner.invoke(
        app, ["env", "get", "LOG_LEVEL", "--app-id", app_id, "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "variable": variable,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_get_environment_variable_json_returns_not_found(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "LOG_LEVEL",
                        "value": "info",
                        "is_secret": False,
                    }
                ]
            },
        )
    )

    result = runner.invoke(
        app, ["env", "get", "DATABASE_URL", "--app-id", app_id, "--json"]
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "Environment variable DATABASE_URL not found.",
            "hint": "Run `fastapi cloud env list` to see available variables.",
        }
    }
    assert result.stderr == ""
