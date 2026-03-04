from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.utils.apps import AppConfig
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["link"])

    assert result.exit_code == 1
    assert "You need to be logged in to link an app." in result.output


def test_shows_a_message_if_already_linked(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 1
    assert "This directory is already linked to an app." in result.output


@pytest.mark.respx
def test_shows_a_message_if_no_teams(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    respx_mock.get("/teams/").mock(return_value=Response(200, json={"data": []}))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 1
    assert "No teams found" in result.output


@pytest.mark.respx
def test_shows_a_message_if_no_apps(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    steps = [Keys.ENTER]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200, json={"data": [{"id": "team-1", "name": "My Team", "slug": "my-team"}]}
        )
    )
    respx_mock.get("/apps/", params={"team_id": "team-1"}).mock(
        return_value=Response(200, json={"data": []})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 1
    assert "No apps found in this team." in result.output


@pytest.mark.respx
def test_links_successfully(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    steps = [Keys.ENTER, Keys.ENTER]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200, json={"data": [{"id": "team-1", "name": "My Team", "slug": "my-team"}]}
        )
    )
    respx_mock.get("/apps/", params={"team_id": "team-1"}).mock(
        return_value=Response(200, json={"data": [{"id": "app-1", "slug": "my-app"}]})
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 0
    assert "Successfully linked to app" in result.output
    assert "my-app" in result.output

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    assert config_path.exists()
    config = AppConfig.model_validate_json(config_path.read_text())
    assert config.app_id == "app-1"
    assert config.team_id == "team-1"


@pytest.mark.respx
def test_shows_error_on_teams_api_failure(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    respx_mock.get("/teams/").mock(return_value=Response(500))

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 1
    assert "Error fetching teams" in result.output


@pytest.mark.respx
def test_shows_error_on_apps_api_failure(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    steps = [Keys.ENTER]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200, json={"data": [{"id": "team-1", "name": "My Team", "slug": "my-team"}]}
        )
    )
    respx_mock.get("/apps/", params={"team_id": "team-1"}).mock(
        return_value=Response(500)
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 1
    assert "Error fetching apps" in result.output


@pytest.mark.respx
def test_links_with_multiple_teams_and_apps(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    steps = [Keys.DOWN_ARROW, Keys.ENTER, Keys.DOWN_ARROW, Keys.ENTER]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"id": "team-1", "name": "Team One", "slug": "team-one"},
                    {"id": "team-2", "name": "Team Two", "slug": "team-two"},
                ]
            },
        )
    )
    respx_mock.get("/apps/", params={"team_id": "team-2"}).mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"id": "app-1", "slug": "first-app"},
                    {"id": "app-2", "slug": "second-app"},
                ]
            },
        )
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = steps
        result = runner.invoke(app, ["link"])

    assert result.exit_code == 0
    assert "Successfully linked to app" in result.output
    assert "second-app" in result.output

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    assert config_path.exists()
    config = AppConfig.model_validate_json(config_path.read_text())
    assert config.app_id == "app-2"
    assert config.team_id == "team-2"
