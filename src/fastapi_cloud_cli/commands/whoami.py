import logging
from typing import Any

from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption, is_json_enabled

logger = logging.getLogger(__name__)


class WhoAmIOutput(BaseModel):
    authenticated: bool
    email: str | None = None
    has_deploy_token: bool


def _render_whoami_output(data: WhoAmIOutput, toolkit: RichToolkit) -> None:
    if not data.authenticated:
        toolkit.print("No credentials found. Use [blue]`fastapi login`[/] to login.")
    else:
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
    json_enabled = is_json_enabled() or json_output

    result = WhoAmIOutput(
        authenticated=False, has_deploy_token=identity.has_deploy_token()
    )

    with get_rich_toolkit(minimal=True, json_output=json_enabled) as toolkit:
        if not identity.is_logged_in():
            if json_enabled:
                toolkit.fail(
                    "not_logged_in",
                    "No credentials found.",
                    hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
                )

            result.authenticated = False
            result.has_deploy_token = identity.has_deploy_token()

            toolkit.success(result, render_output=_render_whoami_output)
            return None

        with APIClient() as client:
            if json_enabled:
                with client.handle_http_errors(
                    None,
                    default_message="",
                    toolkit=toolkit,
                    json_output=True,
                ):
                    response = client.get("/users/me")
                    response.raise_for_status()
            else:
                with toolkit.progress(
                    title="⚡ Fetching profile",
                    transient=True,
                ) as progress:
                    with client.handle_http_errors(progress, default_message=""):
                        response = client.get("/users/me")
                        response.raise_for_status()

        data = response.json()

        result.authenticated = True
        result.email = data["email"]
        result.has_deploy_token = identity.has_deploy_token()

        toolkit.success(result, render_output=_render_whoami_output)
