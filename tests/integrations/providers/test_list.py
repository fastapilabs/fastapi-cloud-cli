import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.utils.apps import AppConfig, write_app_config
from tests.utils import Keys, SnapshotCliRunner, changing_dir

runner = SnapshotCliRunner()

TEAM_ID = "00000000-0000-4000-8000-000000000001"
LINKED_TEAM_ID = "00000000-0000-4000-8000-000000000002"
INTEGRATION_ID = "00000000-0000-4000-8000-000000000003"

NEON_AVAILABLE = {
    "id": "neon",
    "name": "Neon",
    "description": "Serverless Postgres database for your applications.",
    "category": "database",
    "status": "available",
    "default_env_var_name": "DATABASE_URL",
    "suggested_env_var_name": "NEON_DATABASE_URL",
    "connection_string_template": (
        "postgresql://<user>:<password>@<host>/<database>"
        "?sslmode=require&channel_binding=require"
    ),
}
NEON_CONNECTED = {
    **NEON_AVAILABLE,
    "status": "connected",
    "connected_integration": {
        "id": INTEGRATION_ID,
        "type": "neon",
        "created_at": "2026-08-18T10:00:00Z",
    },
}
REDIS_AVAILABLE = {
    "id": "redis",
    "name": "Redis Cloud",
    "description": "In-memory data store for caching and real-time features.",
    "category": "database",
    "status": "available",
    "default_env_var_name": "REDIS_URL",
    "suggested_env_var_name": "REDIS_CLOUD_URL",
    "connection_string_template": None,
}
LOGFIRE_COMING_SOON = {
    "id": "logfire",
    "name": "Logfire",
    "description": "Observability for traces, metrics, and logs.",
    "category": "observability",
    "status": "coming_soon",
    "default_env_var_name": "LOGFIRE_TOKEN",
    "suggested_env_var_name": "LOGFIRE_TOKEN_2",
    "connection_string_template": None,
}
NEON_CONNECTED_OUTPUT = {
    "id": "neon",
    "name": "Neon",
    "status": "connected",
    "connected_integration": {"id": INTEGRATION_ID},
}
REDIS_AVAILABLE_OUTPUT = {
    "id": "redis",
    "name": "Redis Cloud",
    "status": "available",
    "connected_integration": None,
}


def test_lists_providers_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["integrations", "providers", "list", "--team-id", TEAM_ID, "--json"],
    )

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
def test_lists_providers_as_json_with_explicit_team_overriding_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(
            app_id="00000000-0000-4000-8000-000000000004", team_id=LINKED_TEAM_ID
        ),
    )
    respx_mock.get(f"/teams/{TEAM_ID}/integrations").mock(
        return_value=Response(
            200,
            json={"data": [NEON_CONNECTED, REDIS_AVAILABLE], "count": 2},
        )
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            [
                "integrations",
                "providers",
                "list",
                "--team-id",
                TEAM_ID,
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "team_id": TEAM_ID,
            "providers": [NEON_CONNECTED_OUTPUT, REDIS_AVAILABLE_OUTPUT],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_providers_uses_linked_app_team(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id="00000000-0000-4000-8000-000000000004", team_id=TEAM_ID),
    )
    respx_mock.get(f"/teams/{TEAM_ID}/integrations").mock(
        return_value=Response(
            200,
            json={"data": [REDIS_AVAILABLE], "count": 1},
        )
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "providers", "list", "--json"],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "team_id": TEAM_ID,
            "providers": [REDIS_AVAILABLE_OUTPUT],
        }
    }


def test_lists_providers_json_requires_team_without_linked_app(
    logged_in_cli: None,
    tmp_path: Path,
) -> None:
    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "providers", "list", "--json"],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Team ID is required.",
            "hint": "Pass --team-id or run the command from a linked app.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_providers_prompts_for_team_and_renders_statuses(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    team = {"id": TEAM_ID, "slug": "acme", "name": "Acme"}
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [team], "count": 1})
    )
    respx_mock.get(f"/teams/{TEAM_ID}/integrations").mock(
        return_value=Response(
            200,
            json={
                "data": [LOGFIRE_COMING_SOON, NEON_CONNECTED, REDIS_AVAILABLE],
                "count": 3,
            },
        )
    )

    with (
        changing_dir(tmp_path),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = [Keys.ENTER]
        result = runner.invoke(app, ["integrations", "providers", "list"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
Select the team:
Filter:

● Acme

Select the team: Acme

integrations

Name         Status         Integration ID

Logfire      coming soon    -
Neon         connected      00000000-0000-4000-8000-000000000003
Redis Cloud  not connected  -\
""")


@pytest.mark.respx
def test_lists_providers_returns_missing_input_when_no_teams_exist(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    respx_mock.get("/teams/").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    with changing_dir(tmp_path):
        result = runner.invoke(app, ["integrations", "providers", "list"])

    assert result.exit_code == 1
    assert result.output == snapshot("""\
✗ error: No teams found.

  hint: Create a team before listing integration providers.\
""")


@pytest.mark.respx
def test_lists_providers_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/teams/{TEAM_ID}/integrations").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(
        app,
        ["integrations", "providers", "list", "--team-id", TEAM_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
integrations

No integration providers available.\
""")


@pytest.mark.respx
def test_lists_providers_json_returns_not_found_for_unknown_team(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/teams/{TEAM_ID}/integrations").mock(return_value=Response(404))

    result = runner.invoke(
        app,
        ["integrations", "providers", "list", "--team-id", TEAM_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "Team not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""
