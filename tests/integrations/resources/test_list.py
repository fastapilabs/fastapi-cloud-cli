import json
from pathlib import Path
from typing import Literal

import pytest
import respx
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.utils.apps import AppConfig, write_app_config
from tests.utils import SnapshotCliRunner, changing_dir

runner = SnapshotCliRunner()

Provider = Literal["neon", "redis", "supabase", "logfire"]

APP_ID = "00000000-0000-4000-8000-000000000001"
LINKED_APP_ID = "00000000-0000-4000-8000-000000000002"
TEAM_ID = "00000000-0000-4000-8000-000000000003"
RESOURCE_ID = "00000000-0000-4000-8000-000000000004"


def _resource(
    *,
    resource_id: str = RESOURCE_ID,
    name: str = "production",
    provider: Provider = "neon",
) -> dict[str, object]:
    return {
        "id": resource_id,
        "name": name,
        "app_id": APP_ID,
        "integration_id": "00000000-0000-4000-8000-000000000005",
        "provider_metadata": {
            "type": provider,
            "database_name": "unused-by-list",
        },
        "console_url": "https://provider.example/resource",
        "created_at": "2026-08-18T10:00:00Z",
        "updated_at": "2026-08-18T10:00:00Z",
    }


def test_lists_resources_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["integrations", "resources", "list", "--app-id", APP_ID, "--json"],
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
def test_lists_resources_as_json_with_explicit_app_overriding_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=LINKED_APP_ID, team_id=TEAM_ID),
    )
    respx_mock.get(f"/apps/{APP_ID}/connected-resources").mock(
        return_value=Response(
            200,
            json={"data": [_resource()], "count": 1},
        )
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "list",
                "--app-id",
                APP_ID,
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "resources": [
                {
                    "id": RESOURCE_ID,
                    "name": "production",
                    "provider": "neon",
                }
            ],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_resources_uses_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=APP_ID, team_id=TEAM_ID),
    )
    respx_mock.get(f"/apps/{APP_ID}/connected-resources").mock(
        return_value=Response(
            200,
            json={"data": [_resource(provider="redis")], "count": 1},
        )
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "resources", "list", "--json"],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "resources": [
                {
                    "id": RESOURCE_ID,
                    "name": "production",
                    "provider": "redis",
                }
            ],
        }
    }


def test_lists_resources_json_requires_app_without_linked_app(
    logged_in_cli: None,
    tmp_path: Path,
) -> None:
    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            ["integrations", "resources", "list", "--json"],
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
def test_lists_resources_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    resources = [
        _resource(
            resource_id="00000000-0000-4000-8000-000000000010",
            name="primary",
            provider="neon",
        ),
        _resource(
            resource_id="00000000-0000-4000-8000-000000000011",
            name="cache",
            provider="redis",
        ),
        _resource(
            resource_id="00000000-0000-4000-8000-000000000012",
            name="analytics",
            provider="supabase",
        ),
        _resource(
            resource_id="00000000-0000-4000-8000-000000000013",
            name="observability",
            provider="logfire",
        ),
    ]
    respx_mock.get(f"/apps/{APP_ID}/connected-resources").mock(
        return_value=Response(200, json={"data": resources, "count": len(resources)})
    )

    result = runner.invoke(
        app,
        ["integrations", "resources", "list", "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
connected resources

Name           Provider     Resource ID

primary        Neon         00000000-0000-4000-8000-000000000010
cache          Redis Cloud  00000000-0000-4000-8000-000000000011
analytics      Supabase     00000000-0000-4000-8000-000000000012
observability  Logfire      00000000-0000-4000-8000-000000000013\
""")


@pytest.mark.respx
def test_lists_resources_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(
        app,
        ["integrations", "resources", "list", "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
connected resources

No connected resources found.\
""")


@pytest.mark.respx
def test_lists_resources_json_returns_not_found_for_unknown_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources").mock(
        return_value=Response(404)
    )

    result = runner.invoke(
        app,
        ["integrations", "resources", "list", "--app-id", APP_ID, "--json"],
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
