import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()


def test_creates_token_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--name",
            "GitHub Actions",
            "--output-file",
            "deploy-token.txt",
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


def test_deletes_token_json_returns_not_logged_in_when_logged_out(
    logged_out_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
            "delete",
            "00000000-0000-4000-8000-000000000004",
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
def test_deletes_token_as_json_with_app_id(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token_id = "00000000-0000-4000-8000-000000000004"
    respx_mock.delete(f"/apps/{app_id}/tokens/{token_id}").mock(
        return_value=Response(204)
    )

    result = runner.invoke(
        app,
        ["tokens", "delete", token_id, "--app-id", app_id, "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "token_id": token_id,
            "deleted": True,
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_deletes_token_as_json_uses_linked_app(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
) -> None:
    token_id = "00000000-0000-4000-8000-000000000004"
    respx_mock.delete(f"/apps/{configured_app.app_id}/tokens/{token_id}").mock(
        return_value=Response(204)
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["tokens", "delete", token_id, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "token_id": token_id,
            "deleted": True,
        }
    }
    assert result.stderr == ""


def test_deletes_token_json_returns_missing_required_input_without_app_context(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
            "delete",
            "00000000-0000-4000-8000-000000000004",
            "--json",
        ],
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
def test_delete_token_json_returns_not_found_when_token_is_missing(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token_id = "00000000-0000-4000-8000-000000000004"
    respx_mock.delete(f"/apps/{app_id}/tokens/{token_id}").mock(
        return_value=Response(404)
    )

    result = runner.invoke(
        app,
        ["tokens", "delete", token_id, "--app-id", app_id, "--json"],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "not_found",
            "message": f"Deploy token {token_id} not found.",
            "hint": "Run `fastapi cloud tokens list` to see available deploy tokens.",
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_delete_token_human_output(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token_id = "00000000-0000-4000-8000-000000000004"
    respx_mock.delete(f"/apps/{app_id}/tokens/{token_id}").mock(
        return_value=Response(204)
    )

    result = runner.invoke(app, ["tokens", "delete", token_id, "--app-id", app_id])

    assert result.exit_code == 0
    assert f"Deleted deploy token {token_id}" in result.output


def test_creates_token_json_returns_missing_required_input_without_name(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--output-file",
            "deploy-token.txt",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Deploy token name is required.",
            "hint": "Pass --name to choose a deploy token name.",
        }
    }
    assert result.stderr == ""


def test_creates_token_json_returns_missing_required_input_without_output_file(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
            "--name",
            "GitHub Actions",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "missing_required_input",
            "message": "Output file is required.",
            "hint": "Pass --output-file to store the deploy token value.",
        }
    }
    assert result.stderr == ""


def test_create_token_requires_output_file_before_prompting_for_name(
    logged_in_cli: None,
) -> None:
    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            "00000000-0000-4000-8000-000000000002",
        ],
    )

    assert result.exit_code == 1
    assert "deploy tokens" in result.output
    assert "Output file is required." in result.output
    assert "Pass --output-file to store the deploy token value." in result.output
    assert "What's the deploy token name?" not in result.output


@pytest.mark.respx
def test_creates_token_as_json_with_app_id_and_writes_value_to_file(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token_id = "00000000-0000-4000-8000-000000000004"
    token_value = "fcp_secret_token_value"
    output_file = tmp_path / "deploy-token"
    respx_mock.post(
        f"/apps/{app_id}/tokens",
        json={"name": "GitHub Actions", "expires_in_days": 365},
    ).mock(
        return_value=Response(
            201,
            json={
                "id": token_id,
                "name": "GitHub Actions",
                "expired_at": "2027-05-22T10:00:00Z",
                "value": token_value,
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            app_id,
            "--name",
            "GitHub Actions",
            "--output-file",
            str(output_file),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": app_id,
            "token": {
                "id": token_id,
                "name": "GitHub Actions",
                "expired_at": "2027-05-22T10:00:00Z",
            },
            "stored_secret": {
                "provider": "file",
                "path": str(output_file),
            },
        }
    }
    assert token_value not in result.stdout
    assert output_file.read_text(encoding="utf-8") == token_value
    assert result.stderr == ""


@pytest.mark.respx
def test_creates_token_uses_linked_app_and_custom_expiration(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    configured_app: ConfiguredApp,
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "deploy-token"
    respx_mock.post(
        f"/apps/{configured_app.app_id}/tokens",
        json={"name": "Release Bot", "expires_in_days": 30},
    ).mock(
        return_value=Response(
            201,
            json={
                "id": "00000000-0000-4000-8000-000000000004",
                "name": "Release Bot",
                "expired_at": "2026-06-21T10:00:00Z",
                "value": "fcp_secret_token_value",
            },
        )
    )

    with changing_dir(configured_app.path):
        result = runner.invoke(
            app,
            [
                "tokens",
                "create",
                "--name",
                "Release Bot",
                "--expires-in-days",
                "30",
                "--output-file",
                str(output_file),
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["app_id"] == configured_app.app_id
    assert output_file.read_text(encoding="utf-8") == "fcp_secret_token_value"
    assert result.stderr == ""


@pytest.mark.respx
def test_create_token_prompts_for_name_under_deploy_tokens_heading(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    output_file = tmp_path / "deploy-token"
    respx_mock.post(
        f"/apps/{app_id}/tokens",
        json={"name": "GitHub Actions", "expires_in_days": 365},
    ).mock(
        return_value=Response(
            201,
            json={
                "id": "00000000-0000-4000-8000-000000000004",
                "name": "GitHub Actions",
                "expired_at": "2027-05-22T10:00:00Z",
                "value": "fcp_secret_token_value",
            },
        )
    )

    with patch(
        "rich_toolkit.container.getchar",
        side_effect=[*"GitHub Actions", Keys.ENTER],
    ):
        result = runner.invoke(
            app,
            [
                "tokens",
                "create",
                "--app-id",
                app_id,
                "--output-file",
                str(output_file),
            ],
        )

    assert result.exit_code == 0
    assert "deploy tokens" in result.output
    assert "What's the deploy token name?" in result.output
    assert "Created deploy token GitHub Actions" in result.output
    assert output_file.read_text(encoding="utf-8") == "fcp_secret_token_value"


@pytest.mark.respx
def test_create_token_separates_prompt_from_http_error(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    output_file = tmp_path / "deploy-token"
    respx_mock.post(
        f"/apps/{app_id}/tokens",
        json={"name": "GitHub Actions", "expires_in_days": 365},
    ).mock(
        return_value=Response(
            409,
            json={"detail": "Deploy token name already exists."},
        )
    )

    with patch(
        "rich_toolkit.container.getchar",
        side_effect=[*"GitHub Actions", Keys.ENTER],
    ):
        result = runner.invoke(
            app,
            [
                "tokens",
                "create",
                "--app-id",
                app_id,
                "--output-file",
                str(output_file),
            ],
        )

    assert result.exit_code == 1
    assert "What's the deploy token name?" in result.output
    assert "Deploy token name already exists." in result.output
    lines = result.output.splitlines()
    error_index = next(
        index
        for index, line in enumerate(lines)
        if "Deploy token name already exists." in line
    )
    assert lines[error_index - 1].replace("\u200b", "").strip() == ""
    assert not output_file.exists()


@pytest.mark.respx
def test_create_token_human_output_does_not_print_token_value(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    token_value = "fcp_secret_token_value"
    output_file = tmp_path / "deploy-token"
    respx_mock.post(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            201,
            json={
                "id": "00000000-0000-4000-8000-000000000004",
                "name": "GitHub Actions",
                "expired_at": "2027-05-22T10:00:00Z",
                "value": token_value,
            },
        )
    )

    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            app_id,
            "--name",
            "GitHub Actions",
            "--output-file",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    assert "deploy tokens" in result.output
    assert "Created deploy token GitHub Actions" in result.output
    assert "Stored deploy token value in" in result.output
    assert output_file.name in result.output
    assert token_value not in result.output
    assert output_file.read_text(encoding="utf-8") == token_value


@pytest.mark.respx
def test_create_token_json_maps_duplicate_name_to_invalid_input(
    logged_in_cli: None,
    respx_mock: respx.MockRouter,
    tmp_path: Path,
) -> None:
    app_id = "00000000-0000-4000-8000-000000000002"
    output_file = tmp_path / "deploy-token"
    respx_mock.post(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            409,
            json={"detail": "Deploy token name already exists."},
        )
    )

    result = runner.invoke(
        app,
        [
            "tokens",
            "create",
            "--app-id",
            app_id,
            "--name",
            "GitHub Actions",
            "--output-file",
            str(output_file),
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Deploy token name already exists.",
            "hint": None,
        }
    }
    assert not output_file.exists()
    assert result.stderr == ""


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
