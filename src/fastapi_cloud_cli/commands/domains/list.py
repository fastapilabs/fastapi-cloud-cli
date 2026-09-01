from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient, CustomDomain
from fastapi_cloud_cli.commands.domains.rendering import get_custom_domains_table
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
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


def list_domains(
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
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login`.",
            )

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
