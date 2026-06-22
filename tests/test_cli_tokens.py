import json

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()


def test_lists_tokens_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
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


def test_lists_tokens_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(app, ["tokens", "list", "--json"])

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
def test_lists_tokens_as_json_with_app_id_without_secret_values(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token = {
        "id": "00000000-0000-4000-8000-000000000004",
        "name": "GitHub Actions",
        "created_at": "2026-05-22T10:00:00Z",
        "expired_at": "2027-05-22T10:00:00Z",
        "value": "fcp_secret_token_value",
    }
    respx_mock.get(f"/apps/{app_id}/tokens").mock(
        return_value=Response(200, json={"data": [token]})
    )

    result = runner.invoke(app, ["tokens", "list", "--app-id", app_id, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "tokens": [
                {
                    "id": "00000000-0000-4000-8000-000000000004",
                    "name": "GitHub Actions",
                    "created_at": "2026-05-22T10:00:00Z",
                    "expired_at": "2027-05-22T10:00:00Z",
                }
            ],
        }
    }
    assert "fcp_secret_token_value" not in result.stdout
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_tokens_as_json_uses_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    respx_mock.get(f"/apps/{configured_app.app_id}/tokens").mock(
        return_value=Response(200, json={"data": []})
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["tokens", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": configured_app.app_id,
            "tokens": [],
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_lists_tokens_in_human_output_empty(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    respx_mock.get(f"/apps/{app_id}/tokens").mock(
        return_value=Response(200, json={"data": []})
    )

    result = runner.invoke(app, ["tokens", "list", "--app-id", app_id])

    assert result.exit_code == 0
    assert "deploy tokens" in result.output
    assert "No deploy tokens found." in result.output
    assert "Name" not in result.output
    assert "Expiration" not in result.output


@pytest.mark.respx
def test_lists_tokens_human_output_without_secret_values(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token_id = "00000000-0000-4000-8000-000000000004"
    respx_mock.get(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {
                        "id": token_id,
                        "name": "GitHub Actions",
                        "created_at": "2026-05-22T10:00:00Z",
                        "expired_at": "2027-05-22T10:00:00Z",
                        "value": "fcp_secret_token_value",
                    }
                ]
            },
        )
    )

    result = runner.invoke(app, ["tokens", "list", "--app-id", app_id])

    assert result.exit_code == 0
    assert "deploy tokens" in result.output
    assert "Name" in result.output
    assert "Expiration" in result.output
    assert "GitHub Actions" in result.output
    assert "2027-05-22" in result.output
    assert "expires 2027-05-22" not in result.output
    assert token_id in result.output
    assert "fcp_secret_token_value" not in result.output
