from typing import Annotated, Any

import typer

from fastapi_cloud_cli.commands._flow import (
    DEFAULT_LOGIN_TIMEOUT_SECONDS,
    complete_device_login,
    render_login_output,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


def wait(
    device_code: Annotated[
        str,
        typer.Option(
            "--device-code",
            help="Device code returned by `fastapi cloud auth login --json`.",
        ),
    ],
    interval: Annotated[
        int,
        typer.Option(
            "--interval",
            help="Seconds between authorization polling attempts.",
            min=5,
        ),
    ] = 5,
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
    Wait for a device authorization flow to complete.
    """
    with get_rich_toolkit(json_output=json_output) as toolkit:
        with APIClient() as client:
            toolkit.print_title(
                "Login to FastAPI Cloud", tag="FastAPI Cloud", emoji="🔐"
            )
            toolkit.print_line()

            with toolkit.progress(
                "Waiting for user to authorize...", transient=True
            ) as progress:
                result = complete_device_login(
                    client=client,
                    progress=progress,
                    toolkit=toolkit,
                    device_code=device_code,
                    interval=interval,
                    timeout=timeout,
                    cancel_hint="Run `fastapi cloud auth wait --json` again to retry.",
                )

            toolkit.success(
                result,
                render_output=render_login_output,
            )
