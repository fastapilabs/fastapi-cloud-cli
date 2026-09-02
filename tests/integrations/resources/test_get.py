import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pytest
import respx
import time_machine
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.utils.apps import AppConfig, write_app_config
from tests.utils import SnapshotCliRunner, changing_dir

runner = SnapshotCliRunner()

DatabaseProvider = Literal["neon", "redis", "supabase"]

APP_ID = "00000000-0000-4000-8000-000000000001"
LINKED_APP_ID = "00000000-0000-4000-8000-000000000002"
TEAM_ID = "00000000-0000-4000-8000-000000000003"
RESOURCE_ID = "00000000-0000-4000-8000-000000000004"
INTEGRATION_ID = "00000000-0000-4000-8000-000000000005"
CONSOLE_URL = "https://provider.example/resource"
CREATED_AT = "2026-08-18T10:00:00Z"
UPDATED_AT = "2026-08-19T11:00:00Z"


def _database_resource(
    *,
    provider: DatabaseProvider = "neon",
    environment_variables: list[str] | None = None,
) -> dict[str, object]:
    if environment_variables is None:
        environment_variables = ["DATABASE_URL", "DATABASE_PASSWORD"]

    return {
        "id": RESOURCE_ID,
        "name": "production",
        "app_id": APP_ID,
        "integration_id": INTEGRATION_ID,
        "provider_metadata": {
            "type": provider,
            "database_name": "app_db",
            "project_id": "unused-project-id",
            "branch_id": "unused-branch-id",
        },
        "console_url": CONSOLE_URL,
        "environment_variables": [{"name": name} for name in environment_variables],
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }


def _logfire_resource(
    *,
    environment_variables: list[str] | None = None,
) -> dict[str, object]:
    if environment_variables is None:
        environment_variables = ["LOGFIRE_TOKEN"]

    return {
        "id": RESOURCE_ID,
        "name": "observability",
        "app_id": APP_ID,
        "integration_id": INTEGRATION_ID,
        "provider_metadata": {
            "type": "logfire",
            "project_id": "unused-project-id",
            "project_name": "fastapi-api",
            "organization_name": "acme",
            "write_token_id": "unused-token-id",
        },
        "console_url": CONSOLE_URL,
        "environment_variables": [{"name": name} for name in environment_variables],
        "created_at": CREATED_AT,
        "updated_at": UPDATED_AT,
    }


def test_gets_resource_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "integrations",
            "resources",
            "get",
            RESOURCE_ID,
            "--app-id",
            APP_ID,
            "--json",
        ],
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
def test_gets_database_resource_as_json_with_explicit_app_overriding_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=LINKED_APP_ID, team_id=TEAM_ID),
    )
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(200, json=_database_resource())
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "get",
                RESOURCE_ID,
                "--app-id",
                APP_ID,
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "resource": {
                "id": RESOURCE_ID,
                "name": "production",
                "provider": "neon",
                "console_url": CONSOLE_URL,
                "environment_variables": ["DATABASE_URL", "DATABASE_PASSWORD"],
                "created_at": CREATED_AT,
                "updated_at": UPDATED_AT,
                "database_name": "app_db",
            },
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_logfire_resource_as_json_using_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=APP_ID, team_id=TEAM_ID),
    )
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(200, json=_logfire_resource())
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "resources", "get", RESOURCE_ID, "--json"],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "resource": {
                "id": RESOURCE_ID,
                "name": "observability",
                "provider": "logfire",
                "console_url": CONSOLE_URL,
                "environment_variables": ["LOGFIRE_TOKEN"],
                "created_at": CREATED_AT,
                "updated_at": UPDATED_AT,
                "project_name": "fastapi-api",
                "organization_name": "acme",
            },
        }
    }


def test_gets_resource_json_requires_app_without_linked_app(
    logged_in_cli: None,
    tmp_path: Path,
) -> None:
    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "resources", "get", RESOURCE_ID, "--json"],
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
@time_machine.travel(datetime(2026, 9, 1, 10, tzinfo=timezone.utc), tick=False)
def test_gets_database_resource_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(200, json=_database_resource())
    )

    result = runner.invoke(
        app,
        ["integrations", "resources", "get", RESOURCE_ID, "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
connected resource

🔌 production

   id                     00000000-0000-4000-8000-000000000004
   provider               Neon
   database               app_db
   console                https://provider.example/resource
   environment variables  DATABASE_URL
                          DATABASE_PASSWORD
   connected              14 days ago
   last updated           12 days ago\
""")


@pytest.mark.respx
@time_machine.travel(datetime(2026, 9, 1, 10, tzinfo=timezone.utc), tick=False)
def test_gets_logfire_resource_in_human_output_without_environment_variables(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(
            200,
            json=_logfire_resource(environment_variables=[]),
        )
    )

    result = runner.invoke(
        app,
        ["integrations", "resources", "get", RESOURCE_ID, "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
connected resource

🔌 observability

   id                     00000000-0000-4000-8000-000000000004
   provider               Logfire
   project                fastapi-api
   organization           acme
   console                https://provider.example/resource
   environment variables  -
   connected              14 days ago
   last updated           12 days ago\
""")


@pytest.mark.respx
def test_gets_resource_json_returns_not_found(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(404)
    )

    result = runner.invoke(
        app,
        [
            "integrations",
            "resources",
            "get",
            RESOURCE_ID,
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "Connected resource not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""
