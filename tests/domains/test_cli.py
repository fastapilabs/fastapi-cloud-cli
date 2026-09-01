import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
import respx
import time_machine
from httpx import ConnectError, Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.api import CustomDomainStatus
from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.domains.rendering import DOMAIN_STATUS
from tests.conftest import ConfiguredApp
from tests.utils import Keys, SnapshotCliRunner, changing_dir

runner = SnapshotCliRunner()

APP_ID = "00000000-0000-4000-8000-000000000002"
DOMAIN_ID = "00000000-0000-4000-8000-000000000003"


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
    [
        ["list"],
        ["get", "api.example.com"],
        ["add", "api.example.com", "--standard"],
        ["remove", "api.example.com", "--yes"],
        ["restart", "api.example.com"],
    ],
    ids=["list", "get", "add", "remove", "restart"],
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
    assert result.output == snapshot("""\
custom domains

Domain           Status   Setup mode     Last check

new.example.com  Live     Zero-downtime  4 days ago
old.example.com  Pending  Standard       4 days ago\
""")


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
    assert result.output == snapshot("""\
custom domains

No custom domains found.\
""")


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


@pytest.mark.respx
def test_domains_get_renders_restart_action_when_setup_failed(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(
        status="internal_dcv_timeout",
        setup_in_progress=False,
        setup_failed=True,
    )
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", domain["name"], "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🌐 api.example.com

⚠️ Restart domain verification
   We couldn't verify the domain in time, it's possible the DNS changes may
   still be propagating. Please restart the domain verification process.

   To verify ownership and route traffic, add this CNAME record at your DNS
   provider:

   type   CNAME
   name   api
   value  00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

💡 Copy as shown; remove the trailing dot only if your provider rejects it.
   Cloudflare: use DNS only (gray cloud).

   Correct the DNS records, then run `fastapi cloud domains restart
   api.example.com`.\
""")


@pytest.mark.respx
def test_domains_get_renders_correction_action_when_dns_is_invalid(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(status="internal_dcv_invalid")
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", domain["name"], "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🌐 api.example.com

⚠️ Verification needed
   The DNS records were found but don't match the expected values. Double-check
   your provider settings.

   To verify ownership and route traffic, add this CNAME record at your DNS
   provider:

   type   CNAME
   name   api
   value  00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

💡 Copy as shown; remove the trailing dot only if your provider rejects it.
   Cloudflare: use DNS only (gray cloud).

   Correct the DNS records shown. We'll check again automatically.\
""")


