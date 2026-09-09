import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx
import time_machine
from httpx import Response
from inline_snapshot import snapshot

from fastapi_cloud_cli.api import StreamLogError, TooManyRetriesError
from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import SnapshotCliRunner, build_logs_response, changing_dir

runner = SnapshotCliRunner()


@pytest.fixture
def build_logs_deployment(respx_mock: respx.MockRouter) -> dict[str, Any]:
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": "00000000-0000-4000-8000-000000000002",
        "slug": "api-build",
        "status": "building_image",
        "created_at": "2026-05-22T10:00:00Z",
        "failure": None,
    }
    respx_mock.get(f"/deployments/{deployment['id']}").mock(
        side_effect=lambda request: Response(200, json=deployment)
    )
    return deployment


@pytest.mark.respx
def test_lists_deployments_as_json_with_app_id_and_pagination_params(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
        "failure": None,
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(
        f"/apps/{app_id}/deployments/",
        params={"limit": "100", "skip": "20"},
    ).mock(return_value=Response(200, json={"data": [deployment], "count": 1}))

    result = runner.invoke(
        app,
        [
            "deployments",
            "list",
            "--app-id",
            app_id,
            "--limit",
            "100",
            "--offset",
            "20",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "deployments": [deployment],
            "total_count": 1,
            "limit": 100,
            "offset": 20,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_deployments_as_json_uses_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": configured_app.app_id,
        "slug": "api-20260522",
        "status": "success",
        "failure": None,
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(
        f"/apps/{configured_app.app_id}/deployments/",
        params={"limit": "100", "skip": "0"},
    ).mock(return_value=Response(200, json={"data": [deployment], "count": 1}))

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["deployments", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "deployments": [deployment],
            "total_count": 1,
            "limit": 100,
            "offset": 0,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_lists_deployments_human_output_shows_id_status_and_created(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
        "failure": None,
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(
        f"/apps/{app_id}/deployments/",
        params={"limit": "100", "skip": "0"},
    ).mock(return_value=Response(200, json={"data": [deployment], "count": 1}))

    result = runner.invoke(app, ["deployments", "list", "--app-id", app_id])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
deployments

ID                                    Status   Created

00000000-0000-4000-8000-000000000003  success  2 hours ago\
""")


@pytest.mark.respx
def test_lists_deployments_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(
        f"/apps/{app_id}/deployments/",
        params={"limit": "100", "skip": "0"},
    ).mock(return_value=Response(200, json={"data": [], "count": 0}))

    result = runner.invoke(app, ["deployments", "list", "--app-id", app_id])

    assert result.exit_code == 0
    assert result.output == snapshot("""\
deployments

No deployments found.\
""")


def test_lists_deployments_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "deployments",
            "list",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
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


def test_lists_deployments_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["deployments", "list", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "App ID is required.",
            "hint": "Pass --app-id or run `fastapi cloud apps create --link` first.",
        }
    }
    assert result.stderr == ""


def test_gets_deployment_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "deployments",
            "get",
            "00000000-0000-4000-8000-000000000003",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
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
def test_gets_deployment_as_json_with_app_id(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
        "failure": None,
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(f"/deployments/{deployment['id']}").mock(
        return_value=Response(200, json=deployment)
    )

    result = runner.invoke(
        app,
        [
            "deployments",
            "get",
            deployment["id"],
            "--app-id",
            app_id,
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"deployment": deployment}}
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_deployment_as_json_uses_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": configured_app.app_id,
        "slug": "api-20260522",
        "status": "success",
        "failure": None,
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(f"/deployments/{deployment['id']}").mock(
        return_value=Response(200, json=deployment)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["deployments", "get", deployment["id"], "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"data": {"deployment": deployment}}
    assert result.stderr == ""


def test_gets_deployment_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        ["deployments", "get", "00000000-0000-4000-8000-000000000003", "--json"],
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
@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
def test_gets_deployment_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
        "failure": None,
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.example.com/d/api-20260522",
    }
    respx_mock.get(f"/deployments/{deployment['id']}").mock(
        return_value=Response(200, json=deployment)
    )

    result = runner.invoke(
        app,
        ["deployments", "get", deployment["id"], "--app-id", app_id],
    )

    assert result.exit_code == 0
    assert result.output == snapshot("""\
deployment

🚀 00000000-0000-4000-8000-000000000003

   app id     00000000-0000-4000-8000-000000000002
   slug       api-20260522
   status     success
   created    2 hours ago
   url        https://api.fastapicloud.app
   dashboard  https://dashboard.example.com/d/api-20260522\
""")


@pytest.mark.respx
def test_gets_build_logs_no_follow_as_json(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {
                    "type": "message",
                    "id": "1748682000001-0",
                    "message": "Building image",
                },
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--no-follow", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "deployment_id": deployment_id,
            "failure": None,
            "failed": False,
            "logs": [
                {
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {
                    "id": "1748682000001-0",
                    "message": "Building image",
                },
            ],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_failed_build_logs_no_follow_as_json_exits_nonzero(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "failed", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--no-follow", "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "data": {
            "deployment_id": deployment_id,
            "failure": None,
            "failed": True,
            "logs": [
                {
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
            ],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_build_logs_no_follow_in_human_output(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "complete", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--no-follow"],
    )

    assert result.exit_code == 0
    assert "Fetching build logs" in result.output
    assert "Installing dependencies" in result.output


@pytest.mark.respx
def test_gets_build_logs_no_follow_in_human_output_empty(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(200, content="")
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--no-follow"],
    )

    assert result.exit_code == 0
    assert "No build logs found." in result.output


@pytest.mark.respx
def test_gets_failed_build_logs_no_follow_in_human_output_exits_nonzero(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "failed", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--no-follow"],
    )

    assert result.exit_code == 1
    assert "Installing dependencies" in result.output
    assert "Build failed." in result.output


@pytest.mark.respx
def test_streams_build_logs_in_human_output(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "complete", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id],
    )

    assert result.exit_code == 0
    assert "Streaming build logs" in result.output
    assert "Installing dependencies" in result.output


@pytest.mark.respx
def test_streams_failed_build_logs_in_human_output_exits_nonzero(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "failed", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id],
    )

    assert result.exit_code == 1
    assert "Installing dependencies" in result.output
    assert "Build failed." in result.output


@pytest.mark.respx
def test_streams_build_logs_as_json_ndjson(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "complete", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--json"],
    )

    assert result.exit_code == 0
    assert [json.loads(line) for line in result.stdout.splitlines()] == [
        {
            "type": "log",
            "deployment_id": deployment_id,
            "id": "1748682000000-0",
            "message": "Installing dependencies",
        },
        {
            "type": "complete",
            "deployment_id": deployment_id,
            "id": "1748682000001-0",
        },
    ]
    assert result.stderr == ""


def test_build_logs_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "deployments",
            "build-logs",
            "00000000-0000-4000-8000-000000000003",
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


def test_streaming_build_logs_handles_keyboard_interrupt(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"

    with patch(
        "fastapi_cloud_cli.api.APIClient.stream_build_logs",
        side_effect=KeyboardInterrupt,
    ):
        result = runner.invoke(
            app,
            ["deployments", "build-logs", deployment_id],
        )

    assert result.exit_code == 0


def test_build_logs_handles_not_found_stream_error(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"

    with patch(
        "fastapi_cloud_cli.api.APIClient.stream_build_logs",
        side_effect=StreamLogError("not found", status_code=404),
    ):
        result = runner.invoke(
            app,
            ["deployments", "build-logs", deployment_id],
        )

    assert result.exit_code == 1
    assert "Deployment not found." in result.output


def test_build_logs_handles_http_stream_error_with_hint(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"

    def raise_stream_error(*args: object, **kwargs: object) -> None:
        request = httpx.Request("GET", "https://api.example.test/build-logs")
        response = httpx.Response(401, request=request)
        error = httpx.HTTPStatusError(
            "Unauthorized", request=request, response=response
        )

        try:
            raise error
        except httpx.HTTPStatusError as exc:
            raise StreamLogError("HTTP 401") from exc

    with patch(
        "fastapi_cloud_cli.api.APIClient.stream_build_logs",
        side_effect=raise_stream_error,
    ):
        result = runner.invoke(
            app,
            ["deployments", "build-logs", deployment_id],
        )

    assert result.exit_code == 1
    assert "token is not valid" in result.output
    assert "fastapi cloud login" in result.output


def test_build_logs_handles_generic_stream_error(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"

    with patch(
        "fastapi_cloud_cli.api.APIClient.stream_build_logs",
        side_effect=StreamLogError("Log storage unavailable"),
    ):
        result = runner.invoke(
            app,
            ["deployments", "build-logs", deployment_id],
        )

    assert result.exit_code == 1
    assert "Error streaming build logs: Log storage unavailable" in result.output


def test_build_logs_handles_connection_loss(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"

    with patch(
        "fastapi_cloud_cli.api.APIClient.stream_build_logs",
        side_effect=TooManyRetriesError("Connection lost"),
    ):
        result = runner.invoke(
            app,
            ["deployments", "build-logs", deployment_id],
        )

    assert result.exit_code == 1
    assert "Lost connection to build log stream" in result.output
    assert "Please try again later." in result.output


@pytest.mark.respx
def test_streams_failed_build_logs_as_json_ndjson_exits_nonzero(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").mock(
        return_value=Response(
            200,
            content=build_logs_response(
                {
                    "type": "message",
                    "id": "1748682000000-0",
                    "message": "Installing dependencies",
                },
                {"type": "failed", "id": "1748682000001-0"},
            ),
        )
    )

    result = runner.invoke(
        app,
        ["deployments", "build-logs", deployment_id, "--json"],
    )

    assert result.exit_code == 1
    assert [json.loads(line) for line in result.stdout.splitlines()] == [
        {
            "type": "log",
            "deployment_id": deployment_id,
            "id": "1748682000000-0",
            "message": "Installing dependencies",
        },
        {
            "type": "failed",
            "deployment_id": deployment_id,
            "id": "1748682000001-0",
        },
    ]
    assert result.stderr == ""


@pytest.mark.respx
@pytest.mark.parametrize("follow_option", ["--follow", "--no-follow"])
def test_shows_build_failure_diagnostic_in_human_output(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
    follow_option: str,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    build_logs_deployment.update(
        status="building_image_failed",
        failure={
            "error_code": "uv_lockfile_outdated",
            "error_title": "Your lockfile is out of date",
            "error_message": "The lockfile does not match your project dependencies.",
            "error_hint": "Run `uv lock` and commit the updated lockfile.",
        },
    )
    if follow_option == "--follow":
        respx_mock.get(f"/deployments/{deployment_id}").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        **build_logs_deployment,
                        "status": "building_image",
                        "failure": None,
                    },
                ),
                Response(200, json=build_logs_deployment),
            ]
        )
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").respond(
        200,
        content=build_logs_response(
            {"type": "message", "id": "1", "message": "Installing dependencies"},
            {"type": "message", "id": "2", "message": "\n"},
            {"type": "message", "id": "3", "message": "Cleaning up..."},
            {"type": "failed", "id": "4"},
        ),
    )

    result = runner.invoke(
        app, ["deployments", "build-logs", deployment_id, follow_option]
    )

    assert result.exit_code == 1
    if follow_option == "--no-follow":
        assert result.output == snapshot("""\
📜 Fetching build logs for 00000000-0000-4000-8000-000000000003...

▕  Installing dependencies
▕
▕  Cleaning up...

🚨 This deployment failed with the following error:

   Your lockfile is out of date

   The lockfile does not match your project dependencies.

   hint: Run `uv lock` and commit the updated lockfile.\
""")
    else:
        assert result.output == snapshot("""\
📡 Streaming build logs for 00000000-0000-4000-8000-000000000003...

▕  Installing dependencies
▕
▕  Cleaning up...

🚨 This deployment failed with the following error:

   Your lockfile is out of date

   The lockfile does not match your project dependencies.

   hint: Run `uv lock` and commit the updated lockfile.\
""")


@pytest.mark.respx
def test_gets_build_failure_diagnostic_without_logs_or_hint(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    build_logs_deployment.update(
        status="building_image_failed",
        failure={
            "error_code": "future_build_error",
            "error_title": "Cannot install project[dev]",
            "error_message": "The dependency project[dev] could not be installed.",
            "error_hint": "",
        },
    )
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").respond(
        200,
        content=build_logs_response({"type": "timeout"}),
    )

    result = runner.invoke(
        app, ["deployments", "build-logs", deployment_id, "--no-follow"]
    )

    assert result.exit_code == 1
    assert result.output == snapshot("""\
📜 Fetching build logs for 00000000-0000-4000-8000-000000000003...

🚨 This deployment failed with the following error:

   Cannot install project[dev]

   The dependency project[dev] could not be installed.\
""")


@pytest.mark.respx
@pytest.mark.parametrize("hint", ["Run `uv lock` and commit the updated lockfile.", ""])
def test_streams_build_failure_diagnostic_as_json(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
    hint: str,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    failure = {
        "error_code": "uv_lockfile_outdated",
        "error_title": "Your lockfile is out of date",
        "error_message": "The lockfile does not match your project dependencies.",
        "error_hint": hint,
    }
    build_logs_deployment.update(status="building_image_failed", failure=failure)
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").respond(
        200,
        content=build_logs_response(
            {
                "type": "message",
                "id": "0",
                "message": "Error: Building and pushing the app image failed.\n",
            },
            {"type": "message", "id": "2", "message": "Cleaning up..."},
            {"type": "failed", "id": "3"},
        ),
    )

    result = runner.invoke(app, ["deployments", "build-logs", deployment_id, "--json"])

    assert result.exit_code == 1
    assert [json.loads(line) for line in result.stdout.splitlines()] == [
        {
            "type": "log",
            "deployment_id": deployment_id,
            "id": "0",
            "message": "Error: Building and pushing the app image failed.\n",
        },
        {
            "type": "log",
            "deployment_id": deployment_id,
            "id": "2",
            "message": "Cleaning up...",
        },
        {
            "type": "failed",
            "deployment_id": deployment_id,
            "id": "3",
            "failure": failure,
        },
    ]
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_build_failure_diagnostic_as_json(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    failure = {
        "error_code": "uv_lockfile_outdated",
        "error_title": "Your lockfile is out of date",
        "error_message": "The lockfile does not match your project dependencies.",
        "error_hint": "Run `uv lock` and commit the updated lockfile.",
    }
    build_logs_deployment.update(status="building_image_failed", failure=failure)
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").respond(
        200,
        content=build_logs_response(
            {
                "type": "message",
                "id": "0",
                "message": "Error: Building and pushing the app image failed.\n",
            },
            {"type": "failed", "id": "2"},
        ),
    )

    result = runner.invoke(
        app, ["deployments", "build-logs", deployment_id, "--no-follow", "--json"]
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "data": {
            "deployment_id": deployment_id,
            "failed": True,
            "logs": [
                {
                    "id": "0",
                    "message": "Error: Building and pushing the app image failed.\n",
                },
            ],
            "failure": failure,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
@pytest.mark.parametrize("follow_option", ["--follow", "--no-follow"])
def test_generic_build_failure_without_logs(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
    follow_option: str,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").respond(
        200,
        content=build_logs_response(
            {
                "type": "message",
                "id": "0",
                "message": "Error: Building and pushing the app image failed.\n",
            },
            {"type": "failed", "id": "1"},
        ),
    )

    result = runner.invoke(
        app, ["deployments", "build-logs", deployment_id, follow_option]
    )

    assert result.exit_code == 1
    assert "Build failed." in result.output
    assert "Error: Building and pushing the app image failed." in result.output
    assert "No build logs found." not in result.output


@pytest.mark.respx
@pytest.mark.parametrize("follow_option", ["--follow", "--no-follow"])
def test_build_logs_shows_persisted_failure_after_logs_expire(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
    follow_option: str,
) -> None:
    deployment_id = build_logs_deployment["id"]
    failure = {
        "error_code": "uv_lockfile_outdated",
        "error_title": "Your lockfile is out of date",
        "error_message": "The lockfile does not match your project dependencies.",
        "error_hint": "Run `uv lock` and commit the updated lockfile.",
    }
    build_logs_deployment.update(status="building_image_failed", failure=failure)
    respx_mock.get(f"/deployments/{deployment_id}/build-logs", params__eq={}).respond(
        200, content=build_logs_response({"type": "timeout"})
    )

    result = runner.invoke(
        app, ["deployments", "build-logs", deployment_id, follow_option]
    )

    assert result.exit_code == 1
    assert failure["error_title"] in result.output
    assert failure["error_message"] in result.output
    assert failure["error_hint"] in result.output
    assert "No build logs found." not in result.output


@pytest.mark.respx
@pytest.mark.parametrize("follow_option", ["--follow", "--no-follow"])
def test_build_logs_does_not_report_readiness_failure_as_build_failure(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
    respx_mock: respx.MockRouter,
    follow_option: str,
) -> None:
    deployment_id = build_logs_deployment["id"]
    build_logs_deployment["status"] = "verifying_failed"
    respx_mock.get(f"/deployments/{deployment_id}/build-logs").respond(
        200, content=build_logs_response({"type": "complete", "id": "1"})
    )

    result = runner.invoke(
        app, ["deployments", "build-logs", deployment_id, follow_option]
    )

    assert result.exit_code == 0
    assert "Build failed" not in result.output


@pytest.mark.respx
def test_get_deployment_includes_persisted_failure_in_json(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    failure = {
        "error_code": "uv_lockfile_outdated",
        "error_title": "Your lockfile is out of date",
        "error_message": "The lockfile does not match your project dependencies.",
        "error_hint": "Run `uv lock` and commit the updated lockfile.",
    }
    build_logs_deployment.update(status="building_image_failed", failure=failure)

    result = runner.invoke(
        app,
        [
            "deployments",
            "get",
            build_logs_deployment["id"],
            "--app-id",
            build_logs_deployment["app_id"],
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["deployment"]["failure"] == failure


@pytest.mark.respx
def test_get_deployment_shows_persisted_failure(
    logged_in_cli: None,
    build_logs_deployment: dict[str, Any],
) -> None:
    failure = {
        "error_code": "uv_lockfile_outdated",
        "error_title": "Your lockfile is out of date",
        "error_message": "The lockfile does not match your project dependencies.",
        "error_hint": "Run `uv lock` and commit the updated lockfile.",
    }
    build_logs_deployment.update(status="building_image_failed", failure=failure)

    result = runner.invoke(
        app,
        [
            "deployments",
            "get",
            build_logs_deployment["id"],
            "--app-id",
            build_logs_deployment["app_id"],
        ],
    )

    assert result.exit_code == 0
    assert failure["error_title"] in result.output
    assert failure["error_message"] in result.output
    assert failure["error_hint"] in result.output


@pytest.mark.respx
def test_build_logs_handles_deployment_lookup_error(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    deployment_id = "00000000-0000-4000-8000-000000000003"
    respx_mock.get(f"/deployments/{deployment_id}").respond(404)

    result = runner.invoke(app, ["deployments", "build-logs", deployment_id, "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["message"] == "Deployment not found."
