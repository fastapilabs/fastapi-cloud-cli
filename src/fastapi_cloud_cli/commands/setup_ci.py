import logging
import re
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit, handle_http_errors

logger = logging.getLogger(__name__)

TOKEN_EXPIRES_DAYS = 365
DEFAULT_WORKFLOW_PATH = Path(".github/workflows/deploy.yml")


def _repo_slug_from_origin(origin: str) -> str | None:
    """Extract 'owner/repo' from a GitHub remote URL."""
    # Handles URLs like: git@github.com:owner/repo.git or https://github.com/owner/repo.git
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", origin)
    return match.group(1) if match else None


def _check_gh_cli_installed() -> bool:
    """Check if the GitHub CLI (gh) is installed and available."""
    try:
        subprocess.run(["gh", "--version"], capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _get_remote_origin() -> str:
    """Get the remote origin URL of the Git repository."""
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _set_github_secret(name: str, value: str) -> None:
    """Set a GitHub Actions secret via the gh CLI."""
    subprocess.run(
        ["gh", "secret", "set", name, "--body", value],
        capture_output=True,
        check=True,
    )


def _create_or_regenerate_token(
    app_id: str, token_name: str
) -> tuple[dict[str, str], bool]:
    """Create a new deploy token, or regenerate if one already exists.

    Returns (token_data, regenerated).
    """
    with APIClient() as client:
        existing_id = None

        response = client.get(f"/apps/{app_id}/tokens")
        response.raise_for_status()
        for token in response.json()["data"]:
            if token["name"] == token_name:
                existing_id = token["id"]
                break

        if existing_id:
            response = client.post(
                f"/apps/{app_id}/tokens/{existing_id}/regenerate",
                json={"expires_in_days": TOKEN_EXPIRES_DAYS},
            )
        else:
            response = client.post(
                f"/apps/{app_id}/tokens",
                json={"name": token_name, "expires_in_days": TOKEN_EXPIRES_DAYS},
            )

        response.raise_for_status()
        data = response.json()
        return (
            {"value": data["value"], "expired_at": data["expired_at"]},
            existing_id is not None,
        )


def _get_default_branch() -> str:
    """Get the default branch of the Git repository."""
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().split("/")[-1]
    except subprocess.CalledProcessError:
        return "main"


def _write_workflow_file(branch: str, workflow_path: Path) -> None:
    workflow_content = f"""name: Deploy to FastAPI Cloud
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
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(workflow_content)


def setup_ci(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the folder containing the app (defaults to current directory)"
        ),
    ] = None,
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
) -> None:
    """Configures a GitHub Actions workflow for deploying the app on push to the specified branch.

    Examples:
        fastapi cloud setup-ci                      # Provisions token, sets secrets, and writes workflow file for the 'main' branch
        fastapi cloud setup-ci --branch develop     # Same as above but for the 'develop' branch
        fastapi cloud setup-ci --secrets-only       # Only provisions token and sets secrets, does not write workflow file
        fastapi cloud setup-ci --dry-run            # Prints the steps that would be taken without performing them
        fastapi cloud setup-ci --file ci.yml        # Writes workflow to .github/workflows/ci.yml
    """

    identity = Identity()

    with get_rich_toolkit() as toolkit:
        if not identity.is_logged_in():
            toolkit.print(
                "No credentials found. Use [blue]`fastapi login`[/] to login.",
                tag="auth",
            )
            raise typer.Exit(1)

        app_path = path or Path.cwd()
        app_config = get_app_config(app_path)

        if not app_config:
            toolkit.print(
                "No app linked to this directory. Run [blue]`fastapi deploy`[/] first.",
                tag="error",
            )
            raise typer.Exit(1)

        try:
            origin = _get_remote_origin()
        except subprocess.CalledProcessError:
            toolkit.print(
                "Error retrieving git remote origin URL. Make sure you're in a git repository with a remote origin set.",
                tag="error",
            )
            raise typer.Exit(1) from None

        if "github.com" not in origin:
            toolkit.print(
                "Remote origin is not a GitHub repository. Please set up a GitHub repo and add it as the remote origin.",
                tag="error",
            )
            raise typer.Exit(1)

        repo_slug = _repo_slug_from_origin(origin) or origin
        has_gh = _check_gh_cli_installed()

        if not branch:
            branch = _get_default_branch()

        if dry_run:
            toolkit.print(
                "[yellow]This is a dry run — no changes will be made[/yellow]"
            )
            toolkit.print_line()

        toolkit.print_title("Configuring CI", tag="FastAPI")
        toolkit.print_line()

        toolkit.print(f"Setting up CI for [bold]{repo_slug}[/bold] (branch: {branch})")
        toolkit.print_line()

        msg_token = "Created deploy token"
        msg_secrets = (
            "Set [bold]FASTAPI_CLOUD_TOKEN[/bold] and [bold]FASTAPI_CLOUD_APP_ID[/bold]"
        )
        workflow_file = file or DEFAULT_WORKFLOW_PATH.name
        msg_workflow = (
            f"Wrote [bold].github/workflows/{workflow_file}[/bold] (branch: {branch})"
        )
        msg_done = "Done — commit and push to start deploying."

        if dry_run:
            toolkit.print(msg_token)
            toolkit.print(msg_secrets)
            if not secrets_only:
                toolkit.print(msg_workflow)
            toolkit.print_line()
            toolkit.print(
                "[dim]Note: Dry run shows planned actions. "
                "Actual run may show 'Regenerated' if token already exists.[/dim]"
            )
            return

        token_name = f"GitHub Actions — {repo_slug}"
        with (
            toolkit.progress(title="Generating deploy token...") as progress,
            handle_http_errors(
                progress, default_message="Error creating deploy token."
            ),
        ):
            token_data, regenerated = _create_or_regenerate_token(
                app_config.app_id, token_name
            )
            progress.log("Regenerated deploy token" if regenerated else msg_token)

        toolkit.print_line()

        if has_gh:
            with toolkit.progress(title="Setting repo secrets...") as progress:
                try:
                    _set_github_secret("FASTAPI_CLOUD_TOKEN", token_data["value"])
                    _set_github_secret("FASTAPI_CLOUD_APP_ID", app_config.app_id)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    progress.set_error("Failed to set GitHub secrets via gh CLI.")
                    raise typer.Exit(1) from None
                progress.log(msg_secrets)
        else:
            secrets_url = f"https://github.com/{repo_slug}/settings/secrets/actions"
            toolkit.print(
                "[yellow]gh CLI not found. Set these secrets manually:[/yellow]",
                tag="info",
            )
            toolkit.print_line()
            toolkit.print(f"  Repository: [blue]{secrets_url}[/]")
            toolkit.print_line()
            toolkit.print(f"  [bold]FASTAPI_CLOUD_TOKEN[/bold] = {token_data['value']}")
            toolkit.print(f"  [bold]FASTAPI_CLOUD_APP_ID[/bold] = {app_config.app_id}")

        toolkit.print_line()

        if not secrets_only:
            if file:
                workflow_path = Path(f".github/workflows/{file}")
            else:
                workflow_path = DEFAULT_WORKFLOW_PATH

            write_workflow = True
            if not file and workflow_path.exists():
                overwrite = toolkit.confirm(
                    f"Workflow file [bold]{workflow_path}[/bold] already exists. Overwrite?",
                    tag="workflow",
                    default=False,
                )
                if not overwrite:
                    new_name = toolkit.input(
                        "Enter a new filename (without path) or leave blank to skip writing the workflow file:",
                        tag="workflow",
                    ).strip()
                    if new_name:
                        workflow_path = Path(f".github/workflows/{new_name}")
                    else:
                        toolkit.print("Skipped writing workflow file.")
                        toolkit.print_line()
                        write_workflow = False
                toolkit.print_line()
            if write_workflow:
                msg_workflow = f"Wrote [bold]{workflow_path}[/bold] (branch: {branch})"
                with toolkit.progress(title="Writing workflow file...") as progress:
                    _write_workflow_file(branch, workflow_path)
                    progress.log(msg_workflow)

                toolkit.print_line()

        toolkit.print(msg_done)
        toolkit.print_line()
        # Token expiration date is in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ), extract date portion
        toolkit.print(
            f"Your deploy token expires on [bold]{token_data['expired_at'][:10]}[/bold]. "
            "Regenerate it from the dashboard or re-run this command before then.",
        )
