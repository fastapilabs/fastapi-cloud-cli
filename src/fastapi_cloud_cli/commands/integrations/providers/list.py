from typing import Annotated, Any, Literal

import typer
from pydantic import BaseModel
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.integrations.providers._app import providers_app
from fastapi_cloud_cli.utils.execution import JsonOutputOption
from fastapi_cloud_cli.utils.teams import resolve_team_id

ProviderStatus = Literal["available", "coming_soon", "connected"]

STATUS_LABELS: dict[ProviderStatus, str] = {
    "available": "not connected",
    "coming_soon": "coming soon",
    "connected": "connected",
}


class ConnectedIntegration(BaseModel):
    id: str


class IntegrationProvider(BaseModel):
    id: str
    name: str
    status: ProviderStatus
    connected_integration: ConnectedIntegration | None = None


class ProvidersListAPIResponse(BaseModel):
    data: list[IntegrationProvider]


class ProvidersListOutput(BaseModel):
    team_id: str
    providers: list[IntegrationProvider]


def _get_providers(client: APIClient, *, team_id: str) -> list[IntegrationProvider]:
    response = client.get(f"/teams/{team_id}/integrations")
    response.raise_for_status()

    return ProvidersListAPIResponse.model_validate(response.json()).data


def _get_providers_table(providers: list[IntegrationProvider]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Integration ID", no_wrap=True, overflow="ignore")
    table.add_row(
        Text("Name", style="bold"),
        Text("Status", style="bold"),
        Text("Integration ID", style="bold"),
    )
    table.add_row("", "", "")

    for provider in providers:
        connected_integration = provider.connected_integration
        table.add_row(
            Text(provider.name),
            Text(
                STATUS_LABELS[provider.status],
                style="green" if provider.status == "connected" else "dim",
            ),
            Text(connected_integration.id if connected_integration else "-"),
        )

    return table


def _render_providers_list_output(
    data: ProvidersListOutput,
    toolkit: RichToolkit,
) -> None:
    toolkit.print_title("integrations")
    toolkit.print_line()

    if not data.providers:
        toolkit.print("No integration providers available.", bullet=False)
        return

    toolkit.print(_get_providers_table(data.providers), bullet=False)


@providers_app.command("list", cls=UserCommand)
def list_providers(
    ctx: typer.Context,
    team_id: Annotated[
        str | None,
        typer.Option(
            "--team-id",
            help=(
                "ID of the team whose integration providers should be listed. "
                "Defaults to the linked app's team."
            ),
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List integration providers and their connection status for a team.
    """

    toolkit = get_user_command_context(ctx).toolkit

    with APIClient() as client:
        team_id = resolve_team_id(
            toolkit,
            client,
            team_id=team_id,
            empty_hint="Create a team before listing integration providers.",
        )

        with (
            toolkit.progress(
                title="Fetching integration providers",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error fetching integration providers. Please try again later."
                ),
                not_found_message="Team not found.",
                toolkit=toolkit,
            ),
        ):
            providers = _get_providers(client, team_id=team_id)

    toolkit.success(
        ProvidersListOutput(team_id=team_id, providers=providers),
        render_output=_render_providers_list_output,
    )
