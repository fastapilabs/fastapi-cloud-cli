import logging
from typing import Annotated, Any

import typer

from fastapi_cloud_cli.commands._flow import (
    DEFAULT_LOGIN_TIMEOUT_SECONDS,
    complete_device_login,
    device_authorization_output,
    render_login_output,
    start_device_authorization,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


def login(
    no_open: Annotated[
        bool,
        typer.Option(
            "--no-open",
            help="Do not open the browser automatically.",
        ),
    ] = False,
    timeout: Annotated[
        int,
        typer.Option(
            "--timeout",
            help="Maximum seconds to wait for authorization.",
            min=10,
        ),
    ] = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Login to FastAPI Cloud. 🚀
    """
    if json_output:
        with get_rich_toolkit(json_output=json_output, minimal=True) as toolkit:
            with APIClient() as client:
                with toolkit.progress(
                    "Starting authorization", transient=True
                ) as progress:
                    with client.handle_http_errors(progress, toolkit=toolkit):
                        authorization_data = start_device_authorization(client)

                toolkit.success(device_authorization_output(authorization_data))

        return

    identity = Identity()
    is_logged_in = identity.is_logged_in()

    with get_rich_toolkit(minimal=is_logged_in) as toolkit:
        if is_logged_in:
            toolkit.print("You are already logged in.")
            toolkit.print(
                "Run [bold]fastapi cloud logout[/bold] first if you want to switch accounts."
            )

            return

        if identity.has_deploy_token():
            toolkit.print(
                "You have [bold blue]FASTAPI_CLOUD_TOKEN[/] environment variable set.\n"
                "This token will take precedence over the user token for "
                "[blue]`fastapi deploy`[/] command.",
                tag="Warning",
            )

        with APIClient() as client:
            toolkit.print_title("Login to FastAPI Cloud", tag="FastAPI")

            toolkit.print_line()

            with toolkit.progress("Starting authorization", transient=True) as progress:
                with client.handle_http_errors(progress, toolkit=toolkit):
                    authorization_data = start_device_authorization(client)

                url = authorization_data.verification_uri_complete

                if no_open:
                    toolkit.print(f"Open {url}")
                    toolkit.print_line()
                else:
                    launch_cmd_res = typer.launch(url)
                    logger.debug(f"Launch command result: {launch_cmd_res}")
                    progress.log(f"Opening [link={url}]{url}[/link]")

            with toolkit.progress(
                "Waiting for user to authorize...", transient=True
            ) as progress:
                result = complete_device_login(
                    client=client,
                    progress=progress,
                    toolkit=toolkit,
                    device_code=authorization_data.device_code,
                    interval=authorization_data.interval,
                    timeout=timeout,
                    cancel_hint="Run `fastapi cloud login` again to retry.",
                )

            toolkit.success(
                result,
                render_output=render_login_output,
            )
