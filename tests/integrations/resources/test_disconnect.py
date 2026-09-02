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

APP_ID = "00000000-0000-4000-8000-000000000001"
LINKED_APP_ID = "00000000-0000-4000-8000-000000000002"
TEAM_ID = "00000000-0000-4000-8000-000000000003"
RESOURCE_ID = "00000000-0000-4000-8000-000000000004"
SECOND_RESOURCE_ID = "00000000-0000-4000-8000-000000000005"
INTEGRATION_ID = "00000000-0000-4000-8000-000000000006"


def _resource_summary(
    *,
    resource_id: str = RESOURCE_ID,
    name: str = "production",
    provider: str = "neon",
) -> dict[str, object]:
    return {
        "id": resource_id,
        "name": name,
        "app_id": APP_ID,
        "integration_id": INTEGRATION_ID,
        "provider_metadata": {
            "type": provider,
            "database_name": "app_db",
        },
        "console_url": "https://provider.example/resource",
        "created_at": "2026-08-18T10:00:00Z",
        "updated_at": "2026-08-19T11:00:00Z",
    }


def _resource_detail() -> dict[str, object]:
    return {
        **_resource_summary(),
        "provider_metadata": {
            "type": "neon",
            "project_id": "project-id",
            "branch_id": "branch-id",
            "database_name": "app_db",
        },
        "environment_variables": [
            {"name": "DATABASE_URL"},
            {"name": "DATABASE_PASSWORD"},
        ],
    }


def test_disconnect_resource_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "integrations",
            "resources",
            "disconnect",
            RESOURCE_ID,
            "--app-id",
            APP_ID,
            "--yes",
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


def test_disconnect_resource_json_requires_resource_id(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "integrations",
            "resources",
            "disconnect",
            "--app-id",
            APP_ID,
            "--yes",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Resource ID is required.",
            "hint": "Pass RESOURCE_ID to choose a connected resource.",
        }
    }
    assert result.stderr == ""


def test_disconnect_resource_json_requires_confirmation(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "integrations",
            "resources",
            "disconnect",
            RESOURCE_ID,
            "--app-id",
            APP_ID,
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Disconnection confirmation is required.",
            "hint": "Pass --yes to confirm disconnection.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_disconnect_resource_as_json_with_explicit_app_overriding_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    write_app_config(
        tmp_path,
        AppConfig(app_id=LINKED_APP_ID, team_id=TEAM_ID),
    )
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(200, json=_resource_detail())
    )
    respx_mock.delete(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(204)
    )

    with changing_dir(tmp_path):
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "disconnect",
                RESOURCE_ID,
                "--app-id",
                APP_ID,
                "--yes",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": APP_ID,
            "resource_id": RESOURCE_ID,
            "disconnected": True,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_disconnect_resource_allows_interactive_selection(
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
            json={
                "data": [
                    _resource_summary(),
                    _resource_summary(
                        resource_id=SECOND_RESOURCE_ID,
                        name="cache",
                        provider="redis",
                    ),
                ],
                "count": 2,
            },
        )
    )
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(200, json=_resource_detail())
    )
    respx_mock.delete(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(204)
    )

    with (
        changing_dir(tmp_path),
        patch(
            "rich_toolkit.container.getchar",
            side_effect=[Keys.ENTER, Keys.ENTER],
        ),
    ):
        result = runner.invoke(app, ["integrations", "resources", "disconnect"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
disconnect resource

 Select the resource to disconnect:
 ● production (Neon)
 ○ cache (Redis Cloud)

 Select the resource to disconnect: production (Neon)

💡 The managed environment variables DATABASE_URL, DATABASE_PASSWORD will be
   removed from the app. The Neon resource itself will not be deleted.

 Disconnect production?
 ● Yes  ○ No

 Disconnect production? Yes

🔌 Disconnected production from the app.

   Removed managed environment variables: DATABASE_URL, DATABASE_PASSWORD.\
""")


@pytest.mark.respx
def test_disconnect_resource_prompts_for_confirmation_when_id_is_provided(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(
            200,
            json={**_resource_detail(), "environment_variables": []},
        )
    )
    respx_mock.delete(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(204)
    )

    with patch("rich_toolkit.container.getchar", side_effect=[Keys.ENTER]):
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "disconnect",
                RESOURCE_ID,
                "--app-id",
                APP_ID,
            ],
        )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
disconnect resource

💡 Managed environment variables will be removed from the app. The Neon
   resource itself will not be deleted.

 Disconnect production?
 ● Yes  ○ No

 Disconnect production? Yes

🔌 Disconnected production from the app.\
""")


@pytest.mark.respx
def test_disconnect_resource_can_be_cancelled(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources/{RESOURCE_ID}").mock(
        return_value=Response(200, json=_resource_detail())
    )

    with patch(
        "rich_toolkit.container.getchar",
        side_effect=[Keys.RIGHT_ARROW, Keys.ENTER],
    ):
        result = runner.invoke(
            app,
            [
                "integrations",
                "resources",
                "disconnect",
                RESOURCE_ID,
                "--app-id",
                APP_ID,
            ],
        )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
disconnect resource

💡 The managed environment variables DATABASE_URL, DATABASE_PASSWORD will be
   removed from the app. The Neon resource itself will not be deleted.

 Disconnect production?
 ● Yes  ○ No

 Disconnect production?
 ○ Yes  ● No

 Disconnect production? No

 Disconnection cancelled.\
""")


@pytest.mark.respx
def test_disconnect_resource_selector_handles_empty_list(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"/apps/{APP_ID}/connected-resources").mock(
        return_value=Response(200, json={"data": [], "count": 0})
    )

    result = runner.invoke(
        app,
        ["integrations", "resources", "disconnect", "--app-id", APP_ID],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
disconnect resource

No connected resources found.\
""")


@pytest.mark.respx
def test_disconnect_resource_json_returns_not_found(
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
            "disconnect",
            RESOURCE_ID,
            "--app-id",
            APP_ID,
            "--yes",
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
