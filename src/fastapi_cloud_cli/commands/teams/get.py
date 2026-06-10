import logging
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_details_table, get_rich_toolkit
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


def get_team(
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
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

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
