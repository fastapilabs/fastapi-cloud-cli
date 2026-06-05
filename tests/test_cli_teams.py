import json

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app

runner = CliRunner()


@pytest.mark.respx
def test_lists_teams_as_json_with_pagination_params(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "acme",
        "name": "Acme",
    }
    respx_mock.get("/teams/", params={"limit": "100", "skip": "20"}).mock(
        return_value=Response(200, json={"data": [team], "count": 1})
    )

    result = runner.invoke(
        app,
        ["teams", "list", "--limit", "100", "--offset", "20", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "teams": [team],
            "total_count": 1,
            "limit": 100,
            "offset": 20,
        }
    }
    assert result.stderr == ""


def test_lists_teams_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(app, ["teams", "list", "--json"])

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
def test_lists_teams_human_shows_api_error(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/teams/").mock(return_value=Response(500))

    result = runner.invoke(app, ["teams", "list"])

    assert result.exit_code == 1
    assert "Error fetching teams. Please try again later." in result.output


@pytest.mark.respx
def test_lists_teams_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "id": "00000000-0000-4000-8000-000000000001",
                        "slug": "acme",
                        "name": "Acme",
                    }
                ],
                "count": 1,
            },
        )
    )

    result = runner.invoke(app, ["teams", "list"])

    assert result.exit_code == 0
    assert "teams   Name  ID" in result.output
    assert "Slug" not in result.output
    assert "acme" not in result.output
    assert "Acme  00000000-0000-4000-8000-000000000001" in result.output


@pytest.mark.respx
def test_lists_teams_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get("/teams/").mock(
        return_value=Response(
            200,
            json={"data": [], "count": 1},
        )
    )

    result = runner.invoke(app, ["teams", "list"])

    assert result.exit_code == 0
    assert "No teams found." in result.output


def test_lists_teams_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(app, ["teams", "list"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "fastapi cloud login" in result.output


def test_gets_team_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["teams", "get", "00000000-0000-4000-8000-000000000001"],
    )

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "fastapi cloud login" in result.output


@pytest.mark.respx
def test_gets_team_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "acme",
        "name": "Acme",
    }
    respx_mock.get(f"/teams/{team['id']}").mock(return_value=Response(200, json=team))

    result = runner.invoke(app, ["teams", "get", team["id"], "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"team": team}}
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_team_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team = {
        "id": "00000000-0000-4000-8000-000000000001",
        "slug": "acme",
        "name": "Acme",
    }
    dashboard_url = "https://dashboard.fastapicloud.com/acme/apps"
    respx_mock.get(f"/teams/{team['id']}").mock(return_value=Response(200, json=team))

    result = runner.invoke(app, ["teams", "get", team["id"]])

    assert result.exit_code == 0
    assert "team   Acme" in result.output
    assert f"id   {team['id']}" in result.output
    assert "slug   acme" in result.output
    assert f"url   {dashboard_url}" in result.output
    assert "Team:" not in result.output


@pytest.mark.respx
def test_gets_team_json_returns_not_found_for_unknown_team(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    respx_mock.get(f"/teams/{team_id}").mock(return_value=Response(404))

    result = runner.invoke(app, ["teams", "get", team_id, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "Team not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_team_json_returns_permission_denied(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    team_id = "00000000-0000-4000-8000-000000000001"
    respx_mock.get(f"/teams/{team_id}").mock(return_value=Response(403))

    result = runner.invoke(app, ["teams", "get", team_id, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "permission_denied",
            "message": "You don't have permissions for this resource",
            "hint": None,
        }
    }
    assert result.stderr == ""
