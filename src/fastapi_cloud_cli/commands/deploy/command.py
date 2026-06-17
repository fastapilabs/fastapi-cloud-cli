import logging
import tempfile
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from pydantic import BaseModel

from fastapi_cloud_cli.commands.deploy.archive import _get_large_files, archive
from fastapi_cloud_cli.commands.deploy.cloud import (
    AppResponse,
    CreateDeploymentResponse,
    _create_deployment,
    _get_app,
)
from fastapi_cloud_cli.commands.deploy.configure import _configure_app
from fastapi_cloud_cli.commands.deploy.upload import _cancel_upload, _upload_deployment
from fastapi_cloud_cli.commands.deploy.wait import _wait_for_deployment
from fastapi_cloud_cli.commands.login import _interactive_login
from fastapi_cloud_cli.utils.api import APIClient, DeploymentStatus
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.errors import ErrorCode
from fastapi_cloud_cli.utils.execution import JsonOutputOption, is_ci_enabled

logger = logging.getLogger(__name__)


class DeployOutput(BaseModel):
    deployment_id: str
    app_id: str
    slug: str
    status: DeploymentStatus
    dashboard_url: str
    url: str


def _get_deploy_output(deployment: CreateDeploymentResponse) -> DeployOutput:
    return DeployOutput(
        deployment_id=deployment.id,
        app_id=deployment.app_id,
        slug=deployment.slug,
        status=deployment.status,
        dashboard_url=deployment.dashboard_url,
        url=deployment.url,
    )


def _get_large_file_warnings(
    large_files: list[tuple[Path, int]],
    *,
    threshold_mb: int,
) -> list[dict[str, Any]]:
    if not large_files:
        return []

    count = len(large_files)
    message = (
        f"1 uploaded file is larger than {threshold_mb} MB."
        if count == 1
        else f"{count} uploaded files are larger than {threshold_mb} MB."
    )

    return [
        {
            "code": "large_files",
            "message": message,
            "files": [
                {"path": path.as_posix(), "size_bytes": size}
                for path, size in large_files
            ],
        }
    ]


def _render_app_id_mismatch(
    toolkit: FastAPIRichToolkit, *, code: ErrorCode, message: str, hint: str
) -> None:
    toolkit.print_error(message)
    toolkit.print_line()
    toolkit.print_hint(hint)


def _render_app_not_found(
    toolkit: FastAPIRichToolkit, *, code: ErrorCode, message: str, hint: str
) -> None:
    toolkit.print_line()


def _render_linked_app_not_found(
    toolkit: FastAPIRichToolkit, *, code: ErrorCode, message: str, hint: str
) -> None:
    _render_app_not_found(toolkit, code=code, message=message, hint=hint)
    toolkit.print_hint(
        "If you deleted this app, you can run [bold]fastapi cloud unlink[/] to unlink the local configuration."
    )


