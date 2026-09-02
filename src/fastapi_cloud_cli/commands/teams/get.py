import logging
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.teams._app import teams_app
from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.cli import get_details_table
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class Team(BaseModel):
    id: str
    slug: str
    name: str


class TeamGetOutput(BaseModel):
    team: Team


def _get_team_dashboard_url(team: Team, *, settings: Settings) -> str:
    return f"{settings.dashboard_base_url}/{team.slug}/apps"


def _get_team(client: APIClient, team_id: str) -> TeamGetOutput:
    response = client.get(f"/teams/{team_id}")
    response.raise_for_status()

    team = Team.model_validate(response.json())

    return TeamGetOutput(team=team)


def _render_team_get_output(data: TeamGetOutput, toolkit: RichToolkit) -> None:
    toolkit.print(f"[bold]{data.team.name}[/bold]", emoji="🏢")
    toolkit.print_line()
    toolkit.print(
        get_details_table(
            [
                ("id", data.team.id),
                ("slug", data.team.slug),
                ("url", _get_team_dashboard_url(data.team, settings=Settings.get())),
            ]
        )
    )


@teams_app.command("get", cls=UserCommand)
def get_team(
    ctx: typer.Context,
    team_id: Annotated[
        str,
        typer.Argument(
            help="ID of the team to return.",
        ),
    ],
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get a FastAPI Cloud team by ID.
    """

    toolkit = get_user_command_context(ctx).toolkit

    with (
        APIClient() as client,
        toolkit.progress(
            title="Fetching team",
            transient=True,
        ) as progress,
    ):
        with client.handle_http_errors(
            progress,
            default_message="Error fetching team. Please try again later.",
            not_found_message="Team not found.",
            toolkit=toolkit,
        ):
            result = _get_team(client, team_id)

    toolkit.success(result, render_output=_render_team_get_output)
