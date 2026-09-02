from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.tokens._app import tokens_app
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class DeployTokenDeleteOutput(BaseModel):
    token_id: str
    deleted: bool = True


def _delete_deploy_token(client: APIClient, *, app_id: str, token_id: str) -> bool:
    response = client.delete(f"/apps/{app_id}/tokens/{token_id}")

    if response.status_code == 404:
        return False

    response.raise_for_status()

    return True


def _render_deploy_token_delete_output(
    data: DeployTokenDeleteOutput, toolkit: RichToolkit
) -> None:
    toolkit.print(
        f"Deleted deploy token [bold]{data.token_id}[/bold]",
        bullet=False,
    )


@tokens_app.command("delete", cls=UserCommand)
def delete_token(
    ctx: typer.Context,
    token_id: Annotated[
        str,
        typer.Argument(
            help="ID of the deploy token to delete.",
        ),
    ],
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app that owns the deploy token.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Delete a deploy token for an app.
    """

    toolkit = get_user_command_context(ctx).toolkit

    target_app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

    with APIClient() as client:
        with toolkit.progress(
            title="Deleting deploy token",
            transient=True,
        ) as progress:
            with client.handle_http_errors(
                progress,
                default_message="Error deleting deploy token. Please try again later.",
                not_found_message="Deploy token not found.",
                toolkit=toolkit,
            ):
                deleted = _delete_deploy_token(
                    client,
                    app_id=target_app_id,
                    token_id=token_id,
                )

    if not deleted:
        message = (
            f"Deploy token {token_id} not found."
            if toolkit.mode == "json"
            else "Deploy token not found."
        )
        toolkit.fail(
            "not_found",
            message,
            hint="Run `fastapi cloud tokens list` to see available deploy tokens.",
        )

    toolkit.success(
        DeployTokenDeleteOutput(token_id=token_id),
        render_output=_render_deploy_token_delete_output,
    )
