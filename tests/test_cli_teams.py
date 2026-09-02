import json

import pytest
import respx
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from tests.utils import SnapshotCliRunner

runner = SnapshotCliRunner()


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
            "hint": "Run `fastapi cloud login`.",
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
    assert result.output == snapshot("""\
teams

Name  ID

Acme  00000000-0000-4000-8000-000000000001\
""")


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
    assert result.output == snapshot("""\
teams

No teams found.\
""")


def test_lists_teams_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(app, ["teams", "list"])

    assert result.exit_code == 1
    assert result.output == snapshot("""\
✗ error: No credentials found.

  hint: Run `fastapi cloud login`.\
""")


def test_gets_team_human_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["teams", "get", "00000000-0000-4000-8000-000000000001"],
    )

    assert result.exit_code == 1
    assert result.output == snapshot("""\
✗ error: No credentials found.

  hint: Run `fastapi cloud login`.\
""")


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
    respx_mock.get(f"/teams/{team['id']}").mock(return_value=Response(200, json=team))

    result = runner.invoke(app, ["teams", "get", team["id"]])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
🏢 Acme

   id    00000000-0000-4000-8000-000000000001
   slug  acme
   url   https://dashboard.fastapicloud.com/acme/apps\
""")


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
