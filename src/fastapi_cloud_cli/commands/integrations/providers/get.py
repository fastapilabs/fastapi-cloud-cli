from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.integrations.models import PROVIDER_NAMES, Provider
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_details_table, get_rich_toolkit
from fastapi_cloud_cli.utils.dates import format_last_updated
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class ConnectedIntegration(BaseModel):
    id: str
    provider: Provider = Field(validation_alias="type")
    created_at: str


class ConnectedResourceApp(BaseModel):
    id: str
    name: str


class ConnectedResource(BaseModel):
    id: str
    name: str
    app: ConnectedResourceApp
    created_at: str


class ConnectedResourcesAPIResponse(BaseModel):
    data: list[ConnectedResource]


class ProviderGetOutput(BaseModel):
    integration: ConnectedIntegration
    resources: list[ConnectedResource]


def _get_integration(
    client: APIClient,
    *,
    integration_id: str,
) -> ConnectedIntegration:
    response = client.get(f"/integrations/{integration_id}")
    response.raise_for_status()

    return ConnectedIntegration.model_validate(response.json())


def _get_connected_resources(
    client: APIClient,
    *,
    integration_id: str,
) -> list[ConnectedResource]:
    response = client.get(f"/integrations/{integration_id}/connected-resources")
    response.raise_for_status()

    return ConnectedResourcesAPIResponse.model_validate(response.json()).data


def _get_connected_resources_table(resources: list[ConnectedResource]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("App", no_wrap=True)
    table.add_column("Resource ID", no_wrap=True, overflow="ignore")
    table.add_column("Connected", no_wrap=True)
    table.add_row(
        Text("Name", style="bold"),
        Text("App", style="bold"),
        Text("Resource ID", style="bold"),
        Text("Connected", style="bold"),
    )
    table.add_row("", "", "", "")

    for resource in resources:
        table.add_row(
            Text(resource.name),
            Text(resource.app.name, style="dim"),
            Text(resource.id),
            Text(format_last_updated(resource.created_at), style="dim"),
        )

    return table


def _render_provider_get_output(
    data: ProviderGetOutput,
    toolkit: RichToolkit,
) -> None:
    integration = data.integration

    toolkit.print_title("integration")
    toolkit.print_line()
    toolkit.print(
        Text(PROVIDER_NAMES[integration.provider], style="bold"),
        emoji="🔌",
    )
    toolkit.print_line()
    toolkit.print(
        get_details_table(
            [
                ("id", integration.id),
                ("provider", PROVIDER_NAMES[integration.provider]),
                ("connected", format_last_updated(integration.created_at)),
            ]
        )
    )
    toolkit.print_line()
    toolkit.print_title("connected resources")
    toolkit.print_line()

    if not data.resources:
        toolkit.print("No connected resources found.", bullet=False)
        return

    toolkit.print(_get_connected_resources_table(data.resources), bullet=False)


def get_provider(
    integration_id: Annotated[
        str,
        typer.Argument(help="ID of the connected integration to return."),
    ],
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get a connected integration and its resources.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        with APIClient() as client:
            with (
                toolkit.progress(
                    title="Fetching integration details",
                    transient=True,
                ) as progress,
                client.handle_http_errors(
                    progress,
                    default_message=(
                        "Error fetching integration details. Please try again later."
                    ),
                    not_found_message="Integration not found.",
                    toolkit=toolkit,
                ),
            ):
                integration = _get_integration(
                    client,
                    integration_id=integration_id,
                )
                resources = _get_connected_resources(
                    client,
                    integration_id=integration_id,
                )

        toolkit.success(
            ProviderGetOutput(
                integration=integration,
                resources=resources,
            ),
            render_output=_render_provider_get_output,
        )
