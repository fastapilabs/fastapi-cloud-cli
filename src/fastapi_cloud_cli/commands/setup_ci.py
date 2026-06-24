import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)

TOKEN_EXPIRES_DAYS = 365
DEFAULT_WORKFLOW_PATH = Path(".github/workflows/deploy.yml")


class CISetupOutput(BaseModel):
    app_id: str
    repo: str
    branch: str
    workflow_path: str
    created_token: bool
    set_github_secrets: bool
    wrote_workflow: bool
    token_expired_at: str | None = None


def _render_ci_setup_output(data: CISetupOutput, toolkit: FastAPIRichToolkit) -> None:
    if data.wrote_workflow and data.set_github_secrets:
        toolkit.print("Done! Commit and push to start deploying.", emoji="✅")
    elif data.wrote_workflow:
        toolkit.print(
            "Done — workflow file is ready, but GitHub secrets were not set.",
            emoji="✅",
        )
    elif data.set_github_secrets:
        toolkit.print("Done! GitHub Actions secrets are configured.", emoji="✅")
    else:
        toolkit.print("Done!", emoji="✅")

    if data.token_expired_at:
        toolkit.print_line()
        toolkit.print(
            f"Your deploy token expires on [bold]{data.token_expired_at[:10]}[/bold]. "
            "Regenerate it from the dashboard or re-run this command before then.",
        )


class GitHubSecretError(Exception):
    """Raised when setting a GitHub Actions secret fails."""

    pass


def _get_github_host(origin: str) -> str:
    match = re.search(r"(?:git@|https://)([^:/]+)", origin)
    return match.group(1) if match else "github.com"


def _repo_slug_from_origin(origin: str) -> str | None:
    """Extract 'owner/repo' from a GitHub remote URL."""
    # Handles URLs like: git@github.com:owner/repo.git or https://github.com/owner/repo.git
    # Also supports GitHub Enterprise hosts like git@github.enterprise.com:owner/repo.git
    # Match the part after the last : or / (which is owner/repo)
    match = re.search(r"[:/]([^:/]+/[^/]+?)(?:\.git)?$", origin)
    return match.group(1) if match else None


def _check_git_installed() -> bool:
    """Check if git is installed and available."""
    return shutil.which("git") is not None


def _check_gh_cli_installed() -> bool:
    """Check if the GitHub CLI (gh) is installed and available."""
    return shutil.which("gh") is not None


def _get_remote_origin() -> str:
    """Get the remote origin URL of the Git repository."""
    try:
        # Try gh first (to respect gh repo set-default)
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "url", "-q", ".url"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    # CalledProcessError if gh command fails, FileNotFoundError if gh is not installed
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to git command
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()


