import json
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any

import pytest
import respx
import time_machine
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.api import CustomDomainStatus
from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.domains.rendering import DOMAIN_STATUS
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()

APP_ID = "00000000-0000-4000-8000-000000000002"
DOMAIN_ID = "00000000-0000-4000-8000-000000000003"


def _normalize_output(output: str) -> str:
    return "\n".join(line.rstrip() for line in dedent(output).strip().splitlines())


def custom_domain(**overrides: Any) -> dict[str, Any]:
    return {
        "id": DOMAIN_ID,
        "name": "api.example.com",
        "status": "internal_dcv_pending",
        "setup_in_progress": True,
        "setup_failed": False,
        "setup_successful": False,
        "is_using_pre_validation": False,
        "dns_records": [
            {
                "type": "CNAME",
                "name": "api",
                "value": f"{DOMAIN_ID}.endpoints.fastapicloud.dev.",
            }
        ],
        "created_at": "2026-08-28T10:00:00Z",
        "updated_at": "2026-08-28T10:01:00Z",
        "setup_started_at": "2026-08-28T10:00:00Z",
        "setup_checked_at": "2026-08-28T10:01:00Z",
        "app_id": APP_ID,
        **overrides,
    }


def test_domains_list_requires_user_session(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["domains", "list", "--app-id", APP_ID])

    assert result.exit_code == 1
    assert "No credentials found." in result.output
    assert "FASTAPI_CLOUD_TOKEN" not in result.output


def test_domains_list_requires_app_context(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["domains", "list", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "App ID is required.",
            "hint": "Pass --app-id or run `fastapi cloud apps create --link` first.",
        }
    }


@pytest.mark.respx
@time_machine.travel(datetime(2026, 9, 1, 10, 1, tzinfo=timezone.utc), tick=False)
def test_domains_list_uses_linked_app_and_renders_rows(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    newest = custom_domain(
        id="00000000-0000-4000-8000-000000000004",
        name="new.example.com",
        status="origin_setup_success",
        setup_in_progress=False,
        setup_successful=True,
        is_using_pre_validation=True,
        app_id=configured_app.app_id,
    )
    oldest = custom_domain(name="old.example.com", app_id=configured_app.app_id)
    respx_mock.get(f"/apps/{configured_app.app_id}/custom-domains").mock(
        return_value=Response(200, json={"data": [newest, oldest], "count": 2})
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["domains", "list"])

    assert result.exit_code == 0
    assert _normalize_output(result.output) == _normalize_output(
        """
        custom domains

        Domain           Status   Setup mode     Last check

        new.example.com  Live     Zero-downtime  4 days ago
        old.example.com  Pending  Standard       4 days ago
        """
    )


@pytest.mark.respx
def test_domains_list_returns_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(app, ["domains", "list", "--app-id", APP_ID, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "domains": [domain],
            "total_count": 1,
        }
    }


@pytest.mark.respx
def test_domains_list_renders_empty_state(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(app, ["domains", "list", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert "No custom domains found." in result.output


@pytest.mark.respx
def test_domains_list_surfaces_app_not_found_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(404, json={"detail": "App not found"})
    )

    result = runner.invoke(app, ["domains", "list", "--app-id", APP_ID, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "App not found",
            "hint": None,
        }
    }


def test_domain_status_metadata_is_exhaustive() -> None:
    assert set(DOMAIN_STATUS) == set(CustomDomainStatus)
