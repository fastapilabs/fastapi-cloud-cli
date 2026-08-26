from pathlib import Path

from pydantic import BaseModel
from rich_toolkit.menu import Option

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit


class Team(BaseModel):
    id: str
    slug: str
    name: str


def get_teams(client: APIClient) -> list[Team]:
    response = client.get("/teams/")
    response.raise_for_status()

    return [Team.model_validate(team) for team in response.json()["data"]]


def select_team(
    toolkit: FastAPIRichToolkit,
    client: APIClient,
    *,
    empty_hint: str,
) -> Team:
    with toolkit.progress(
        title="Fetching teams",
        transient=True,
    ) as progress:
        with client.handle_http_errors(
            progress,
            default_message="Error fetching teams. Please try again later.",
            toolkit=toolkit,
        ):
            teams = get_teams(client)

    if not teams:
        toolkit.fail(
            "missing_required_input",
            "No teams found.",
            hint=empty_hint,
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


def resolve_team_id(
    toolkit: FastAPIRichToolkit,
    client: APIClient,
    *,
    team_id: str | None = None,
    path: Path | None = None,
    empty_hint: str,
) -> str:
    if team_id is not None:
        return team_id

    if app_config := get_app_config(path or Path.cwd()):
        return app_config.team_id

    if toolkit.mode == "json":
        toolkit.fail(
            "missing_required_input",
            "Team ID is required.",
            hint="Pass --team-id or run the command from a linked app.",
        )

    team = select_team(toolkit, client, empty_hint=empty_hint)
    toolkit.print_line()

    return team.id
