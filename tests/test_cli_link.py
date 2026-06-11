import json
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


def test_link_json_requires_app_id(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["link", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "App ID is required.",
            "hint": "Pass an app ID to link an app.",
        }
    }
    assert result.stderr == ""


def test_link_json_returns_not_logged_in_when_logged_out(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["link", "--json"])

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
def test_link_direct_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    result = runner.invoke(
        app,
        [
            "link",
            app_id,
            "--path",
            str(path_to_link),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "team_id": team_id,
            "path": str(path_to_link),
        }
    }
    assert AppConfig.model_validate_json(
        (path_to_link / ".fastapicloud" / "cloud.json").read_text(encoding="utf-8")
    ) == AppConfig(app_id=app_id, team_id=team_id)
    assert result.stderr == ""


@pytest.mark.respx
def test_link_direct_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    result = runner.invoke(
        app,
        [
            "link",
            app_id,
            "--path",
            str(path_to_link),
        ],
    )

    assert result.exit_code == 0
    assert "Linked" in result.output
    assert "API" in result.output
    assert "Config:" in result.output
    assert "cloud.json" in result.output
    assert AppConfig.model_validate_json(
        (path_to_link / ".fastapicloud" / "cloud.json").read_text(encoding="utf-8")
    ) == AppConfig(app_id=app_id, team_id=team_id)


@pytest.mark.respx
def test_link_direct_with_app_id_option_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    app_id = "00000000-0000-4000-8000-000000000002"
    path_to_link = tmp_path / "repo"
    path_to_link.mkdir()
    app_data = {
        "id": app_id,
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": None,
    }
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(200, json=app_data))

    result = runner.invoke(
        app,
        [
            "link",
            "--app-id",
            app_id,
            "--path",
            str(path_to_link),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "team_id": team_id,
            "path": str(path_to_link),
        }
    }
    assert AppConfig.model_validate_json(
        (path_to_link / ".fastapicloud" / "cloud.json").read_text(encoding="utf-8")
    ) == AppConfig(app_id=app_id, team_id=team_id)
    assert result.stderr == ""


def test_link_returns_invalid_input_when_app_id_is_ambiguous(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "link",
            "00000000-0000-4000-8000-000000000002",
            "--app-id",
            "00000000-0000-4000-8000-000000000003",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "App ID was provided more than once.",
            "hint": "Pass either APP_ID or --app-id, not both.",
        }
    }
    assert result.stderr == ""


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
def test_app_menu_is_ordered_by_slug(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    steps = [Keys.ENTER, Keys.ENTER]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200, json={"data": [{"id": "team-1", "name": "My Team", "slug": "my-team"}]}
        )
    )
    respx_mock.get("/apps/", params={"team_id": "team-1"}).mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"id": "app-2", "slug": "zebra"},
                    {"id": "app-1", "slug": "alpha"},
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
    assert "alpha" in result.output

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config = AppConfig.model_validate_json(config_path.read_text())
    assert config.app_id == "app-1"


@pytest.mark.respx
def test_team_menu_is_ordered_by_name(
    logged_in_cli: None, respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    steps = [Keys.ENTER, Keys.ENTER]

    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"id": "team-2", "name": "Zebra Team", "slug": "zebra-team"},
                    {"id": "team-1", "name": "Alpha Team", "slug": "alpha-team"},
                ]
            },
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

    config_path = tmp_path / ".fastapicloud" / "cloud.json"
    config = AppConfig.model_validate_json(config_path.read_text())
    assert config.team_id == "team-1"


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
