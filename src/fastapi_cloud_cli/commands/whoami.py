import logging
from typing import Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli._app import cloud_app
from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class WhoAmIOutput(BaseModel):
    email: str | None = None
    has_deploy_token: bool


def _render_whoami_output(data: WhoAmIOutput, toolkit: RichToolkit) -> None:
    toolkit.print(f"[bold]{data.email}[/bold]", emoji="⚡")

    if data.has_deploy_token:
        toolkit.print(
            "[bold]Using API token from environment variable for "
            "[blue]`fastapi deploy`[/blue] command.[/bold]",
            emoji="⚡",
        )


@cloud_app.command(cls=UserCommand)
def whoami(
    ctx: typer.Context,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Show the currently logged in user.
    """

    command_context = get_user_command_context(ctx)
    toolkit = command_context.toolkit
    identity = command_context.identity

    with (
        APIClient() as client,
        toolkit.progress(
            title="Fetching profile",
            transient=True,
        ) as progress,
    ):
        with client.handle_http_errors(
            progress,
            default_message="",
            toolkit=toolkit,
        ):
            response = client.get("/users/me")
            response.raise_for_status()

    data = response.json()

    result = WhoAmIOutput(
        has_deploy_token=identity.has_deploy_token(), email=data["email"]
    )

    toolkit.success(result, render_output=_render_whoami_output)
