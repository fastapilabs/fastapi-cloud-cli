import json

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()


@pytest.mark.respx
def test_lists_deployments_as_json_with_app_id_and_pagination_params(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
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
    deployment = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": configured_app.app_id,
        "slug": "api-20260522",
        "status": "success",
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
def test_lists_deployments_human_output_shows_id_and_status_only(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
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
    assert "Status" in result.output
    assert "00000000-0000-4000-8000-000000000003  success" in result.output
    assert "Slug" not in result.output
    assert "URL" not in result.output
    assert "api-20260522" not in result.output
    assert "https://api.fastapicloud.app" not in result.output


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
    assert "deployments" in result.output
    assert "No deployments found." in result.output


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
            "hint": "Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
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
            "hint": "Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_gets_deployment_as_json_with_app_id(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(f"/apps/{app_id}/deployments/{deployment['id']}").mock(
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
    deployment = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": configured_app.app_id,
        "slug": "api-20260522",
        "status": "success",
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.fastapicloud.com/acme/apps/api/deployments/api-20260522",
    }
    respx_mock.get(
        f"/apps/{configured_app.app_id}/deployments/{deployment['id']}"
    ).mock(return_value=Response(200, json=deployment))

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
def test_gets_deployment_in_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    deployment = {
        "id": "00000000-0000-4000-8000-000000000003",
        "app_id": app_id,
        "slug": "api-20260522",
        "status": "success",
        "created_at": "2026-05-22T10:00:00Z",
        "url": "https://api.fastapicloud.app",
        "dashboard_url": "https://dashboard.example.com/d/api-20260522",
    }
    respx_mock.get(f"/apps/{app_id}/deployments/{deployment['id']}").mock(
        return_value=Response(200, json=deployment)
    )

    result = runner.invoke(
        app,
        ["deployments", "get", deployment["id"], "--app-id", app_id],
    )

    assert result.exit_code == 0
    assert f"deployment  {deployment['id']}" in result.output
    assert f"app id   {app_id}" in result.output
    assert "slug   api-20260522" in result.output
    assert "status   success" in result.output
    assert "url   https://api.fastapicloud.app" in result.output
    assert "dashboard   https://dashboard.example.com/d/api-20260522" in result.output
    assert "created at" not in result.output
    assert "2026-05-22T10:00:00Z" not in result.output
