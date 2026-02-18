import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.config import Settings
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()
settings = Settings.get()

GITHUB_ORIGIN = "git@github.com:owner/repo.git"
GITLAB_ORIGIN = "git@gitlab.com:owner/repo.git"


def _mock_subprocess_run(
    *,
    origin: str = GITHUB_ORIGIN,
    gh_installed: bool = True,
    default_branch: str = "main",
    gh_view_error: bool = False,
    gh_secret_error: bool = False,
):
    """Create a side_effect for setup_ci.subprocess.run."""

    def side_effect(cmd, **kwargs):
        if cmd[:3] == ["git", "config", "--get"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{origin}\n", stderr="")
        if cmd[:2] == ["gh", "--version"]:
            if not gh_installed:
                raise FileNotFoundError
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["gh", "repo", "view"]:
            if gh_view_error:
                raise subprocess.CalledProcessError(1, "gh")
            stdout = json.dumps({"defaultBranchRef": {"name": default_branch}})
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        if cmd[:3] == ["gh", "secret", "set"]:
            if gh_secret_error:
                raise subprocess.CalledProcessError(1, "gh")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise ValueError(f"Unexpected command: {cmd}")  # pragma: no cover

    return side_effect


def _mock_token_api(respx_mock: respx.MockRouter, app_id: str) -> None:
    """Set up token API mocks for tests that create tokens."""
    respx_mock.get(f"/apps/{app_id}/tokens").mock(
        return_value=Response(200, json={"data": []})
    )
    respx_mock.post(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            201,
            json={"value": "test-token", "expired_at": "2027-02-18T00:00:00Z"},
        )
    )


def test_shows_login_message_when_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "No credentials found" in result.output


def test_shows_error_when_app_not_configured(
    logged_in_cli: None, tmp_path: Path
) -> None:
    with changing_dir(tmp_path):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "No app linked to this directory" in result.output


def test_exits_with_error_when_no_remote_origin(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    subprocess.run(["git", "init"], cwd=configured_app.path, capture_output=True)

    with changing_dir(configured_app.path):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1


def test_shows_error_when_origin_is_not_github(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    subprocess.run(["git", "init"], cwd=configured_app.path, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", GITLAB_ORIGIN],
        cwd=configured_app.path,
        capture_output=True,
    )

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "Remote origin is not a GitHub repository" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_detects_github_origin_and_completes_successfully(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    subprocess.run(["git", "init"], cwd=configured_app.path, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", GITHUB_ORIGIN],
        cwd=configured_app.path,
        capture_output=True,
    )

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "owner/repo" in result.output
    assert "Done" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_detects_non_main_default_branch(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    subprocess.run(["git", "init"], cwd=configured_app.path, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", GITHUB_ORIGIN],
        cwd=configured_app.path,
        capture_output=True,
    )

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="develop",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "develop" in result.output


def test_dry_run_shows_planned_steps(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci", "--dry-run"])

    assert result.exit_code == 0
    assert "dry run" in result.output.lower()
    assert "Created deploy token" in result.output
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "FASTAPI_CLOUD_APP_ID" in result.output
    assert "deploy.yml" in result.output


def test_dry_run_secrets_only_skips_workflow(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci", "--dry-run", "--secrets-only"])

    assert result.exit_code == 0
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "deploy.yml" not in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_creates_token_sets_secrets_and_writes_workflow(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = configured_app.app_id

    respx_mock.get(f"/apps/{app_id}/tokens").mock(
        return_value=Response(200, json={"data": []})
    )
    respx_mock.post(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            201,
            json={
                "value": "test-token-value",
                "expired_at": "2027-02-18T00:00:00Z",
            },
        )
    )

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
            side_effect=_mock_subprocess_run(),
        ) as mock_subprocess,
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "Created deploy token" in result.output
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "FASTAPI_CLOUD_APP_ID" in result.output
    assert "deploy.yml" in result.output
    assert "Done" in result.output
    assert "2027-02-18" in result.output

    # Verify secrets were set via gh CLI
    mock_subprocess.assert_any_call(
        ["gh", "secret", "set", "FASTAPI_CLOUD_TOKEN", "--body", "test-token-value"],
        capture_output=True,
        check=True,
    )
    mock_subprocess.assert_any_call(
        ["gh", "secret", "set", "FASTAPI_CLOUD_APP_ID", "--body", app_id],
        capture_output=True,
        check=True,
    )


@pytest.mark.respx(base_url=settings.base_api_url)
def test_regenerates_existing_token(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = configured_app.app_id

    respx_mock.get(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"id": "token-123", "name": "GitHub Actions \u2014 owner/repo"}
                ]
            },
        )
    )
    respx_mock.post(f"/apps/{app_id}/tokens/token-123/regenerate").mock(
        return_value=Response(
            200,
            json={
                "value": "regenerated-token",
                "expired_at": "2027-02-18T00:00:00Z",
            },
        )
    )

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "Regenerated deploy token" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_shows_manual_instructions_when_gh_not_installed(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = configured_app.app_id

    _mock_token_api(respx_mock, app_id)

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
            side_effect=_mock_subprocess_run(gh_installed=False),
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "gh CLI not found" in result.output
    assert "github.com/owner/repo/settings/secrets/actions" in result.output
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "test-token" in result.output
    assert "FASTAPI_CLOUD_APP_ID" in result.output
    assert app_id in result.output
    assert "Done" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_handles_gh_command_errors_gracefully(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
            side_effect=_mock_subprocess_run(
                gh_view_error=True, gh_secret_error=True
            ),
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "Done" in result.output


@pytest.mark.respx(base_url=settings.base_api_url)
def test_file_flag_uses_custom_filename(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci", "--file", "ci.yml"])

    assert result.exit_code == 0
    assert "ci.yml" in result.output
    assert (configured_app.path / ".github" / "workflows" / "ci.yml").exists()


@pytest.mark.respx(base_url=settings.base_api_url)
def test_overwrites_existing_workflow_when_confirmed(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    workflow_dir = configured_app.path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "deploy.yml").write_text("old content")

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
        patch("rich_toolkit.container.getchar") as mock_getchar,
    ):
        mock_getchar.side_effect = [Keys.ENTER]
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "already exists" in result.output
    assert "Deploy to FastAPI Cloud" in (workflow_dir / "deploy.yml").read_text()


@pytest.mark.respx(base_url=settings.base_api_url)
def test_skips_writing_workflow_when_declined(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    workflow_dir = configured_app.path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "deploy.yml").write_text("old content")

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
        patch("rich_toolkit.container.getchar") as mock_getchar,
        patch(
            "fastapi_cloud_cli.commands.setup_ci.typer.prompt",
            return_value="",
        ),
    ):
        mock_getchar.side_effect = [Keys.RIGHT_ARROW, Keys.ENTER]
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "Skipped writing workflow file" in result.output
    assert (workflow_dir / "deploy.yml").read_text() == "old content"


@pytest.mark.respx(base_url=settings.base_api_url)
def test_renames_workflow_when_declined_and_new_name_given(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

    workflow_dir = configured_app.path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "deploy.yml").write_text("old content")

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=True,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
        patch("rich_toolkit.container.getchar") as mock_getchar,
        patch(
            "fastapi_cloud_cli.commands.setup_ci.typer.prompt",
            return_value="ci-deploy.yml",
        ),
    ):
        mock_getchar.side_effect = [Keys.RIGHT_ARROW, Keys.ENTER]
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "ci-deploy.yml" in result.output
    assert (workflow_dir / "deploy.yml").read_text() == "old content"
    assert (workflow_dir / "ci-deploy.yml").exists()
