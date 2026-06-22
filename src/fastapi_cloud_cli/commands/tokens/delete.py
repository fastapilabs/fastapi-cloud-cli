from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
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


def delete_token(
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
