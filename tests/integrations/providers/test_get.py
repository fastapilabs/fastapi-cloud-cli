import json
from typing import Literal

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app

runner = CliRunner()

Provider = Literal["neon", "redis", "supabase", "logfire"]

INTEGRATION_ID = "00000000-0000-4000-8000-000000000001"
APP_ID = "00000000-0000-4000-8000-000000000002"
RESOURCE_ID = "00000000-0000-4000-8000-000000000003"
SECOND_RESOURCE_ID = "00000000-0000-4000-8000-000000000004"
CREATED_AT = "2026-08-18T10:00:00Z"
RESOURCE_CREATED_AT = "2026-08-19T11:00:00Z"
SECOND_RESOURCE_CREATED_AT = "2026-08-18T11:00:00Z"


def _integration(*, provider: Provider = "neon") -> dict[str, str]:
    return {
        "id": INTEGRATION_ID,
        "type": provider,
        "created_at": CREATED_AT,
    }


def _resource(
    *,
    resource_id: str = RESOURCE_ID,
    name: str = "primary",
    created_at: str = RESOURCE_CREATED_AT,
) -> dict[str, object]:
    return {
        "id": resource_id,
        "name": name,
        "app": {
            "id": APP_ID,
            "name": "API",
            "slug": "api",
            "team_id": "unused-team-id",
        },
        "provider_metadata": {
            "type": "neon",
            "project_id": "unused-project-id",
            "database_name": "unused-database-name",
        },
        "created_at": created_at,
        "updated_at": "2026-08-20T12:00:00Z",
    }


def test_gets_provider_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["integrations", "providers", "get", INTEGRATION_ID, "--json"],
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
def test_gets_provider_and_resources_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    resources = [
        _resource(),
        _resource(
            resource_id=SECOND_RESOURCE_ID,
            name="analytics",
            created_at=SECOND_RESOURCE_CREATED_AT,
        ),
    ]
    respx_mock.get(f"/integrations/{INTEGRATION_ID}").mock(
        return_value=Response(200, json=_integration())
    )
    respx_mock.get(f"/integrations/{INTEGRATION_ID}/connected-resources").mock(
        return_value=Response(200, json={"data": resources, "count": 2})
    )

    result = runner.invoke(
        app,
        ["integrations", "providers", "get", INTEGRATION_ID, "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "integration": {
                "id": INTEGRATION_ID,
                "provider": "neon",
                "created_at": CREATED_AT,
            },
            "resources": [
                {
                    "id": RESOURCE_ID,
                    "name": "primary",
                    "app": {"id": APP_ID, "name": "API"},
                    "created_at": RESOURCE_CREATED_AT,
                },
                {
                    "id": SECOND_RESOURCE_ID,
                    "name": "analytics",
                    "app": {"id": APP_ID, "name": "API"},
                    "created_at": SECOND_RESOURCE_CREATED_AT,
                },
            ],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_provider_and_resources_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    resources = [
        _resource(),
        _resource(
            resource_id=SECOND_RESOURCE_ID,
            name="analytics",
            created_at=SECOND_RESOURCE_CREATED_AT,
        ),
    ]
    respx_mock.get(f"/integrations/{INTEGRATION_ID}").mock(
        return_value=Response(200, json=_integration(provider="redis"))
    )
    respx_mock.get(f"/integrations/{INTEGRATION_ID}/connected-resources").mock(
        return_value=Response(200, json={"data": resources, "count": 2})
    )

    result = runner.invoke(
        app,
        ["integrations", "providers", "get", INTEGRATION_ID],
    )

    assert result.exit_code == 0
    assert "integration" in result.output
    assert "Redis Cloud" in result.output
    assert f"id         {INTEGRATION_ID}" in result.output
    assert "provider   Redis Cloud" in result.output
    assert "connected resources" in result.output
    assert "Name" in result.output
    assert "App" in result.output
    assert "Resource ID" in result.output
    assert "Connected" in result.output
    assert "primary" in result.output
    assert "API" in result.output
    assert RESOURCE_ID in result.output
    assert result.output.index("primary") < result.output.index("analytics")
    assert APP_ID not in result.output
    assert "unused-project-id" not in result.output


@pytest.mark.respx
def test_gets_provider_in_human_output_without_resources(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/integrations/{INTEGRATION_ID}").mock(
        return_value=Response(200, json=_integration())
    )
    respx_mock.get(f"/integrations/{INTEGRATION_ID}/connected-resources").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(
        app,
        ["integrations", "providers", "get", INTEGRATION_ID],
    )

    assert result.exit_code == 0
    assert "No connected resources found." in result.output


@pytest.mark.respx
def test_gets_provider_json_returns_not_found(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/integrations/{INTEGRATION_ID}").mock(return_value=Response(404))

    result = runner.invoke(
        app,
        ["integrations", "providers", "get", INTEGRATION_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "Integration not found.",
            "hint": None,
        }
    }
    assert result.stderr == ""
