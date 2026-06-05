import logging
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer
from rich_toolkit.menu import Option

from fastapi_cloud_cli.commands.deploy.archive import _get_large_files, archive
from fastapi_cloud_cli.commands.deploy.cloud import _create_deployment, _get_app
from fastapi_cloud_cli.commands.deploy.configure import _configure_app
from fastapi_cloud_cli.commands.deploy.upload import _cancel_upload, _upload_deployment
from fastapi_cloud_cli.commands.deploy.wait import _wait_for_deployment
from fastapi_cloud_cli.commands.deploy.waitlist import _waitlist_form
from fastapi_cloud_cli.commands.login import login
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import is_ci_enabled

logger = logging.getLogger(__name__)


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
) -> Any:
    """
    Deploy a [bold]FastAPI[/bold] app to FastAPI Cloud. 🚀
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

    with get_rich_toolkit() as toolkit:
        if not has_auth:
            logger.debug("User not logged in, prompting for login or waitlist")

            if is_ci_enabled():
                toolkit.fail(
                    "not_logged_in",
                    "FASTAPI_CLOUD_TOKEN is required to deploy from CI.",
                    hint=(
                        "Run `fastapi cloud setup-ci` to configure a deploy token, "
                        "or set FASTAPI_CLOUD_TOKEN in your CI secrets."
                    ),
                )

            toolkit.print_title("Welcome to FastAPI Cloud!", tag="FastAPI")
            toolkit.print_line()

            if identity.user_token and identity.is_user_token_expired():
                toolkit.print(
                    "Your session has expired. Please log in again.",
                    tag="info",
                )
            else:
                toolkit.print(
                    "You need to be logged in to deploy to FastAPI Cloud.",
                    tag="info",
                )
            toolkit.print_line()

            choice = toolkit.ask(
                "What would you like to do?",
                tag="auth",
                options=[
                    Option({"name": "Login to my existing account", "value": "login"}),
                    Option({"name": "Join the waiting list", "value": "waitlist"}),
                ],
            )

            if choice == "login":
                login()
            else:
                _waitlist_form(toolkit)
                raise typer.Exit(1)

        if use_deploy_token:
            toolkit.print(
                "Using token from [bold blue]FASTAPI_CLOUD_TOKEN[/] environment variable",
                tag="info",
            )
            toolkit.print_line()

        with APIClient(use_deploy_token=use_deploy_token) as client:
            toolkit.print_title("Starting deployment", tag="FastAPI")
            toolkit.print_line()

            path_to_deploy = path or Path.cwd()
            logger.debug("Deploying from path: %s", path_to_deploy)

            app_config = get_app_config(path_to_deploy)

            if app_config and provided_app_id and app_config.app_id != provided_app_id:
                toolkit.print(
                    f"[error]Error: Provided app ID ({provided_app_id}) does not match the local "
                    f"config ({app_config.app_id}).[/]"
                )
                toolkit.print_line()
                toolkit.print(
                    "Run [bold]fastapi cloud unlink[/] to remove the local config, "
                    "or remove --app-id / unset FASTAPI_CLOUD_APP_ID to use the configured app.",
                    tag="tip",
                )

                raise typer.Exit(1) from None

            if provided_app_id:
                target_app_id = provided_app_id
            elif app_config:
                target_app_id = app_config.app_id
            else:
                logger.debug("No app config found, configuring new app")

                app_config = _configure_app(
                    toolkit=toolkit,
                    client=client,
                    path_to_deploy=path_to_deploy,
                )
                toolkit.print_line()

                target_app_id = app_config.app_id

            if provided_app_id:
                toolkit.print(f"Deploying to app [blue]{target_app_id}[/blue]...")
            else:
                toolkit.print("Deploying app...")

            toolkit.print_line()

            with toolkit.progress("Checking app...", transient=True) as progress:
                with client.handle_http_errors(progress):
                    logger.debug("Checking app with ID: %s", target_app_id)
                    app = _get_app(client=client, app_id=target_app_id)

                if not app:
                    logger.debug("App not found in API")
                    progress.set_error(
                        "App not found. Make sure you're logged in the correct account."
                    )

            if not app:
                toolkit.print_line()

                if not provided_app_id:
                    toolkit.print(
                        "If you deleted this app, you can run [bold]fastapi cloud unlink[/] to unlink the local configuration.",
                        tag="tip",
                    )
                raise typer.Exit(1)

            large_files = _get_large_files(
                path_to_deploy, threshold_mb=large_file_threshold
            )
            if large_files:
                toolkit.print(
                    f"⚠️  Some uploaded files are larger than {large_file_threshold} MB ⚖️ :",
                    tag="warning",
                )
                for fname, fsize in large_files[:3]:
                    fsize_mb = fsize // (1024 * 1024)
                    toolkit.print(f" • {fname} [yellow]({fsize_mb} MB)[/yellow]")
                is_more = len(large_files) > 3
                if is_more:
                    toolkit.print(f" [dim]...and {len(large_files) - 3} more[/dim]")

                large_files_docs_url = "https://fastapicloud.com/docs/fastapi-cloud-cli/deploy/#large-files-warning"
                toolkit.print(
                    f"Read more: [link={large_files_docs_url}]{large_files_docs_url}[/link]",
                    tag="tip",
                )
                toolkit.print_line()

            with tempfile.TemporaryDirectory() as temp_dir:
                logger.debug("Creating archive for deployment")
                archive_path = Path(temp_dir) / "archive.tar"
                archive(path_to_deploy, archive_path)

                with (
                    toolkit.progress(
                        title="Creating deployment", done_emoji="📦"
                    ) as progress,
                    client.handle_http_errors(progress),
                ):
                    logger.debug("Creating deployment for app: %s", app.id)
                    deployment = _create_deployment(client=client, app_id=app.id)

                    try:
                        progress.log(
                            f"Deployment created successfully! Deployment slug: {deployment.slug}"
                        )

                        _upload_deployment(
                            fastapi_client=client,
                            deployment_id=deployment.id,
                            archive_path=archive_path,
                            progress=progress,
                        )

                        progress.log("Deployment uploaded successfully!")
                    except KeyboardInterrupt:
                        _cancel_upload(client=client, deployment_id=deployment.id)
                        raise

            toolkit.print_line()

            if not skip_wait:
                logger.debug("Waiting for deployment to complete")
                _wait_for_deployment(
                    toolkit=toolkit,
                    client=client,
                    app_id=app.id,
                    deployment=deployment,
                )
            else:
                logger.debug("Skipping deployment wait as requested")
                toolkit.print(
                    f"Check the status of your deployment at [link={deployment.dashboard_url}]{deployment.dashboard_url}[/link]"
                )
