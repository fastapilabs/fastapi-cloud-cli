from typing import Annotated, Any

import typer
from pydantic import AliasPath, BaseModel, Field
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.integrations.resources._app import resources_app
from fastapi_cloud_cli.commands.integrations.resources.providers import (
    PROVIDER_NAMES,
    Provider,
)
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class ConnectedResource(BaseModel):
    id: str
    name: str
    provider: Provider = Field(validation_alias=AliasPath("provider_metadata", "type"))


class ConnectedResourcesListAPIResponse(BaseModel):
    data: list[ConnectedResource]


class ResourcesListOutput(BaseModel):
    app_id: str
    resources: list[ConnectedResource]


def _get_resources(client: APIClient, *, app_id: str) -> list[ConnectedResource]:
    response = client.get(f"/apps/{app_id}/connected-resources")
    response.raise_for_status()

    return ConnectedResourcesListAPIResponse.model_validate(response.json()).data


def _get_resources_table(resources: list[ConnectedResource]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Provider", no_wrap=True)
    table.add_column("Resource ID", no_wrap=True, overflow="ignore")
    table.add_row(
        Text("Name", style="bold"),
        Text("Provider", style="bold"),
        Text("Resource ID", style="bold"),
    )
    table.add_row("", "", "")

    for resource in resources:
        table.add_row(
            Text(resource.name),
            Text(PROVIDER_NAMES[resource.provider], style="dim"),
            Text(resource.id),
        )

    return table


def _render_resources_list_output(
    data: ResourcesListOutput,
    toolkit: RichToolkit,
) -> None:
    toolkit.print_title("connected resources")
    toolkit.print_line()

    if not data.resources:
        toolkit.print("No connected resources found.", bullet=False)
        return

    toolkit.print(_get_resources_table(data.resources), bullet=False)


@resources_app.command("list", cls=UserCommand)
def list_resources(
    ctx: typer.Context,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose connected resources should be listed.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List resources connected to an app.
    """

    toolkit = get_user_command_context(ctx).toolkit

    app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

    with APIClient() as client:
        with (
            toolkit.progress(
                title="Fetching connected resources",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error fetching connected resources. Please try again later."
                ),
                not_found_message="App not found.",
                toolkit=toolkit,
            ),
        ):
            resources = _get_resources(client, app_id=app_id)

    toolkit.success(
        ResourcesListOutput(app_id=app_id, resources=resources),
        render_output=_render_resources_list_output,
    )