def _set_github_secret(name: str, value: str) -> None:
    """Set a GitHub Actions secret via the gh CLI.

    Raises:
        GitHubSecretError: If setting the secret fails.
    """
    try:
        subprocess.run(
            ["gh", "secret", "set", name, "--body", value],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise GitHubSecretError(f"Failed to set GitHub secret '{name}'") from e


def _create_token(client: APIClient, app_id: str, token_name: str) -> dict[str, str]:
    """Create a new deploy token.

    Returns token_data dict with 'value' and 'expired_at' keys.
    """
    response = client.post(
        f"/apps/{app_id}/tokens",
        json={"name": token_name, "expires_in_days": TOKEN_EXPIRES_DAYS},
    )
    response.raise_for_status()
    data = response.json()
    return {"value": data["value"], "expired_at": data["expired_at"]}


def _get_default_branch() -> str:
    """Get the default branch of the Git repository."""
    try:
        result = subprocess.run(
            [
                "gh",
                "repo",
                "view",
                "--json",
                "defaultBranchRef",
                "-q",
                ".defaultBranchRef.name",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "main"


def _get_workflow_content(branch: str) -> str:
    return f"""\
name: Deploy to FastAPI Cloud
on:
  push:
    branches: [{branch}]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv run fastapi deploy
        env:
          FASTAPI_CLOUD_TOKEN: ${{{{ secrets.FASTAPI_CLOUD_TOKEN }}}}
          FASTAPI_CLOUD_APP_ID: ${{{{ secrets.FASTAPI_CLOUD_APP_ID }}}}
"""


def _write_workflow_file(branch: str, workflow_path: Path) -> None:
    workflow_content = _get_workflow_content(branch)
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(workflow_content)


def _get_workflow_path(file: str | None) -> Path:
    if file:
        return Path(f".github/workflows/{file}")

    return DEFAULT_WORKFLOW_PATH


def _format_workflow_path(workflow_path: PurePath) -> str:
    return workflow_path.as_posix()


def _resolve_existing_workflow_path(
    toolkit: FastAPIRichToolkit, workflow_path: Path
) -> Path | None:
    if toolkit.confirm(
        f"Workflow file [bold]{_format_workflow_path(workflow_path)}[/bold] already exists. Overwrite?",
        default=False,
        emoji="🗂️",
    ):
        toolkit.print_line()

        return workflow_path

    toolkit.print_line()

    if new_name := toolkit.input(
        "Enter a new filename (without path) or leave blank to skip writing the workflow file:",
        emoji="✏️",
    ).strip():
        toolkit.print_line()

        return Path(f".github/workflows/{new_name}")

    toolkit.print_line()
    toolkit.print("Skipped writing workflow file.", emoji="⏭️")
    toolkit.print_line()

    return None


def setup_ci(
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            )
        ),
    ] = None,
    app_id: str | None = typer.Option(
        None,
        "--app-id",
        help="ID of the app to set up CI for (defaults to the app linked to the directory)",
    ),
    branch: str | None = typer.Option(
        None,
        "--branch",
        "-b",
        help="Branch that triggers deploys (defaults to the repo's default branch)",
    ),
    secrets_only: bool = typer.Option(
        False,
        "--secrets-only",
        "-s",
        help="Provisions token and sets secrets, skips writing the workflow file",
        show_default=True,
    ),
    workflow_only: bool = typer.Option(
        False,
        "--workflow-only",
        help="Writes the workflow file without creating a token or setting secrets",
        show_default=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Prints steps that would be taken without actually performing them",
        show_default=True,
    ),
    file: str | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Custom workflow filename (written to .github/workflows/)",
    ),
    json_output: JsonOutputOption = False,
) -> Any:
    """Configures a GitHub Actions workflow for deploying the app on push to the specified branch.

    Examples:
        fastapi cloud setup-ci                      # Provisions token, sets secrets, and writes workflow file for the 'main' branch
        fastapi cloud setup-ci --branch develop     # Same as above but for the 'develop' branch
        fastapi cloud setup-ci --secrets-only       # Only provisions token and sets secrets, does not write workflow file
        fastapi cloud setup-ci --workflow-only      # Only writes the workflow file
        fastapi cloud setup-ci --dry-run            # Prints the steps that would be taken without performing them
        fastapi cloud setup-ci --file ci.yml        # Writes workflow to .github/workflows/ci.yml
    """

    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        if secrets_only and workflow_only:
            toolkit.fail(
                "invalid_input",
                "--secrets-only and --workflow-only cannot be used together.",
            )

        target_app_id = resolve_app_id_or_fail(
            toolkit,
            app_id=app_id,
            path=path,
            hint="Pass --app-id or run `fastapi deploy` first.",
        )

        if not _check_git_installed():
            toolkit.fail(
                "not_found",
                "git is not installed. Please install git to use this command.",
            )

        try:
            origin = _get_remote_origin()
        except subprocess.CalledProcessError:
            toolkit.fail(
                "not_found",
                "Could not retrieve the git remote origin URL. Make sure you're in a git repository with a remote origin set.",
            )

        # Check if it's a GitHub host (github.com or GitHub Enterprise)
        if "github" not in origin.lower():
            toolkit.fail(
                "invalid_input",
                "Remote origin is not a GitHub repository. Please set up a GitHub repo and add it as the remote origin.",
            )

        repo_slug = _repo_slug_from_origin(origin) or origin

        if not branch:
            branch = _get_default_branch()

        workflow_path = _get_workflow_path(file)
        needs_secrets = not workflow_only
        needs_workflow = not secrets_only
        has_gh = _check_gh_cli_installed() if needs_secrets and not dry_run else True

        if (
            toolkit.mode == "json"
            and needs_workflow
            and not dry_run
            and not file
            and workflow_path.exists()
        ):
            toolkit.fail(
                "invalid_input",
                f"Workflow file {_format_workflow_path(workflow_path)} already exists.",
                hint="Pass --file to choose another workflow file or remove the existing file.",
            )

        if needs_secrets and not dry_run and toolkit.mode == "json" and not has_gh:
            toolkit.fail(
                "dependency_missing",
                "GitHub CLI (`gh`) is required to set GitHub Actions secrets.",
                hint="Install gh or use --workflow-only to write only the workflow file.",
            )

        if dry_run:
            toolkit.print(
                "[yellow]This is a dry run — no changes will be made[/yellow]"
            )
            toolkit.print_line()

        toolkit.print_title("Configuring CI")
        toolkit.print_line()

        toolkit.print(
            f"Setting up CI for [bold]{repo_slug}[/bold] (branch: {branch})",
            emoji="⚙️",
        )
        toolkit.print_line()

        msg_token = "Created deploy token"
        msg_secrets = (
            "Set GitHub Actions secrets [bold blue]FASTAPI_CLOUD_TOKEN[/] "
            "and [bold blue]FASTAPI_CLOUD_APP_ID[/]"
        )
        msg_workflow = f"Wrote [bold]{workflow_path}[/bold] (branch: {branch})"

        if dry_run:
            if needs_secrets:
                toolkit.print(msg_token)
                toolkit.print(msg_secrets)

            if needs_workflow:
                toolkit.print(msg_workflow)

            toolkit.success(
                CISetupOutput(
                    app_id=target_app_id,
                    repo=repo_slug,
                    branch=branch,
                    workflow_path=_format_workflow_path(workflow_path),
                    created_token=False,
                    set_github_secrets=False,
                    wrote_workflow=False,
                ),
                render_output=lambda _data, _toolkit: None,
            )
            return

        token_expired_at: str | None = None
        created_token = False
        set_github_secrets = False
        wrote_workflow = False

        if needs_secrets:
            should_create_token = (
                True
                if toolkit.mode == "json"
                else toolkit.confirm(
                    "Create a FastAPI Cloud deploy token for GitHub Actions?",
                    default=True,
                )
            )
            if toolkit.mode != "json":
                toolkit.print_line()

            if should_create_token:
                # Create unique token name with timestamp to avoid duplicates
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                token_name = f"GitHub Actions — {repo_slug} ({timestamp})"

                with (
                    APIClient() as client,
                    toolkit.progress(
                        title="Generating deploy token...", done_emoji="🔑"
                    ) as progress,
                    client.handle_http_errors(
                        progress, default_message="Error creating deploy token."
                    ),
                ):
                    token_data = _create_token(
                        client=client, app_id=target_app_id, token_name=token_name
                    )
                    token_expired_at = token_data["expired_at"]
                    created_token = True
                    progress.log(msg_token)

                toolkit.print_line()

                if has_gh:
                    should_set_secrets = (
                        True
                        if toolkit.mode == "json"
                        else toolkit.confirm(
                            "Set GitHub Actions secrets "
                            "[bold blue]FASTAPI_CLOUD_TOKEN[/] and "
                            "[bold blue]FASTAPI_CLOUD_APP_ID[/] via gh?",
                            default=True,
                        )
                    )
                    if toolkit.mode != "json":
                        toolkit.print_line()
                else:
                    should_set_secrets = False
                    secrets_url = (
                        f"https://{_get_github_host(origin)}/{repo_slug}"
                        "/settings/secrets/actions"
                    )
                    toolkit.print(
                        "[yellow]gh CLI not found. Set these secrets manually:[/yellow]",
                    )
                    toolkit.print_line()
                    toolkit.print(f"Repository: [blue]{secrets_url}[/]")
                    toolkit.print_line()
                    toolkit.print(
                        f"[bold blue]FASTAPI_CLOUD_TOKEN[/] = {token_data['value']}"
                    )
                    toolkit.print(
                        f"[bold blue]FASTAPI_CLOUD_APP_ID[/] = {target_app_id}"
                    )

                if should_set_secrets:
                    with toolkit.progress(
                        title="Setting repo secrets...", done_emoji="🔒"
                    ) as progress:
                        try:
                            _set_github_secret(
                                "FASTAPI_CLOUD_TOKEN", token_data["value"]
                            )
                            _set_github_secret("FASTAPI_CLOUD_APP_ID", target_app_id)

                            progress.log(msg_secrets)
                        except GitHubSecretError:
                            progress.set_error(
                                "Failed to set GitHub secrets via gh CLI."
                            )
                            toolkit.fail(
                                "api_error",
                                "Failed to set GitHub secrets via gh CLI.",
                            )
                        set_github_secrets = True
                else:
                    toolkit.print("Skipped setting GitHub Actions secrets.", emoji="⏭️")
            else:
                toolkit.print(
                    "Skipped creating deploy token and GitHub secrets.", emoji="⏭️"
                )

        toolkit.print_line()

        if needs_workflow:
            if not file and workflow_path.exists():
                resolved_workflow_path = _resolve_existing_workflow_path(
                    toolkit, workflow_path
                )

                if resolved_workflow_path is None:
                    needs_workflow = False
                else:
                    workflow_path = resolved_workflow_path

            if needs_workflow:
                msg_workflow = f"Wrote [bold]{workflow_path}[/bold] (branch: {branch})"

                _write_workflow_file(branch, workflow_path)
                wrote_workflow = True

                toolkit.print(msg_workflow)
                toolkit.print_line()

        output = CISetupOutput(
            app_id=target_app_id,
            repo=repo_slug,
            branch=branch,
            workflow_path=_format_workflow_path(workflow_path),
            created_token=created_token,
            set_github_secrets=set_github_secrets,
            wrote_workflow=wrote_workflow,
            token_expired_at=token_expired_at,
        )

        toolkit.success(output, render_output=_render_ci_setup_output)
