import logging
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option

from fastapi_cloud_cli.config import Settings
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0


class App(BaseModel):
    id: str
    team_id: str
    slug: str
    name: str
    directory: str | None
    url: str | None = None
    region: str | None = None
    updated_at: str | None = None


class Team(BaseModel):
    id: str
    slug: str
    name: str


class AppsListAPIResponse(BaseModel):
    data: list[App]
    count: int


class AppsListOutput(BaseModel):
    apps: list[App]
    total_count: int
    limit: int
    offset: int
    team_slug: Annotated[str, Field(exclude=True)]


def _get_app_dashboard_url(app: App, *, team_slug: str, settings: Settings) -> str:
    return f"{settings.dashboard_base_url}/{team_slug}/apps/{app.slug}"


def _format_app_name(app: App, *, team_slug: str, settings: Settings) -> str:
    dashboard_url = _get_app_dashboard_url(
        app,
        team_slug=team_slug,
        settings=settings,
    )
    return f"[link={dashboard_url}]{app.name}[/link]"


def _get_apps_list_table(
    apps: list[App], *, team_slug: str, settings: Settings
) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("ID", no_wrap=True, overflow="ignore")
    table.add_row(
        "[bold]Name[/bold]",
        "[bold]ID[/bold]",
    )
    table.add_row("", "")

    for app in apps:
        table.add_row(
            _format_app_name(app, team_slug=team_slug, settings=settings),
            Text(app.id),
        )

    return table


def _get_teams(client: APIClient) -> list[Team]:
    response = client.get("/teams/")
    response.raise_for_status()

    data = response.json()["data"]

    return [Team.model_validate(team) for team in data]


def _get_team(client: APIClient, team_id: str) -> Team:
    response = client.get(f"/teams/{team_id}")
    response.raise_for_status()

    return Team.model_validate(response.json())


def _get_app(client: APIClient, app_id: str) -> App:
    response = client.get(f"/apps/{app_id}")
    response.raise_for_status()

    return App.model_validate(response.json())


def _get_apps(
    client: APIClient, *, team_id: str, limit: int, offset: int, team_slug: str
) -> AppsListOutput:
    response = client.get(
        "/apps/",
        params={
            "team_id": team_id,
            "limit": limit,
            "skip": offset,
        },
    )
    response.raise_for_status()

    data = AppsListAPIResponse.model_validate(response.json())

    return AppsListOutput(
        apps=data.data,
        total_count=data.count,
        limit=limit,
        offset=offset,
        team_slug=team_slug,
    )


def _render_apps_list_output(data: AppsListOutput, toolkit: RichToolkit) -> None:
    toolkit.print_title("apps")
    toolkit.print_line()

    if not data.apps:
        toolkit.print("No apps found.", bullet=False)
        return

    toolkit.print(
        _get_apps_list_table(
            data.apps,
            team_slug=data.team_slug,
            settings=Settings.get(),
        ),
        bullet=False,
    )


def _prompt_for_team(toolkit: FastAPIRichToolkit, client: APIClient) -> Team:
    with toolkit.progress(
        title="Fetching teams",
        transient=True,
    ) as progress:
        with client.handle_http_errors(
            progress,
            default_message="Error fetching teams. Please try again later.",
            toolkit=toolkit,
        ):
            teams = _get_teams(client)

    if not teams:
        toolkit.fail(
            "missing_required_input",
            "No teams found.",
            hint="Create a team before listing apps.",
        )

    return toolkit.ask(
        "Select the team:",
        options=[
            Option({"name": team.name, "value": team})
            for team in sorted(teams, key=lambda team: team.name.lower())
        ],
        allow_filtering=True,
        bullet=False,
    )


def list_apps(
    team_id: Annotated[
        str | None,
        typer.Option(
            "--team-id",
            help="ID of the team whose apps should be listed.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum number of apps to return.",
            min=1,
        ),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        typer.Option(
            "--offset",
            help="Offset into the app result set.",
            min=0,
        ),
    ] = DEFAULT_OFFSET,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List FastAPI Cloud apps.
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
            team_slug: str | None = None

            if team_id is None:
                if json_output:
                    toolkit.fail(
                        "missing_required_input",
                        "Team ID is required.",
                        hint="Pass --team-id to choose a team.",
                    )

                team = _prompt_for_team(toolkit, client)
                team_id = team.id
                team_slug = team.slug

                toolkit.print_line()
            else:
                with toolkit.progress(
                    title="Fetching team",
                    transient=True,
                ) as progress:
                    with client.handle_http_errors(
                        progress,
                        default_message="Error fetching team. Please try again later.",
                        not_found_message="Team not found.",
                        toolkit=toolkit,
                    ):
                        team = _get_team(client, team_id)
                        team_slug = team.slug

            with toolkit.progress(
                title="Fetching apps",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error fetching apps. Please try again later.",
                    toolkit=toolkit,
                ):
                    result = _get_apps(
                        client,
                        team_id=team_id,
                        limit=limit,
                        offset=offset,
                        team_slug=team_slug,
                    )

        toolkit.success(result, render_output=_render_apps_list_output)
