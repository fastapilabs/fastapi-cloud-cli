import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from tests.utils import Keys, changing_dir

runner = CliRunner()

assets_path = Path(__file__).parent / "assets"


@pytest.fixture
def configured_app(tmp_path: Path) -> Path:
    app_id = "123"
    team_id = "456"

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    return tmp_path


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 1
    assert "App ID is required." in result.output


@pytest.mark.respx
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.post(
        "/apps/123/environment-variables/",
        json={"name": "SOME_VAR", "value": "secret", "is_secret": False},
    ).mock(return_value=Response(500))

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx
def test_shows_message_when_it_sets(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.post(
        "/apps/123/environment-variables/",
        json={"name": "SOME_VAR", "value": "secret", "is_secret": False},
    ).mock(return_value=Response(200))

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret"])

    assert result.exit_code == 0
    assert "Environment variable SOME_VAR set" in result.output


@pytest.mark.respx
def test_asks_for_name_and_value(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    steps = [*"SOME_VAR", Keys.ENTER, *"secret", Keys.ENTER]

    respx_mock.post(
        "/apps/123/environment-variables/",
        json={"name": "SOME_VAR", "value": "secret", "is_secret": False},
    ).mock(return_value=Response(200))

    with (
        changing_dir(configured_app),
        patch("rich_toolkit.container.getchar", side_effect=steps),
    ):
        result = runner.invoke(app, ["env", "set"])

    assert result.exit_code == 0

    assert "Enter the name of the environment variable" in result.output
    assert "Enter the value of the environment variable" in result.output
    assert "Environment variable SOME_VAR set" in result.output


@pytest.mark.respx
def test_asks_for_name_and_value_for_secret(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    steps = [*"SOME_VAR", Keys.ENTER, *"secret", Keys.ENTER]

    respx_mock.post(
        "/apps/123/environment-variables/",
        json={"name": "SOME_VAR", "value": "secret", "is_secret": True},
    ).mock(return_value=Response(200))

    with (
        changing_dir(configured_app),
        patch("rich_toolkit.container.getchar", side_effect=steps),
    ):
        result = runner.invoke(app, ["env", "set", "--secret"])

    assert result.exit_code == 0

    assert "Enter the name of the secret" in result.output
    assert "Enter the secret value" in result.output
    assert "Secret environment variable SOME_VAR set" in result.output

    assert "*" * 6 in result.output


@pytest.mark.respx
def test_sets_secret_flag(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.post(
        "/apps/123/environment-variables/",
        json={"name": "SOME_VAR", "value": "secret", "is_secret": True},
    ).mock(return_value=Response(200))

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "set", "SOME_VAR", "secret", "--secret"])

    assert result.exit_code == 0
    assert "Secret environment variable SOME_VAR set" in result.output


@pytest.mark.respx
def test_sets_environment_variable_as_json(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.post(
        f"/apps/{app_id}/environment-variables/",
        json={"name": "LOG_LEVEL", "value": "info", "is_secret": False},
    ).mock(return_value=Response(201))

    result = runner.invoke(
        app,
        ["env", "set", "LOG_LEVEL", "info", "--app-id", app_id, "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "LOG_LEVEL",
            "is_secret": False,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_sets_secret_environment_variable_as_json(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.post(
        f"/apps/{app_id}/environment-variables/",
        json={"name": "DATABASE_URL", "value": "postgres://db", "is_secret": True},
    ).mock(return_value=Response(201))

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "DATABASE_URL",
            "postgres://db",
            "--secret",
            "--app-id",
            app_id,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "DATABASE_URL",
            "is_secret": True,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_sets_environment_variable_as_json_reads_value_stdin(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.post(
        f"/apps/{app_id}/environment-variables/",
        json={"name": "DATABASE_URL", "value": "postgres://db", "is_secret": True},
    ).mock(return_value=Response(201))

    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "DATABASE_URL",
            "--value-stdin",
            "--secret",
            "--app-id",
            app_id,
            "--json",
        ],
        input="postgres://db\n",
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "DATABASE_URL",
            "is_secret": True,
        }
    }
    assert result.stderr == ""


def test_set_json_returns_missing_required_input_without_name(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["env", "set", "--app-id", "00000000-0000-4000-8000-000000000002", "--json"],
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


def test_set_rejects_value_and_value_stdin(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "LOG_LEVEL",
            "info",
            "--value-stdin",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
        input="debug\n",
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Only one environment variable value source can be used.",
            "hint": "Pass either VALUE or --value-stdin.",
        }
    }
    assert result.stderr == ""


def test_set_json_returns_missing_required_input_without_value(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "env",
            "set",
            "LOG_LEVEL",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Environment variable value is required.",
            "hint": "Pass VALUE or --value-stdin to set the environment variable.",
        }
    }
    assert result.stderr == ""
