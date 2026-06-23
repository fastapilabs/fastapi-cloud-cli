import json
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.setup_ci import _get_workflow_content
from tests.conftest import ConfiguredApp
from tests.utils import changing_dir

runner = CliRunner()

GITHUB_ORIGIN = "git@github.com:owner/repo.git"


def _mock_token_api(
    respx_mock: respx.MockRouter,
    app_id: str,
    *,
    token_value: str = "test-token",
) -> None:
    respx_mock.post(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            201,
            json={"value": token_value, "expired_at": "2027-05-22T10:00:00Z"},
        )
    )


def test_print_workflow_uses_default_branch() -> None:
    with patch(
        "fastapi_cloud_cli.commands.ci.print_workflow._get_default_branch",
        return_value="develop",
    ):
        result = runner.invoke(app, ["ci", "print-workflow"])

    assert result.exit_code == 0
    assert result.stdout == _get_workflow_content("develop")
    assert result.stderr == ""


def test_print_workflow_uses_branch_option() -> None:
    result = runner.invoke(app, ["ci", "print-workflow", "--branch", "main"])

    assert result.exit_code == 0
    assert result.stdout == _get_workflow_content("main")
    assert result.stderr == ""


def test_print_workflow_json_outputs_envelope() -> None:
    result = runner.invoke(app, ["ci", "print-workflow", "--branch", "main", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "filename": "deploy.yml",
            "content": _get_workflow_content("main"),
        }
    }
    assert result.stderr == ""


@pytest.mark.respx
def test_ci_setup_json_outputs_envelope(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(
        respx_mock,
        configured_app.app_id,
        token_value="secret-token-value",
    )

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret") as mock_secret,
    ):
        result = runner.invoke(
            app,
            [
                "ci",
                "setup",
                "--app-id",
                configured_app.app_id,
                "--branch",
                "main",
                "--file",
                "deploy.yml",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": configured_app.app_id,
            "repo": "owner/repo",
            "branch": "main",
            "workflow_path": ".github/workflows/deploy.yml",
            "created_token": True,
            "set_github_secrets": True,
            "wrote_workflow": True,
            "token_expired_at": "2027-05-22T10:00:00Z",
        }
    }
    assert "secret-token-value" not in result.stdout
    assert result.stderr == ""
    mock_secret.assert_any_call("FASTAPI_CLOUD_TOKEN", "secret-token-value")
    mock_secret.assert_any_call("FASTAPI_CLOUD_APP_ID", configured_app.app_id)
    assert (configured_app.path / ".github" / "workflows" / "deploy.yml").exists()


def test_ci_setup_json_returns_dependency_missing_when_gh_is_missing(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=False,
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._create_token") as mock_create_token,
    ):
        result = runner.invoke(
            app,
            [
                "ci",
                "setup",
                "--app-id",
                configured_app.app_id,
                "--branch",
                "main",
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "dependency_missing",
            "message": "GitHub CLI (`gh`) is required to set GitHub Actions secrets.",
            "hint": "Install gh or use --workflow-only to write only the workflow file.",
        }
    }
    assert result.stderr == ""
    mock_create_token.assert_not_called()


def test_ci_setup_workflow_only_skips_token_and_secret_creation(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._create_token") as mock_create_token,
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret") as mock_secret,
    ):
        result = runner.invoke(
            app,
            [
                "ci",
                "setup",
                "--app-id",
                configured_app.app_id,
                "--branch",
                "main",
                "--workflow-only",
                "--json",
            ],
        )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "data": {
            "app_id": configured_app.app_id,
            "repo": "owner/repo",
            "branch": "main",
            "workflow_path": ".github/workflows/deploy.yml",
            "created_token": False,
            "set_github_secrets": False,
            "wrote_workflow": True,
            "token_expired_at": None,
        }
    }
    assert result.stderr == ""
    mock_create_token.assert_not_called()
    mock_secret.assert_not_called()
    workflow_file = configured_app.path / ".github" / "workflows" / "deploy.yml"
    assert workflow_file.read_text() == _get_workflow_content("main")


def test_ci_setup_json_existing_workflow_fails_without_prompt(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
) -> None:
    workflow_file = configured_app.path / ".github" / "workflows" / "deploy.yml"
    workflow_file.parent.mkdir(parents=True)
    workflow_file.write_text("old content")

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITHUB_ORIGIN,
        ),
    ):
        result = runner.invoke(
            app,
            [
                "ci",
                "setup",
                "--app-id",
                configured_app.app_id,
                "--branch",
                "main",
                "--workflow-only",
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Workflow file .github/workflows/deploy.yml already exists.",
            "hint": "Pass --file to choose another workflow file or remove the existing file.",
        }
    }
    assert workflow_file.read_text() == "old content"


def test_ci_setup_json_existing_workflow_fails_before_side_effects(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
) -> None:
    workflow_file = configured_app.path / ".github" / "workflows" / "deploy.yml"
    workflow_file.parent.mkdir(parents=True)
    workflow_file.write_text("old content")

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._create_token") as mock_create_token,
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret") as mock_secret,
    ):
        result = runner.invoke(
            app,
            [
                "ci",
                "setup",
                "--app-id",
                configured_app.app_id,
                "--branch",
                "main",
                "--json",
            ],
        )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": {
            "code": "invalid_input",
            "message": "Workflow file .github/workflows/deploy.yml already exists.",
            "hint": "Pass --file to choose another workflow file or remove the existing file.",
        }
    }
    assert workflow_file.read_text() == "old content"
    mock_create_token.assert_not_called()
    mock_secret.assert_not_called()
