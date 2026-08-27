import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.apps import AppConfig, write_app_config
from tests.utils import changing_dir

runner = CliRunner()

APP_ID = "00000000-0000-4000-8000-000000000001"
LINKED_APP_ID = "00000000-0000-4000-8000-000000000002"
TEAM_ID = "00000000-0000-4000-8000-000000000003"
TEAM_SLUG = "acme"
APP_SLUG = "api"
CONNECT_URL = (
    f"{Settings().dashboard_base_url}/{TEAM_SLUG}/apps/{APP_SLUG}/integrations/connect"
)


def _app(*, app_id: str = APP_ID) -> dict[str, object]:
    return {
        "id": app_id,
        "team_id": TEAM_ID,
        "slug": APP_SLUG,
        "name": "API",
        "directory": None,
    }


def _team() -> dict[str, str]:
    return {
        "id": TEAM_ID,
        "slug": TEAM_SLUG,
        "name": "Acme",
    }


def _mock_app_and_team(
    respx_mock: respx.MockRouter,
    *,
    app_id: str = APP_ID,
) -> None:
    respx_mock.get(f"/apps/{app_id}").mock(
        return_value=Response(200, json=_app(app_id=app_id))
    )
    respx_mock.get(f"/teams/{TEAM_ID}").mock(return_value=Response(200, json=_team()))


def test_connect_resource_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["integrations", "resources", "connect", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_logged_in",
            "message": "No credentials found.",
            "hint": "Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_connect_resource_json_returns_url_without_opening_browser(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=LINKED_APP_ID, team_id=TEAM_ID),
    )
    _mock_app_and_team(respx_mock)

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.commands.integrations.resources.connect.typer.launch"
        ) as mock_launch,
    ):
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "connect",
                "--app-id",
                APP_ID,
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "connect_url": CONNECT_URL,
        }
    }
    assert result.stderr == ""
    mock_launch.assert_not_called()


@pytest.mark.respx
def test_connect_resource_opens_browser_for_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=APP_ID, team_id=TEAM_ID),
    )
    _mock_app_and_team(respx_mock)

    with (
        changing_dir(tmp_path),
        patch(
            "fastapi_cloud_cli.commands.integrations.resources.connect.typer.launch",
            return_value=0,
        ) as mock_launch,
    ):
        result = runner.invoke(app, ["integrations", "resources", "connect"])

    assert result.exit_code == 0
    mock_launch.assert_called_once_with(CONNECT_URL)
    assert "connect resource" in result.output
    assert "Opened the integration setup for API in your browser." in result.output
    assert CONNECT_URL in result.output
    assert "When the connection is complete" in result.output
    assert "fastapi cloud integrations resources list" in " ".join(
        result.output.split()
    )
    assert APP_ID not in result.output


@pytest.mark.respx
def test_connect_resource_no_open_prints_url_without_opening_browser(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_app_and_team(respx_mock)

    with patch(
        "fastapi_cloud_cli.commands.integrations.resources.connect.typer.launch"
    ) as mock_launch:
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "connect",
                "--app-id",
                APP_ID,
                "--no-open",
            ],
        )

    assert result.exit_code == 0
    mock_launch.assert_not_called()
    assert "Open the integration setup for API in your browser:" in result.output
    assert CONNECT_URL in result.output
    assert f"fastapi cloud integrations resources list --app-id {APP_ID}" in " ".join(
        result.output.split()
    )


def test_connect_resource_json_requires_app_without_linked_app(
    logged_in_cli: None,
    tmp_path: Path,
) -> None:
    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "resources", "connect", "--json"],
        )

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
def test_connect_resource_json_returns_not_found_for_unknown_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}").mock(return_value=Response(404))

    result = runner.invoke(
        app,
        ["integrations", "resources", "connect", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "App not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""
