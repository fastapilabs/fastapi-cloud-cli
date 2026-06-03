import logging
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.markup import escape
from rich.table import Table
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.teams.get import (
    Team,
    TeamOutput,
    build_team_output,
    get_team,
)
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0


class TeamsListAPIResponse(BaseModel):
    data: list[Team]
    count: int


class TeamsListOutput(BaseModel):
    teams: list[TeamOutput]
    total_count: int
    limit: int
    offset: int


def _get_teams(client: APIClient, *, limit: int, offset: int) -> TeamsListOutput:
    settings = Settings.get()

    response = client.get(
        "/teams/",
        params={
            "limit": limit,
            "skip": offset,
        },
    )
    response.raise_for_status()

    data = TeamsListAPIResponse.model_validate(response.json())

    return TeamsListOutput(
        teams=[build_team_output(team, settings) for team in data.data],
        total_count=data.count,
        limit=limit,
        offset=offset,
    )


def _render_teams_list_output(data: TeamsListOutput, toolkit: RichToolkit) -> None:
    if not data.teams:
        toolkit.print("No teams found.", tag="teams")
        return

    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Name")
    table.add_column("ID")
    table.add_row("[bold]Name[/bold]", "[bold]ID[/bold]")
    table.add_row("", "")

    for team in data.teams:
        table.add_row(
            f"[link={team.dashboard_url}]{escape(team.name)}[/link]",
            team.id,
        )

    toolkit.print(table, tag="teams")


teams_app = typer.Typer(no_args_is_help=True)


@teams_app.command("list")
def list_teams(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum number of teams to return.",
            min=1,
        ),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        typer.Option(
            "--offset",
            help="Offset into the team result set.",
            min=0,
        ),
    ] = DEFAULT_OFFSET,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List FastAPI Cloud teams.
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
            with toolkit.progress(
                title="Fetching teams",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error fetching teams. Please try again later.",
                    toolkit=toolkit,
                ):
                    result = _get_teams(client, limit=limit, offset=offset)

        toolkit.success(result, render_output=_render_teams_list_output)


teams_app.command("get")(get_team)
