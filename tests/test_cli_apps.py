import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import respx
import time_machine
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.apps.list import (
    App,
    _get_app_dashboard_url,
)
from fastapi_cloud_cli.config import Settings
from tests.utils import Keys

runner = CliRunner()


@pytest.mark.respx
def test_lists_apps_as_json_with_team_and_pagination_params(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "strawberry",
        "name": "Strawberry",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://strawberryrocks.fastapicloud.dev",
        "region": "us-east-1",
        "updated_at": "2026-05-15T12:00:00Z",
    }
    team_route = respx_mock.get(f"/teams/{team_id}").mock(
        return_value=Response(200, json=team_data)
    )
    respx_mock.get(
        "/apps/",
        params={"team_id": team_id, "limit": "100", "skip": "20"},
    ).mock(return_value=Response(200, json={"data": [app_data], "count": 1}))

    result = runner.invoke(
        app,
        [
            "apps",
            "list",
            "--team-id",
            team_id,
            "--limit",
            "100",
            "--offset",
            "20",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "apps": [app_data],
            "total_count": 1,
            "limit": 100,
            "offset": 20,
        }
    }
    assert team_route.called
    assert result.stderr == ""


def test_lists_apps_json_returns_missing_required_input_without_team_id(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["apps", "list", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Team ID is required.",
            "hint": "Pass --team-id to choose a team.",
        }
    }
    assert result.stderr == ""


def test_gets_app_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["apps", "get", "00000000-0000-4000-8000-000000000002"],
    )

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "fastapi cloud login" in result.output


@pytest.mark.respx
def test_lists_apps_prompts_for_team_when_team_id_is_missing(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "acme",
        "name": "Acme",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team["id"],
        "slug": "api",
        "name": "API",
        "directory": "backend",
    }
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [team], "count": 1})
    )
    apps_route = respx_mock.get("/apps/").mock(
        return_value=Response(200, json={"data": [app_data], "count": 1})
    )

    with patch("rich_toolkit.container.getchar") as mock_getchar:
        mock_getchar.side_effect = [Keys.ENTER]
        result = runner.invoke(app, ["apps", "list"])

    assert result.exit_code == 0
    assert "Select the team:" in result.output
    assert "Acme" in result.output
    assert "API" in result.output
    assert apps_route.calls.last.request.url.params["team_id"] == team["id"]


@pytest.mark.respx
def test_lists_apps_returns_missing_required_input_when_no_teams(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(app, ["apps", "list"])

    assert result.exit_code == 1
    assert "No teams found." in result.output
    assert "Create a team before listing apps." in result.output


def test_lists_apps_rejects_no_input_option(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["apps", "list", "--no-input"])

    assert result.exit_code == 2
    assert "--no-input" in result.output


@pytest.mark.respx
def test_gets_app_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": "00000000-0000-4000-8000-000000000001",
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://api.fastapicloud.app",
    }
    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )

    result = runner.invoke(app, ["apps", "get", app_data["id"], "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app": {
                **app_data,
                "region": None,
                "updated_at": None,
            }
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_app_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_data = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "strawberry",
        "name": "Strawberry",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_data["id"],
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://api.fastapicloud.app",
    }
    dashboard_url = "https://dashboard.fastapicloud.com/strawberry/apps/api"
    respx_mock.get(f"/apps/{app_data['id']}").mock(
        return_value=Response(200, json=app_data)
    )
    respx_mock.get(f"/teams/{team_data['id']}").mock(
        return_value=Response(200, json=team_data)
    )

    result = runner.invoke(app, ["apps", "get", app_data["id"]])

    assert result.exit_code == 0
    assert "app   API" in result.output
    assert "slug   api" in result.output
    assert "directory   backend" in result.output
    assert "url   https://api.fastapicloud.app" in result.output
    assert f"dashboard   {dashboard_url}" in result.output
    assert f"id   {app_data['id']}" in result.output
    assert f"team id   {app_data['team_id']}" in result.output


@pytest.mark.respx
def test_gets_app_json_returns_not_found_for_unknown_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}").mock(return_value=Response(404))

    result = runner.invoke(app, ["apps", "get", app_id, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "App not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""


def test_get_app_dashboard_url_uses_settings_team_and_app_slugs() -> None:
    app_data = App.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000002",
            "team_id": "00000000-0000-4000-8000-000000000001",
            "slug": "api",
            "name": "API",
            "directory": "backend",
        }
    )

    assert (
        _get_app_dashboard_url(
            app_data,
            team_slug="strawberry",
            settings=Settings(dashboard_base_url="https://dashboard.example.com"),
        )
        == "https://dashboard.example.com/strawberry/apps/api"
    )


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_lists_apps_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "strawberry",
        "name": "Strawberry",
    }
    app_data = {
        "id": "00000000-0000-4000-8000-000000000002",
        "team_id": team_id,
        "slug": "api",
        "name": "API",
        "directory": "backend",
        "url": "https://strawberryrocks.fastapicloud.dev",
        "region": "us-east-1",
        "updated_at": "2026-05-15T12:00:00Z",
    }
    respx_mock.get(f"/teams/{team_id}").mock(return_value=Response(200, json=team_data))
    respx_mock.get("/apps/").mock(
        return_value=Response(200, json={"data": [app_data], "count": 1})
    )

    result = runner.invoke(app, ["apps", "list", "--team-id", team_id])

    assert result.exit_code == 0
    assert "apps   Name  ID" in result.output
    assert "API   00000000-0000-4000-8000-000000000002" in result.output


@pytest.mark.respx
def test_lists_apps_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    team_data = {
        "id": team_id,
        "slug": "strawberry",
        "name": "Strawberry",
    }
    respx_mock.get(f"/teams/{team_id}").mock(return_value=Response(200, json=team_data))
    respx_mock.get(
        "/apps/",
        params={"team_id": team_id, "limit": "100", "skip": "0"},
    ).mock(return_value=Response(200, json={"data": [], "count": 0}))

    result = runner.invoke(app, ["apps", "list", "--team-id", team_id])

    assert result.exit_code == 0
    assert "No apps found." in result.output


def test_lists_apps_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(app, ["apps", "list", "--team-id", "team-1"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "fastapi cloud login" in result.output
