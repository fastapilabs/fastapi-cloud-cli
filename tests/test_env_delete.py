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


def _has_environment_variables_title(output: str) -> bool:
    return any(line.strip() == "environment variables" for line in output.splitlines())


@pytest.fixture
def configured_app(tmp_path: Path) -> Path:
    app_id = "123"
    team_id = "456"

    config_path = tmp_path / ".fastapicloud" / "cloud.json"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(f'{{"app_id": "{app_id}", "team_id": "{team_id}"}}')

    return tmp_path


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "delete"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "delete"])

    assert result.exit_code == 1
    assert "App ID is required." in result.output


def test_delete_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["env", "delete", "DATABASE_URL", "--yes", "--json"])

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
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.delete("/apps/123/environment-variables/SOME_VAR").mock(
        return_value=Response(500)
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "delete", "SOME_VAR", "--yes"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx
def test_shows_message_if_not_found(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.delete("/apps/123/environment-variables/SOME_VAR").mock(
        return_value=Response(404)
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "delete", "SOME_VAR", "--yes"])

    assert result.exit_code == 1
    assert "Environment variable not found" in result.output


def test_shows_a_message_if_name_is_invalid(
    logged_in_cli: None, configured_app: Path
) -> None:
    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "delete", "aaa-aaa"])

    assert result.exit_code == 1
    assert "The environment variable name aaa-aaa is invalid." in result.output


@pytest.mark.respx
def test_shows_message_when_it_deletes(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.delete("/apps/123/environment-variables/SOME_VAR").mock(
        return_value=Response(204)
    )

    with (
        changing_dir(configured_app),
        patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]),
    ):
        result = runner.invoke(app, ["env", "delete", "SOME_VAR"])

    assert result.exit_code == 0
    assert "Delete SOME_VAR?" in result.output
    assert _has_environment_variables_title(result.output)
    assert "Environment variable SOME_VAR deleted" in result.output


@pytest.mark.respx
def test_deletes_environment_variable_as_json_with_app_id(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.delete(f"/apps/{app_id}/environment-variables/DATABASE_URL").mock(
        return_value=Response(204)
    )

    result = runner.invoke(
        app,
        [
            "env",
            "delete",
            "DATABASE_URL",
            "--app-id",
            app_id,
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "name": "DATABASE_URL",
            "deleted": True,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_delete_environment_variable_json_returns_not_found(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.delete(f"/apps/{app_id}/environment-variables/DATABASE_URL").mock(
        return_value=Response(404)
    )

    result = runner.invoke(
        app,
        [
            "env",
            "delete",
            "DATABASE_URL",
            "--app-id",
            app_id,
            "--yes",
            "--json",
        ],
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


@pytest.mark.respx
def test_shows_selector_for_environment_variables(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    steps = [Keys.ENTER]
    respx_mock.get("/apps/123/environment-variables/").mock(
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

    respx_mock.delete("/apps/123/environment-variables/SECRET_KEY").mock(
        return_value=Response(204)
    )

    with (
        changing_dir(configured_app),
        patch("rich_toolkit.container.getchar", side_effect=steps),
    ):
        result = runner.invoke(app, ["env", "delete"])

    assert result.exit_code == 0
    assert _has_environment_variables_title(result.output)
    selector_line = next(
        line
        for line in result.output.splitlines()
        if line.strip() == "Select the environment variable to delete:"
    )
    assert selector_line.startswith("  Select the environment variable to delete:")
    assert "Select the environment variable to delete" in result.output

    assert "Environment variable SECRET_KEY deleted" in result.output


@pytest.mark.respx
def test_shows_message_if_no_environment_variable(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: Path
) -> None:
    respx_mock.get("/apps/123/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    with changing_dir(configured_app):
        result = runner.invoke(app, ["env", "delete"])

    assert result.exit_code == 0
    assert _has_environment_variables_title(result.output)
    assert "No environment variables found." in result.output


def test_delete_json_returns_missing_required_input_without_name(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["env", "delete", "--app-id", "00000000-0000-4000-8000-000000000002", "--json"],
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


def test_delete_json_returns_missing_required_input_without_confirmation(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "env",
            "delete",
            "DATABASE_URL",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Deletion confirmation is required.",
            "hint": "Pass --yes to confirm deletion.",
        }
    }
    assert result.stderr == ""


def test_shows_message_when_deletion_is_cancelled(
    logged_in_cli: None, configured_app: Path
) -> None:
    with (
        changing_dir(configured_app),
        patch(
            "rich_toolkit.container.getchar",
            side_effect=[Keys.RIGHT_ARROW, Keys.ENTER],
        ),
    ):
        result = runner.invoke(app, ["env", "delete", "SOME_VAR"])

    assert result.exit_code == 0
    assert "Delete SOME_VAR?" in result.output
    assert "Deletion cancelled." in result.output
