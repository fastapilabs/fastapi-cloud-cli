import subprocess
from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from fastapi_cloud_cli.cli import cloud_app as app
from fastapi_cloud_cli.commands.setup_ci import (
    GitHubSecretError,
    _check_gh_cli_installed,
    _check_git_installed,
    _get_default_branch,
    _get_remote_origin,
    _set_github_secret,
)
from tests.conftest import ConfiguredApp
from tests.utils import Keys, changing_dir

runner = CliRunner()

GITHUB_ORIGIN = "git@github.com:owner/repo.git"
GITLAB_ORIGIN = "git@gitlab.com:owner/repo.git"


def _mock_token_api(
    respx_mock: respx.MockRouter, app_id: str, *, token_value: str = "test-token"
) -> None:
    """Set up token API mocks for tests that create tokens."""
    respx_mock.post(f"/apps/{app_id}/tokens").mock(
        return_value=Response(
            201,
            json={"value": token_value, "expired_at": "2027-02-18T00:00:00Z"},
        )
    )


def test_shows_login_message_when_not_logged_in(logged_out_cli: None) -> None:
    result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "No credentials found" in result.output


def test_shows_message_if_app_not_configured(logged_in_cli: None) -> None:
    result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "No app linked to this directory" in result.output


def test_shows_error_when_git_not_installed(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_git_installed",
            return_value=False,
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "git is not installed" in result.output


def test_exits_with_error_when_no_remote_origin(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "Error retrieving git remote origin URL" in result.output


def test_shows_error_when_origin_is_not_github(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITLAB_ORIGIN,
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "Remote origin is not a GitHub repository" in result.output


@pytest.mark.respx
def test_detects_github_origin_and_completes_successfully(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

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


@pytest.mark.respx
def test_detects_non_main_default_branch(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

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
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="develop",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "(branch: develop)" in result.output


def test_get_default_branch_falls_back_to_main() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "git"),
    ):
        assert _get_default_branch() == "main"


def test_get_default_branch_returns_branch_name() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0, stdout="develop\n"),
    ):
        assert _get_default_branch() == "develop"


def test_check_git_installed_returns_true() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.shutil.which", return_value="/usr/bin/git"
    ):
        assert _check_git_installed() is True


def test_check_git_installed_returns_false_when_missing() -> None:
    with patch("fastapi_cloud_cli.commands.setup_ci.shutil.which", return_value=None):
        assert _check_git_installed() is False


def test_check_gh_cli_installed_returns_true() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.shutil.which", return_value="/usr/bin/gh"
    ):
        assert _check_gh_cli_installed() is True


def test_check_gh_cli_installed_returns_false_when_missing() -> None:
    with patch("fastapi_cloud_cli.commands.setup_ci.shutil.which", return_value=None):
        assert _check_gh_cli_installed() is False


def test_get_remote_origin_returns_url() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
        return_value=subprocess.CompletedProcess(
            [], 0, stdout="git@github.com:owner/repo.git\n"
        ),
    ):
        assert _get_remote_origin() == "git@github.com:owner/repo.git"


def test_get_remote_origin_falls_back_to_git_when_gh_fails() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
        side_effect=[
            subprocess.CalledProcessError(1, "gh"),  # gh fails
            subprocess.CompletedProcess(
                [], 0, stdout="git@github.com:owner/repo.git\n"
            ),
        ],
    ):
        assert _get_remote_origin() == "git@github.com:owner/repo.git"


def test_set_github_secret_calls_gh_cli() -> None:
    with patch("fastapi_cloud_cli.commands.setup_ci.subprocess.run") as mock_run:
        _set_github_secret("MY_SECRET", "my-value")

    mock_run.assert_called_once_with(
        ["gh", "secret", "set", "MY_SECRET", "--body", "my-value"],
        capture_output=True,
        check=True,
    )


def test_set_github_secret_raises_custom_exception_on_command_error() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "gh"),
    ):
        with pytest.raises(GitHubSecretError, match="Failed to set GitHub secret"):
            _set_github_secret("MY_SECRET", "my-value")


def test_set_github_secret_raises_custom_exception_when_gh_not_found() -> None:
    with patch(
        "fastapi_cloud_cli.commands.setup_ci.subprocess.run",
        side_effect=FileNotFoundError("gh not found"),
    ):
        with pytest.raises(GitHubSecretError, match="Failed to set GitHub secret"):
            _set_github_secret("MY_SECRET", "my-value")


def test_dry_run_shows_planned_steps(
    logged_in_cli: None, configured_app: ConfiguredApp
) -> None:
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
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
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
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
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
    ):
        result = runner.invoke(app, ["setup-ci", "--dry-run", "--secrets-only"])

    assert result.exit_code == 0
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "deploy.yml" not in result.output


