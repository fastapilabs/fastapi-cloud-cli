import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import respx
import time_machine
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import SnapshotCliRunner, changing_dir

runner = SnapshotCliRunner()

assets_path = Path(__file__).parent / "assets"


def test_shows_a_message_if_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert "No credentials found." in result.output


def test_shows_a_message_if_app_is_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert "App ID is required." in result.output


def test_list_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["env", "list", "--json"])

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
def test_shows_a_message_if_something_is_wrong(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(500)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 1
    assert (
        "Something went wrong while contacting the FastAPI Cloud server."
        in result.output
    )


@pytest.mark.respx
def test_shows_a_message_if_no_env_variables(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

No environment variables found.\
""")


@pytest.mark.respx
def test_shows_environment_variables_names(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"name": "SECRET_KEY", "value": "123"},
                    {"name": "API_KEY", "value": "456"},
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Key         Value  Last updated

SECRET_KEY  123    -
API_KEY     456    -\
""")


@pytest.mark.respx
def test_lists_environment_variables_as_json_with_app_id(
    logged_in_cli: None, respx_mock: respx.MockRouter
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    variables = [
        {
            "name": "DATABASE_URL",
            "is_secret": True,
            "updated_at": "2026-05-22T10:00:00Z",
        },
        {
            "name": "LOG_LEVEL",
            "value": "info",
            "is_secret": False,
            "updated_at": "2026-05-22T10:00:00Z",
        },
    ]
    respx_mock.get(f"/apps/{app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": variables})
    )

    result = runner.invoke(app, ["env", "list", "--app-id", app_id, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "variables": [
                {
                    "name": "DATABASE_URL",
                    "value": None,
                    "is_secret": True,
                    "updated_at": "2026-05-22T10:00:00Z",
                },
                {
                    "name": "LOG_LEVEL",
                    "value": "info",
                    "is_secret": False,
                    "updated_at": "2026-05-22T10:00:00Z",
                },
            ],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_environment_variables_as_json_with_path(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(200, json={"data": []})
    )

    result = runner.invoke(
        app, ["env", "list", "--path", str(configured_app.path), "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": configured_app.app_id,
            "variables": [],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_shows_environment_variables_in_compact_table(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "APP_URL",
                        "value": "https://fastapicloud.com",
                        "updated_at": "2026-05-10T12:00:00Z",
                    },
                    {
                        "name": "SENTRY_ENVIRONMENT",
                        "value": "production",
                        "updated_at": "2026-03-22T12:00:00Z",
                    },
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Key                 Value                     Last updated

APP_URL             https://fastapicloud.com  12 days ago
SENTRY_ENVIRONMENT  production                2 months ago\
""")


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_truncates_values_and_marks_secrets_in_compact_table(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    long_value = "12345678901234567890123456789012345678901234567890"

    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "LONG_VALUE",
                        "value": long_value,
                        "updated_at": "2026-03-22T12:00:00Z",
                    },
                    {
                        "name": "SECRET_KEY",
                        "is_secret": True,
                        "updated_at": "2026-04-22T12:00:00Z",
                    },
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Key         Value                                     Last updated

LONG_VALUE  1234567890123456789012345678901234567...  2 months ago
SECRET_KEY  [secret]                                  1 month ago\
""")


@pytest.mark.respx
@time_machine.travel(datetime(2026, 8, 13, 12, tzinfo=timezone.utc), tick=False)
def test_shows_secret_environment_variables_without_value(
    logged_in_cli: None, respx_mock: respx.MockRouter, configured_app: ConfiguredApp
) -> None:
    """Test that secret env vars without a value field are handled correctly."""
    respx_mock.get(f"/apps/{configured_app.app_id}/environment-variables/").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "name": "SECRET_KEY",
                        "is_secret": True,
                        "created_at": "2026-01-13T19:01:07.408378Z",
                        "updated_at": "2026-01-13T19:01:07.408389Z",
                        "connected_resource": None,
                    },
                ]
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["env", "list"])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
environment variables

Key         Value     Last updated

SECRET_KEY  [secret]  7 months ago\
""")