@pytest.mark.respx
def test_domains_get_omits_next_action_while_setup_is_in_progress(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(dns_records=[])
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    result = runner.invoke(
        app,
        ["domains", "get", domain["name"], "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🌐 api.example.com

⏳ Waiting domain verification
   We are checking your DNS configuration to confirm domain ownership. This
   usually takes a few minutes.

   Add the record below. We'll verify ownership, issue your TLS certificate,
   and route traffic automatically.\
""")


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
    assert result.output == snapshot("""\
custom domains

 Select the custom domain to get:
 ● api.example.com

 Select the custom domain to get: api.example.com

🌐 api.example.com

⏳ Waiting domain verification
   We are checking your DNS configuration to confirm domain ownership. This
   usually takes a few minutes.

   To verify ownership and route traffic, add this CNAME record at your DNS
   provider:

   type   CNAME
   name   api
   value  00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

💡 Copy as shown; remove the trailing dot only if your provider rejects it.
   Cloudflare: use DNS only (gray cloud).\
""")


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
    assert result.output == snapshot("""\
custom domains

No custom domains found.\
""")


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
    ("status", "shows_ownership", "shows_certificate", "shows_traffic", "done_steps"),
    [
        ("internal_dcv_pending", True, False, False, 0),
        ("external_dcv_pending", False, True, False, 1),
        ("origin_setup_pending", False, False, True, 2),
    ],
)
def test_domains_get_gates_zero_downtime_records_by_phase(
    status: str,
    shows_ownership: bool,
    shows_certificate: bool,
    shows_traffic: bool,
    done_steps: int,
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
    assert ("ownership-value" in result.output) is shows_ownership
    assert ("certificate-value" in result.output) is shows_certificate
    assert ("Generating; check again shortly" in result.output) is shows_certificate
    assert ("Type" in result.output) is shows_certificate
    assert ("traffic-value" in result.output) is shows_traffic
    assert result.output.count("✅") == done_steps


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
    assert result.output == snapshot("""\
custom domains

🌐 https://api.example.com

✅ Your domain is live.\
""")


def test_domains_add_json_requires_domain(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        ["domains", "add", "--standard", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Custom domain is required.",
            "hint": "Pass DOMAIN to choose the hostname to add.",
        }
    }


def test_domains_add_json_requires_setup_mode(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        ["domains", "add", "api.example.com", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Custom domain setup mode is required.",
            "hint": "Pass either --standard or --zero-downtime.",
        }
    }


def test_domains_add_rejects_both_setup_modes(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        [
            "domains",
            "add",
            "api.example.com",
            "--standard",
            "--zero-downtime",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Setup modes are mutually exclusive.",
            "hint": "Pass either --standard or --zero-downtime.",
        }
    }


@pytest.mark.respx
def test_domains_add_surfaces_backend_hostname_validation(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    message = "Domain name must have at least two labels (e.g., example.com)"
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={"name": "localhost", "is_using_pre_validation": False},
    ).mock(
        return_value=Response(
            422,
            json={
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body", "name"],
                        "msg": f"Value error, {message}",
                        "input": "localhost",
                    }
                ]
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "add",
            "  LOCALHOST. ",
            "--standard",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": message,
            "hint": None,
        }
    }


@pytest.mark.respx
@pytest.mark.parametrize(
    ("flag", "is_using_pre_validation"),
    [("--standard", False), ("--zero-downtime", True)],
)
def test_domains_add_posts_setup_mode_and_returns_json(
    flag: str,
    is_using_pre_validation: bool,
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(
        name="api.example.com",
        is_using_pre_validation=is_using_pre_validation,
    )
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={
            "name": "api.example.com",
            "is_using_pre_validation": is_using_pre_validation,
        },
    ).mock(return_value=Response(201, json=domain))

    result = runner.invoke(
        app,
        [
            "domains",
            "add",
            "  API.Example.COM. ",
            flag,
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"app_id": APP_ID, "domain": domain}}


@pytest.mark.respx
def test_domains_add_with_arguments_renders_result(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={"name": "api.example.com", "is_using_pre_validation": False},
    ).mock(return_value=Response(201, json=domain))

    result = runner.invoke(
        app,
        [
            "domains",
            "add",
            "api.example.com",
            "--standard",
            "--app-id",
            APP_ID,
        ],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🐔 Added api.example.com

   To verify ownership and route traffic, add this CNAME record at your DNS
   provider:

   type   CNAME
   name   api
   value  00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

💡 Copy as shown; remove the trailing dot only if your provider rejects it.
   Cloudflare: use DNS only (gray cloud).\
""")


@pytest.mark.respx
def test_domains_add_standard_wizard(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={"name": "api.example.com", "is_using_pre_validation": False},
    ).mock(return_value=Response(201, json=domain))
    keys = ["api.example.com", Keys.ENTER, Keys.ENTER]

    with patch("rich_toolkit.container.getchar", side_effect=keys):
        result = runner.invoke(app, ["domains", "add", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🌐 What domain do you want to add?


🌐 What domain do you want to add?
   api.example.com

🌐 What domain do you want to add? api.example.com

   Is api.example.com already serving traffic?

   ● No — set up a new or unused domain
   ○ Yes — migrate it without downtime

   No — set up a new or unused domain

🐔 Added api.example.com

   To verify ownership and route traffic, add this CNAME record at your DNS
   provider:

   type   CNAME
   name   api
   value  00000000-0000-4000-8000-000000000003.endpoints.fastapicloud.dev.

💡 Copy as shown; remove the trailing dot only if your provider rejects it.
   Cloudflare: use DNS only (gray cloud).\
""")


@pytest.mark.respx
def test_domains_add_zero_downtime_wizard_hides_traffic_records(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain(
        is_using_pre_validation=True,
        dns_records=PREVALIDATION_RECORDS,
    )
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={"name": "api.example.com", "is_using_pre_validation": True},
    ).mock(return_value=Response(201, json=domain))
    keys = ["api.example.com", Keys.ENTER, Keys.DOWN_ARROW, Keys.ENTER]

    with patch("rich_toolkit.container.getchar", side_effect=keys):
        result = runner.invoke(app, ["domains", "add", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🌐 What domain do you want to add?


🌐 What domain do you want to add?
   api.example.com

🌐 What domain do you want to add? api.example.com

   Is api.example.com already serving traffic?

   ● No — set up a new or unused domain
   ○ Yes — migrate it without downtime

   ○ No — set up a new or unused domain
   ● Yes — migrate it without downtime

   Yes — migrate it without downtime

🐔 Added api.example.com

1️⃣ Prove ownership
   Add this TXT record at your DNS provider:

   type   TXT
   name   _fc-dcv.api
   value  ownership-value

2️⃣ Secure your domain

3️⃣ Switch traffic\
""")


@pytest.mark.respx
def test_domains_add_surfaces_duplicate_as_invalid_input(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={"name": "api.example.com", "is_using_pre_validation": False},
    ).mock(
        return_value=Response(
            400,
            json={
                "detail": "A custom domain with this name already exists for the app"
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "add",
            "api.example.com",
            "--standard",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "A custom domain with this name already exists for the app",
            "hint": None,
        }
    }


@pytest.mark.respx
def test_domains_add_surfaces_entitlement_limit(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    message = "Custom domain limit reached (1). Upgrade your plan to add more domains."
    respx_mock.post(
        f"/apps/{APP_ID}/custom-domains",
        json={"name": "api.example.com", "is_using_pre_validation": False},
    ).mock(return_value=Response(403, json={"detail": message}))

    result = runner.invoke(
        app,
        [
            "domains",
            "add",
            "api.example.com",
            "--standard",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "permission_denied",
            "message": message,
            "hint": None,
        }
    }


def test_domains_remove_json_requires_domain(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        ["domains", "remove", "--yes", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Custom domain is required.",
            "hint": "Pass DOMAIN to choose a custom domain.",
        }
    }


def test_domains_remove_json_requires_confirmation(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        ["domains", "remove", "api.example.com", "--app-id", APP_ID, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Removal confirmation is required.",
            "hint": "Pass --yes to confirm removal.",
        }
    }


@pytest.mark.respx
def test_domains_remove_resolves_name_and_returns_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )
    respx_mock.delete(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}").mock(
        return_value=Response(200, json={"message": "Custom domain deleted"})
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "remove",
            "  API.Example.COM. ",
            "--yes",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "domain_id": DOMAIN_ID,
            "name": "api.example.com",
            "removed": True,
        }
    }


@pytest.mark.respx
def test_domains_remove_warns_and_confirms(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )
    respx_mock.delete(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}").mock(
        return_value=Response(200, json={"message": "Custom domain deleted"})
    )

    with patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]):
        result = runner.invoke(
            app,
            ["domains", "remove", domain["name"], "--app-id", APP_ID],
        )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