@pytest.mark.respx
def test_secrets_only_skips_workflow_file(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

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
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci", "--secrets-only"])

    assert result.exit_code == 0
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "Done" in result.output
    assert not (configured_app.path / ".github" / "workflows" / "deploy.yml").exists()


@pytest.mark.respx
def test_branch_flag_overrides_detected_branch(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

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
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret"),
    ):
        result = runner.invoke(app, ["setup-ci", "--branch", "production"])

    assert result.exit_code == 0
    assert "(branch: production)" in result.output

    workflow_file = configured_app.path / ".github" / "workflows" / "deploy.yml"
    content = workflow_file.read_text()
    assert "branches: [production]" in content


@pytest.mark.respx
def test_creates_token_sets_secrets_and_writes_workflow(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    app_id = configured_app.app_id
    _mock_token_api(respx_mock, app_id, token_value="test-token-value")

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
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch("fastapi_cloud_cli.commands.setup_ci._set_github_secret") as mock_secret,
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "Created deploy token" in result.output
    assert "FASTAPI_CLOUD_TOKEN" in result.output
    assert "FASTAPI_CLOUD_APP_ID" in result.output
    assert "deploy.yml" in result.output
    assert "Done" in result.output
    assert "2027-02-18" in result.output

    mock_secret.assert_any_call("FASTAPI_CLOUD_TOKEN", "test-token-value")
    mock_secret.assert_any_call("FASTAPI_CLOUD_APP_ID", app_id)

    workflow_file = configured_app.path / ".github" / "workflows" / "deploy.yml"
    assert workflow_file.exists()
    content = workflow_file.read_text()
    assert "Deploy to FastAPI Cloud" in content
    assert "branches: [main]" in content


@pytest.mark.respx
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
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=GITHUB_ORIGIN,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=False,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
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


@pytest.mark.respx
def test_handles_gh_command_errors_gracefully(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

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
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._set_github_secret",
            side_effect=GitHubSecretError(
                "Failed to set GitHub secret 'FASTAPI_CLOUD_TOKEN'"
            ),
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 1
    assert "Failed to set GitHub secrets" in result.output


@pytest.mark.respx
def test_file_flag_uses_custom_filename(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    _mock_token_api(respx_mock, configured_app.app_id)

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


@pytest.mark.respx
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
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
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


@pytest.mark.respx
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
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
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
        mock_getchar.side_effect = [Keys.RIGHT_ARROW, Keys.ENTER, Keys.ENTER]
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "Skipped writing workflow file" in result.output
    assert (workflow_dir / "deploy.yml").read_text() == "old content"


@pytest.mark.respx
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
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
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
        mock_getchar.side_effect = [
            Keys.RIGHT_ARROW,
            Keys.ENTER,
            *"ci-deploy.yml",
            Keys.ENTER,
        ]
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "ci-deploy.yml" in result.output
    assert (workflow_dir / "deploy.yml").read_text() == "old content"
    assert (workflow_dir / "ci-deploy.yml").exists()


def test_get_github_host_extracts_from_ssh_url() -> None:
    from fastapi_cloud_cli.commands.setup_ci import _get_github_host

    assert _get_github_host("git@github.com:owner/repo.git") == "github.com"


def test_get_github_host_extracts_from_https_url() -> None:
    from fastapi_cloud_cli.commands.setup_ci import _get_github_host

    assert _get_github_host("https://github.com/owner/repo.git") == "github.com"


def test_get_github_host_extracts_from_enterprise_ssh_url() -> None:
    from fastapi_cloud_cli.commands.setup_ci import _get_github_host

    assert (
        _get_github_host("git@github.enterprise.com:owner/repo.git")
        == "github.enterprise.com"
    )


def test_get_github_host_extracts_from_enterprise_https_url() -> None:
    from fastapi_cloud_cli.commands.setup_ci import _get_github_host

    assert (
        _get_github_host("https://github.enterprise.com/owner/repo.git")
        == "github.enterprise.com"
    )


@pytest.mark.respx
def test_shows_enterprise_secrets_url_when_gh_not_installed(
    logged_in_cli: None,
    configured_app: ConfiguredApp,
    respx_mock: respx.MockRouter,
) -> None:
    """Verify that GitHub Enterprise URLs are built correctly for manual setup."""
    _mock_token_api(respx_mock, configured_app.app_id)

    enterprise_origin = "git@github.enterprise.com:owner/repo.git"

    with (
        changing_dir(configured_app.path),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_remote_origin",
            return_value=enterprise_origin,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._check_gh_cli_installed",
            return_value=False,
        ),
        patch(
            "fastapi_cloud_cli.commands.setup_ci._get_default_branch",
            return_value="main",
        ),
    ):
        result = runner.invoke(app, ["setup-ci"])

    assert result.exit_code == 0
    assert "gh CLI not found" in result.output
    # Should use enterprise host, not github.com
    assert "github.enterprise.com/owner/repo/settings/secrets/actions" in result.output
    assert "github.com/owner/repo" not in result.output
