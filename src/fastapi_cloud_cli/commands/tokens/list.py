from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class DeployToken(BaseModel):
    id: str
    name: str
    created_at: str
    expired_at: str


class DeployTokensListAPIResponse(BaseModel):
    data: list[DeployToken]


class DeployTokensListOutput(BaseModel):
    app_id: str
    tokens: list[DeployToken]


def _get_deploy_tokens(client: APIClient, app_id: str) -> DeployTokensListAPIResponse:
    response = client.get(f"/apps/{app_id}/tokens")
    response.raise_for_status()

    return DeployTokensListAPIResponse.model_validate(response.json())


def _get_deploy_tokens_table(tokens: list[DeployToken]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Expiration", no_wrap=True)
    table.add_column("ID", no_wrap=True, overflow="ignore")
    table.add_row(
        Text("Name", style="bold"),
        Text("Expiration", style="bold"),
        Text("ID", style="bold"),
    )
    table.add_row("", "", "")

    for token in tokens:
        table.add_row(
            Text(token.name),
            Text(token.expired_at[:10], style="dim"),
            Text(token.id),
        )

    return table


def _render_deploy_tokens_list_output(
    data: DeployTokensListOutput, toolkit: RichToolkit
) -> None:
    toolkit.print_title("deploy tokens")
    toolkit.print_line()

    if not data.tokens:
        toolkit.print("No deploy tokens found.", bullet=False)
        return

    toolkit.print(_get_deploy_tokens_table(data.tokens), bullet=False)


def list_tokens(
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose deploy tokens should be listed.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List deploy tokens for an app.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        target_app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

        with APIClient() as client:
            with toolkit.progress(
                title="Fetching deploy tokens",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error fetching deploy tokens. Please try again later.",
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ):
                    tokens = _get_deploy_tokens(client=client, app_id=target_app_id)

        toolkit.success(
            DeployTokensListOutput(app_id=target_app_id, tokens=tokens.data),
            render_output=_render_deploy_tokens_list_output,
        )