⚠️ FastAPI Cloud resources for api.example.com will be removed. DNS records at
   your provider will not be changed.

 Remove api.example.com?
 ● Yes  ○ No

 Remove api.example.com? Yes

🐔 Removed api.example.com\
""")


@pytest.mark.respx
def test_domains_remove_can_select_domain(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )
    respx_mock.delete(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}").mock(
        return_value=Response(200, json={"message": "Custom domain deleted"})
    )

    with patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]):
        result = runner.invoke(
            app,
            ["domains", "remove", "--yes", "--app-id", APP_ID],
        )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

 Select the custom domain to remove:
 ● api.example.com

 Select the custom domain to remove: api.example.com

⚠️ FastAPI Cloud resources for api.example.com will be removed. DNS records at
   your provider will not be changed.

🐔 Removed api.example.com\
""")


@pytest.mark.respx
def test_domains_remove_can_be_cancelled(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [domain], "count": 1})
    )

    with patch(
        "rich_toolkit.container.getchar",
        side_effect=[Keys.RIGHT_ARROW, Keys.ENTER],
    ):
        result = runner.invoke(
            app,
            ["domains", "remove", domain["name"], "--app-id", APP_ID],
        )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

⚠️ FastAPI Cloud resources for api.example.com will be removed. DNS records at
   your provider will not be changed.

 Remove api.example.com?
 ● Yes  ○ No

 Remove api.example.com?
 ○ Yes  ● No

 Remove api.example.com? No

 Removal cancelled.\
""")


@pytest.mark.respx
def test_domains_remove_reports_not_found_before_delete(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [custom_domain()], "count": 1})
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "remove",
            "missing.example.com",
            "--yes",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == {
        "code": "not_found",
        "message": "Custom domain missing.example.com not found.",
        "hint": "Run `fastapi cloud domains list` to see available custom domains.",
    }


@pytest.mark.respx
def test_domains_remove_selector_handles_empty_collection(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(
        app,
        ["domains", "remove", "--yes", "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

No custom domains found.\
""")


