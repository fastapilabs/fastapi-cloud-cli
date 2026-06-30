import logging
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.deploy.archive import validate_app_directory
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class UpdatedApp(BaseModel):
    id: str
    team_id: str
    slug: str
    name: str
    directory: str | None


class AppsUpdateOutput(BaseModel):
    app: UpdatedApp


def _update_app(client: APIClient, *, app_id: str, directory: str | None) -> UpdatedApp:
    response = client.patch(
        f"/apps/{app_id}",
        json={"directory": directory},
    )
    response.raise_for_status()

    return UpdatedApp.model_validate(response.json())


def _render_apps_update_output(data: AppsUpdateOutput, toolkit: RichToolkit) -> None:
    toolkit.print(f"Updated app [bold]{data.app.name}[/bold]", bullet=False)
    toolkit.print(
        f"Directory: [bold]{data.app.directory if data.app.directory is not None else '.'}[/bold]",
        bullet=False,
    )


def update_app(
    app_id: Annotated[
        str | None,
        typer.Argument(
            help="ID of the app to update (defaults to the app linked to the current directory).",
        ),
    ] = None,
    directory: Annotated[
        str | None,
        typer.Option(
            "--directory",
            help=(
                "Relative app directory containing the pyproject.toml "
                "(for example: src or backend)."
            ),
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Update FastAPI Cloud app metadata.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        if directory is None:
            toolkit.fail(
                "missing_required_input",
                "No updates provided.",
                hint="Pass --directory to update the app directory.",
            )

        target_app_id = resolve_app_id_or_fail(
            toolkit,
            app_id=app_id,
            hint="Pass an app ID or run `fastapi cloud apps create --link` first.",
        )

        try:
            directory = validate_app_directory(directory)
        except ValueError as e:
            toolkit.fail(
                "invalid_input",
                f"Invalid app directory: {e}",
                hint="Pass a relative app directory such as `src` or `backend`.",
            )

        with APIClient() as client:
            with toolkit.progress(
                title="Updating app",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error updating app. Please try again later.",
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ):
                    app = _update_app(
                        client,
                        app_id=target_app_id,
                        directory=directory,
                    )

        toolkit.success(
            AppsUpdateOutput(app=app),
            render_output=_render_apps_update_output,
        )
