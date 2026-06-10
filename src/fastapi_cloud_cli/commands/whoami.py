import logging
from typing import Any

from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.errors import ErrorCode
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class WhoAmIOutput(BaseModel):
    email: str | None = None
    has_deploy_token: bool


def _render_not_logged_in(
    toolkit: RichToolkit, *, code: ErrorCode, message: str, hint: str
) -> None:
    toolkit.print(f"{message} {hint}")


def _render_whoami_output(data: WhoAmIOutput, toolkit: RichToolkit) -> None:
    toolkit.print(f"⚡ [bold]{data.email}[/bold]")

    if data.has_deploy_token:
        toolkit.print(
            "⚡ [bold]Using API token from environment variable for "
            "[blue]`fastapi deploy`[/blue] command.[/bold]"
        )


def whoami(
    json_output: JsonOutputOption = False,
) -> Any:
    identity = Identity()

    with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run [blue]`fastapi login`[/] or set [blue]FASTAPI_CLOUD_TOKEN.[/]",
                render_output=_render_not_logged_in,
            )

        with (
            APIClient() as client,
            toolkit.progress(
                title="⚡ Fetching profile",
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
