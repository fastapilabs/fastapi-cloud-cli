from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient, CustomDomain
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.domains._app import domains_app
from fastapi_cloud_cli.commands.domains.rendering import get_custom_domains_table
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class CustomDomainsListOutput(BaseModel):
    app_id: str
    domains: list[CustomDomain]
    total_count: int


def _render_custom_domains_list_output(
    data: CustomDomainsListOutput,
    toolkit: RichToolkit,
) -> None:
    toolkit.print_title("custom domains")
    toolkit.print_line()

    if not data.domains:
        toolkit.print("No custom domains found.", bullet=False)
        return

    toolkit.print(get_custom_domains_table(data.domains), bullet=False)


@domains_app.command("list", cls=UserCommand)
def list_domains(
    ctx: typer.Context,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose custom domains should be listed.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List custom domains for an app.
    """
    toolkit = get_user_command_context(ctx).toolkit
    app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

    with APIClient() as client:
        with (
            toolkit.progress(
                title="Fetching custom domains",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error fetching custom domains. Please try again later."
                ),
                not_found_message="App not found.",
                toolkit=toolkit,
            ),
        ):
            response = client.get_custom_domains(app_id=app_id)

    toolkit.success(
        CustomDomainsListOutput(
            app_id=app_id,
            domains=response.data,
            total_count=response.count,
        ),
        render_output=_render_custom_domains_list_output,
    )