def deploy(
    path: Annotated[
        Path | None,
        typer.Argument(
            help=(
                "Path to the directory with your app's pyproject.toml "
                "(defaults to current directory)"
            )
        ),
    ] = None,
    skip_wait: Annotated[
        bool, typer.Option("--no-wait", help="Skip waiting for deployment status")
    ] = False,
    provided_app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="Application ID to deploy to",
            envvar="FASTAPI_CLOUD_APP_ID",
        ),
    ] = None,
    large_file_threshold: Annotated[
        int,
        typer.Option(
            help="File size threshold in MB for warning about large files",
            min=1,
            envvar="FASTAPI_CLOUD_LARGE_FILE_THRESHOLD",
        ),
    ] = 10,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Deploy a [bold]FastAPI[/bold] app to FastAPI Cloud.
    """
    logger.debug("Deploy command started")
    logger.debug(
        "Deploy path: %s, skip_wait: %s, app_id: %s", path, skip_wait, provided_app_id
    )

    identity = Identity()
    use_deploy_token = identity.has_deploy_token()
    has_auth = use_deploy_token or identity.is_logged_in()

    logger.debug(
        "Authentication mode: %s", "deploy token" if use_deploy_token else "user token"
    )

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not has_auth:
            logger.debug("User not logged in, starting login")

            if is_ci_enabled():
                toolkit.fail(
                    "not_logged_in",
                    "FASTAPI_CLOUD_TOKEN is required to deploy from CI.",
                    hint=(
                        "Run `fastapi cloud setup-ci` to configure a deploy token, "
                        "or set FASTAPI_CLOUD_TOKEN in your CI secrets."
                    ),
                )

            if json_output:
                toolkit.fail(
                    "not_logged_in",
                    "No credentials found.",
                    hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
                )

            toolkit.print_title(
                "Welcome to FastAPI Cloud!",
                tag="FastAPI Cloud",
                emoji="👋",
                animate=True,
            )
            toolkit.print_line()

            if identity.user_token and identity.is_user_token_expired():
                toolkit.print("Your session has expired. Please log in again.")
            else:
                toolkit.print("You need to be logged in to deploy to FastAPI Cloud.")

            toolkit.print_line()
            should_login = toolkit.confirm(
                "Do you want to log in now?",
                default=True,
            )

            if not should_login:
                toolkit.print_line()
                toolkit.print("Deployment cancelled.")
                raise typer.Exit(0)

            toolkit.print_line()
            _interactive_login(toolkit)
            toolkit.print_line()

        with APIClient(use_deploy_token=use_deploy_token) as client:
            # the welcome title already shows the header when logging in
            if has_auth:
                toolkit.print_title("FastAPI Cloud", animate=True)
                toolkit.print_line()

            if use_deploy_token:
                toolkit.print(
                    "Using token from [bold blue]FASTAPI_CLOUD_TOKEN[/] environment variable",
                )
                toolkit.print_line()

            path_to_deploy = path or Path.cwd()
            logger.debug("Deploying from path: %s", path_to_deploy)

            app_config = get_app_config(path_to_deploy)

            if app_config and provided_app_id and app_config.app_id != provided_app_id:
                toolkit.fail(
                    "invalid_input",
                    f"Provided app ID ({provided_app_id}) does not match the local config ({app_config.app_id}).",
                    hint=(
                        "Run `fastapi cloud unlink` to remove the local config, "
                        "or remove --app-id / unset FASTAPI_CLOUD_APP_ID to use the configured app."
                    ),
                    render_output=_render_app_id_mismatch,
                )

            if provided_app_id:
                target_app_id = provided_app_id
            elif app_config:
                target_app_id = app_config.app_id
            else:
                if json_output:
                    toolkit.fail(
                        "missing_required_input",
                        "App ID is required.",
                        hint="Pass --app-id or run `fastapi cloud apps create --link` first.",
                    )

                logger.debug("No app config found, configuring new app")

                app_config = _configure_app(
                    toolkit=toolkit,
                    client=client,
                    path_to_deploy=path_to_deploy,
                )
                toolkit.print_line()

                target_app_id = app_config.app_id

            if provided_app_id:
                toolkit.print(
                    f"Deploying to app [blue]{target_app_id}[/blue]...", emoji="🚀"
                )
            else:
                toolkit.print("Deploying app...", emoji="🚀")

            toolkit.print_line()

            with toolkit.progress("Checking app...", transient=True) as progress:
                with client.handle_http_errors(progress, toolkit=toolkit):
                    logger.debug("Checking app with ID: %s", target_app_id)
                    app = _get_app(client=client, app_id=target_app_id)

                if app is None:
                    logger.debug("App not found in API")
                    progress.set_error(
                        "App not found. Make sure you're logged in the correct account."
                    )

            if app is None:
                toolkit.fail(
                    "not_found",
                    "App not found. Make sure you're logged in the correct account.",
                    render_output=(
                        _render_app_not_found
                        if provided_app_id
                        else _render_linked_app_not_found
                    ),
                )

            app = cast(AppResponse, app)

            large_files = _get_large_files(
                path_to_deploy, threshold_mb=large_file_threshold
            )
            warnings = _get_large_file_warnings(
                large_files,
                threshold_mb=large_file_threshold,
            )
            if large_files:
                toolkit.print(
                    f"Some uploaded files are larger than {large_file_threshold} MB:",
                    emoji="⚠️",
                )
                toolkit.print_line()
                for fname, fsize in large_files[:3]:
                    fsize_mb = fsize // (1024 * 1024)
                    toolkit.print(
                        f"• [bold]{fname}[/bold] [yellow]({fsize_mb} MB)[/yellow]"
                    )
                is_more = len(large_files) > 3
                if is_more:
                    toolkit.print(f"[dim]...and {len(large_files) - 3} more[/dim]")

                large_files_docs_url = "https://fastapicloud.com/docs/fastapi-cloud-cli/deploy/#large-files-warning"
                toolkit.print_line()
                toolkit.print(
                    f"Read more: [link={large_files_docs_url}]{large_files_docs_url}[/link]",
                    emoji="💡",
                )
                toolkit.print_line()

            will_wait = not skip_wait and not json_output

            with tempfile.TemporaryDirectory() as temp_dir:
                logger.debug("Creating archive for deployment")
                archive_path = Path(temp_dir) / "archive.tar"
                archive(path_to_deploy, archive_path)

                with (
                    toolkit.progress(
                        title="Creating deployment",
                        # the build status replaces this when waiting
                        transient=will_wait,
                        done_emoji="📦",
                    ) as progress,
                    client.handle_http_errors(progress, toolkit=toolkit),
                ):
                    logger.debug("Creating deployment for app: %s", app.id)
                    deployment = _create_deployment(client=client, app_id=app.id)

                    try:
                        progress.log(
                            f"Deployment created successfully! Deployment slug: {deployment.slug}"
                        )

                        deployment = _upload_deployment(
                            fastapi_client=client,
                            deployment_id=deployment.id,
                            archive_path=archive_path,
                            progress=progress,
                        )

                        progress.log("Deployment uploaded successfully!")
                    except KeyboardInterrupt:
                        _cancel_upload(client=client, deployment_id=deployment.id)
                        raise

            if will_wait:
                logger.debug("Waiting for deployment to complete")
                _wait_for_deployment(
                    toolkit=toolkit,
                    client=client,
                    app_id=app.id,
                    deployment=deployment,
                )
            else:
                toolkit.print_line()
                logger.debug("Skipping deployment wait as requested")
                if json_output:
                    toolkit.success(
                        _get_deploy_output(deployment),
                        warnings=warnings,
                        hint=(
                            "Check deployment status in the FastAPI Cloud dashboard: "
                            f"{deployment.dashboard_url}"
                        ),
                    )
                    return

                toolkit.print(
                    f"Check the status of your deployment at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
                )