def test_domains_restart_json_requires_domain(logged_in_cli: None) -> None:
    result = runner.invoke(
        app,
        ["domains", "restart", "--app-id", APP_ID, "--json"],
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
def test_domains_restart_returns_reset_domain_as_json(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    failed_domain = custom_domain(
        status="internal_dcv_timeout",
        setup_in_progress=False,
        setup_failed=True,
    )
    restarted_domain = custom_domain()
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [failed_domain], "count": 1})
    )
    respx_mock.post(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}/restart-setup").mock(
        return_value=Response(200, json=restarted_domain)
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "restart",
            "  API.Example.COM. ",
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {"app_id": APP_ID, "domain": restarted_domain}
    }


@pytest.mark.respx
def test_domains_restart_with_argument_renders_result(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    failed_domain = custom_domain(
        status="internal_dcv_timeout",
        setup_in_progress=False,
        setup_failed=True,
    )
    restarted_domain = custom_domain(dns_records=[])
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [failed_domain], "count": 1})
    )
    respx_mock.post(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}/restart-setup").mock(
        return_value=Response(200, json=restarted_domain)
    )

    result = runner.invoke(
        app,
        ["domains", "restart", failed_domain["name"], "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

🐔 Restarted verification for api.example.com

🌐 api.example.com

⏳ Waiting domain verification
   We are checking your DNS configuration to confirm domain ownership. This
   usually takes a few minutes.

   Add the record below. We'll verify ownership, issue your TLS certificate,
   and route traffic automatically.

   hint: Run `fastapi cloud domains get api.example.com` to check progress.\
""")


@pytest.mark.respx
def test_domains_restart_selector_only_shows_failed_domains(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    live_domain = custom_domain(
        id="00000000-0000-4000-8000-000000000004",
        name="live.example.com",
        status="origin_setup_success",
        setup_in_progress=False,
        setup_successful=True,
    )
    failed_domain = custom_domain(
        name="failed.example.com",
        status="external_dcv_timeout",
        setup_in_progress=False,
        setup_failed=True,
    )
    restarted_domain = custom_domain(
        name="failed.example.com",
        is_using_pre_validation=True,
        dns_records=PREVALIDATION_RECORDS,
    )
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(
            200,
            json={"data": [live_domain, failed_domain], "count": 2},
        )
    )
    respx_mock.post(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}/restart-setup").mock(
        return_value=Response(200, json=restarted_domain)
    )

    with patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]):
        result = runner.invoke(app, ["domains", "restart", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

 Select the custom domain to restart:
 ● failed.example.com

 Select the custom domain to restart: failed.example.com

🐔 Restarted verification for failed.example.com

🌐 failed.example.com

⏳ Waiting domain verification
   We are checking your DNS configuration to confirm domain ownership. This
   usually takes a few minutes.

1️⃣ Prove ownership
   Add this TXT record at your DNS provider:

   type   TXT
   name   _fc-dcv.api
   value  ownership-value

2️⃣ Secure your domain

3️⃣ Switch traffic

   hint: Run `fastapi cloud domains get failed.example.com` to check progress.\
""")


@pytest.mark.respx
def test_domains_restart_selector_handles_no_failed_domains(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    live_domain = custom_domain(
        status="origin_setup_success",
        setup_in_progress=False,
        setup_successful=True,
    )
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [live_domain], "count": 1})
    )

    result = runner.invoke(app, ["domains", "restart", "--app-id", APP_ID])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
custom domains

No failed custom domains found.\
""")


@pytest.mark.respx
def test_domains_restart_reports_not_found(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [custom_domain()], "count": 1})
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "restart",
            "missing.example.com",
            "--app-id",
            APP_ID,
            "--json",
        ],
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
def test_domains_restart_surfaces_backend_rejection_for_live_domain(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    live_domain = custom_domain(
        status="origin_setup_success",
        setup_in_progress=False,
        setup_successful=True,
    )
    message = "The custom domain setup has already been completed successfully"
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        return_value=Response(200, json={"data": [live_domain], "count": 1})
    )
    respx_mock.post(f"/apps/{APP_ID}/custom-domains/{DOMAIN_ID}/restart-setup").mock(
        return_value=Response(400, json={"detail": message})
    )

    result = runner.invoke(
        app,
        [
            "domains",
            "restart",
            live_domain["name"],
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": message,
            "hint": None,
        }
    }


@pytest.mark.respx
def test_domains_list_surfaces_network_errors(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/custom-domains").mock(
        side_effect=ConnectError("Connection failed")
    )

    result = runner.invoke(app, ["domains", "list", "--app-id", APP_ID, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "network_error",
            "message": "Error fetching custom domains. Please try again later.",
            "hint": None,
        }
    }
