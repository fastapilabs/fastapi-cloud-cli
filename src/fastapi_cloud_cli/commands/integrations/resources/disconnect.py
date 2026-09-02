from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit
from rich_toolkit.menu import Option

from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.commands._auth import UserCommand, get_user_command_context
from fastapi_cloud_cli.commands.integrations.resources._app import resources_app
from fastapi_cloud_cli.commands.integrations.resources.get import _get_resource
from fastapi_cloud_cli.commands.integrations.resources.list import _get_resources
from fastapi_cloud_cli.commands.integrations.resources.providers import PROVIDER_NAMES
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class ResourceDisconnectOutput(BaseModel):
    app_id: str
    resource_id: str
    disconnected: bool = True
    resource_name: Annotated[str, Field(exclude=True)]
    environment_variables: Annotated[list[str], Field(exclude=True)]


def _disconnect_resource(
    client: APIClient,
    *,
    app_id: str,
    resource_id: str,
) -> None:
    response = client.delete(f"/apps/{app_id}/connected-resources/{resource_id}")
    response.raise_for_status()


def _print_disconnect_warning(
    toolkit: RichToolkit,
    *,
    provider_name: str,
    environment_variables: list[str],
) -> None:
    if environment_variables:
        variable_label = "variable" if len(environment_variables) == 1 else "variables"
        environment_variable_warning = (
            f"The managed environment {variable_label} "
            f"[bold]{', '.join(environment_variables)}[/bold] will be removed "
            "from the app."
        )
    else:
        environment_variable_warning = (
            "Managed environment variables will be removed from the app."
        )

    toolkit.print(
        f"{environment_variable_warning} "
        f"The {provider_name} resource itself will not be deleted.",
        emoji="💡",
    )


def _render_resource_disconnect_output(
    data: ResourceDisconnectOutput,
    toolkit: RichToolkit,
) -> None:
    toolkit.print(
        f"Disconnected [bold]{data.resource_name}[/bold] from the app.",
        emoji="🔌",
    )

    if data.environment_variables:
        toolkit.print_line()
        toolkit.print(
            "Removed managed environment variables: "
            f"[bold]{', '.join(data.environment_variables)}[/bold]."
        )


@resources_app.command("disconnect", cls=UserCommand)
def disconnect_resource(
    ctx: typer.Context,
    resource_id: Annotated[
        str | None,
        typer.Argument(
            help="ID of the connected resource to disconnect.",
        ),
    ] = None,
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app that owns the connected resource.",
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Confirm disconnection without prompting.",
        ),
    ] = False,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Disconnect a provider resource from an app.

    The provider resource is not deleted, but its managed environment variables
    are removed from the app.
    """

    toolkit = get_user_command_context(ctx).toolkit

    app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)
    resource_id_was_provided = resource_id is not None

    if json_output:
        if resource_id is None:
            toolkit.fail(
                "missing_required_input",
                "Resource ID is required.",
                hint="Pass RESOURCE_ID to choose a connected resource.",
            )

        if not yes:
            toolkit.fail(
                "missing_required_input",
                "Disconnection confirmation is required.",
                hint="Pass --yes to confirm disconnection.",
            )

    with APIClient() as client:
        if resource_id is None:
            with (
                toolkit.progress(
                    title="Fetching connected resources",
                    transient=True,
                ) as progress,
                client.handle_http_errors(
                    progress,
                    default_message=(
                        "Error fetching connected resources. Please try again later."
                    ),
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ),
            ):
                resources = _get_resources(client, app_id=app_id)

            toolkit.print_title("disconnect resource")
            toolkit.print_line()

            if not resources:
                toolkit.print("No connected resources found.", bullet=False)
                return

            resource_id = toolkit.ask(
                "Select the resource to disconnect:",
                options=[
                    Option(
                        {
                            "name": (
                                f"{resource.name} ({PROVIDER_NAMES[resource.provider]})"
                            ),
                            "value": resource.id,
                        }
                    )
                    for resource in resources
                ],
                bullet=False,
            )
            toolkit.print_line()

        with (
            toolkit.progress(
                title="Fetching connected resource",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error fetching connected resource. Please try again later."
                ),
                not_found_message="Connected resource not found.",
                toolkit=toolkit,
            ),
        ):
            resource = _get_resource(
                client,
                app_id=app_id,
                resource_id=resource_id,
            )

        if resource_id_was_provided:
            toolkit.print_title("disconnect resource")
            toolkit.print_line()

        _print_disconnect_warning(
            toolkit,
            provider_name=PROVIDER_NAMES[resource.provider],
            environment_variables=resource.environment_variables,
        )

        if not yes:
            toolkit.print_line()
            should_disconnect = toolkit.confirm(
                f"Disconnect [bold]{resource.name}[/bold]?",
                default=False,
                bullet=False,
            )
            if not should_disconnect:
                toolkit.print_line()
                toolkit.print("Disconnection cancelled.", bullet=False)
                raise typer.Exit(0)

        toolkit.print_line()
        with (
            toolkit.progress(
                title="Disconnecting connected resource",
                transient=True,
            ) as progress,
            client.handle_http_errors(
                progress,
                default_message=(
                    "Error disconnecting connected resource. Please try again later."
                ),
                not_found_message="Connected resource not found.",
                toolkit=toolkit,
            ),
        ):
            _disconnect_resource(
                client,
                app_id=app_id,
                resource_id=resource.id,
            )

    toolkit.success(
        ResourceDisconnectOutput(
            app_id=app_id,
            resource_id=resource.id,
            resource_name=resource.name,
            environment_variables=resource.environment_variables,
        ),
        render_output=_render_resource_disconnect_output,
    )
