import json
from datetime import datetime, timezone
from textwrap import dedent
from typing import Any
from unittest.mock import patch

import pytest
import respx
import time_machine
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.api import CustomDomain, CustomDomainStatus
from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.domains.rendering import (
    DOMAIN_STATUS,
    _get_next_action,
)
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()

APP_ID = "00000000-0000-4000-8000-000000000002"
DOMAIN_ID = "00000000-0000-4000-8000-000000000003"


def _normalize_output(output: str) -> str:
    output = dedent(output.replace("\u200b", "")).strip()
    return "\n".join(line.rstrip() for line in output.splitlines())


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


@pytest.mark.parametrize(
    "command",
    [["list"], ["get", "api.example.com"]],
    ids=["list", "get"],
)
def test_domains_commands_require_user_session(
    command: list[str],
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["domains", *command, "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_logged_in",
            "message": "No credentials found.",
            "hint": "Run `fastapi cloud login`.",
        }
    }


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


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "status": "internal_dcv_timeout",
                "setup_in_progress": False,
                "setup_failed": True,
            },
            (
                "Correct the DNS records, then run "
                "`fastapi cloud domains restart api.example.com`."
            ),
        ),
        (
            {"status": "internal_dcv_invalid"},
            "Correct the DNS records shown. We'll check again automatically.",
        ),
    ],
)
def test_domain_next_action_when_user_intervention_is_required(
    overrides: dict[str, Any],
    expected: str,
) -> None:
    domain = CustomDomain.model_validate(custom_domain(**overrides))

    assert _get_next_action(domain) == expected


def test_domains_get_json_requires_domain(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        ["domains", "get", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Custom domain is required.",
            "hint": "Pass DOMAIN to choose a custom domain.",
        }
    }


@pytest.mark.respx
@pytest.mark.parametrize("identifier", ["  API.Example.COM.  ", DOMAIN_ID])
def test_domains_get_resolves_normalized_hostname_or_id_as_json(
    identifier: str,
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", identifier, "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"app_id": APP_ID, "domain": domain}}


@pytest.mark.respx
@time_machine.travel(datetime(2026, 9, 1, 10, 1, tzinfo=timezone.utc), tick=False)
def test_domains_get_prompts_with_selector_and_renders_details(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    with patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]):
        result = runner.invoke(app, ["domains", "get", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert _normalize_output(result.output) == _normalize_output(
        """
        custom domains

         Select the custom domain to get:
         ● api.example.com

         Select the custom domain to get: api.example.com

        🌐 api.example.com

           hostname       api.example.com
           status         Pending
           raw status     internal_dcv_pending
           setup mode     Standard
           id             00000000-0000-4000-8000-000000000003
           created        4 days ago
           updated        4 days ago
           setup started  4 days ago
           last checked   4 days ago

           Waiting domain verification
           We are checking your DNS configuration to confirm domain ownership. This
           usually takes a few minutes.

         1  Verify ownership and route traffic  In progress
         Add the record below. We'll verify ownership, issue your TLS certificate, and
         route traffic automatically.

         Type   Name  Value
         CNAME  api   00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

        💡 Copy CNAME values as shown. If your DNS provider rejects the trailing dot,
           remove it and try again.

        💡 Using Cloudflare? Set these records to DNS only (gray cloud), not Proxied
           (orange cloud).

        ⏳ Wait for automatic verification. DNS changes can take up to 48 hours to
           propagate.
        """
    )


@pytest.mark.respx
def test_domains_get_reports_not_found(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [custom_domain()], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", "missing.example.com", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": "Custom domain missing.example.com not found.",
            "hint": (
                "Run `fastapi cloud domains list` to see available custom domains."
            ),
        }
    }


@pytest.mark.respx
def test_domains_get_selector_handles_empty_collection(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(app, ["domains", "get", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert "No custom domains found." in result.output


PREVALIDATION_RECORDS = [
    {"type": "TXT", "name": "_fc-dcv.api", "value": "ownership-value"},
    {"type": "TXT", "name": None, "value": None},
    {
        "type": "CNAME",
        "name": "_acme-challenge.api",
        "value": "certificate-value.",
    },
    {"type": "CNAME", "name": "api", "value": "traffic-value."},
]


@pytest.mark.respx
@pytest.mark.parametrize(
    ("status", "shows_certificate", "shows_traffic"),
    [
        ("internal_dcv_pending", False, False),
        ("external_dcv_pending", True, False),
        ("origin_setup_pending", True, True),
    ],
)
def test_domains_get_gates_zero_downtime_records_by_phase(
    status: str,
    shows_certificate: bool,
    shows_traffic: bool,
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(
        status=status,
        is_using_pre_validation=True,
        dns_records=PREVALIDATION_RECORDS,
    )
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", "api.example.com", "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert "ownership-value" in result.output
    assert ("certificate-value" in result.output) is shows_certificate
    assert ("Generating; check again shortly" in result.output) is shows_certificate
    assert ("traffic-value" in result.output) is shows_traffic


@pytest.mark.respx
@time_machine.travel(datetime(2026, 9, 1, 10, 1, tzinfo=timezone.utc), tick=False)
def test_domains_get_shows_url_and_no_action_when_live(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(
        status="origin_setup_success",
        setup_in_progress=False,
        setup_successful=True,
    )
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", domain["name"], "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert _normalize_output(result.output) == _normalize_output(
        """
        custom domains

        🌐 api.example.com

           hostname       api.example.com
           url            https://api.example.com
           status         Live
           raw status     origin_setup_success
           setup mode     Standard
           id             00000000-0000-4000-8000-000000000003
           created        4 days ago
           updated        4 days ago
           setup started  4 days ago
           last checked   4 days ago

           Live
           Your domain is fully configured, secured with TLS, and set up to route
           traffic to your app.

         1  Verify ownership and route traffic  Verified
         Your domain is live on FastAPI Cloud.

         Type   Name  Value
         CNAME  api   00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

        💡 Copy CNAME values as shown. If your DNS provider rejects the trailing dot,
           remove it and try again.

        ⏳ No action needed. Your domain is live.
        """
    )
