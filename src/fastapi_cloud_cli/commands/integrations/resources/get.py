from typing import Annotated, Any, Literal

import typer
from pydantic import BaseModel, Field
from rich.console import RenderableType
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.integrations.resources.providers import (
    PROVIDER_NAMES,
    Provider,
)
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.apps import resolve_app_id_or_fail
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_details_table, get_rich_toolkit
from fastapi_cloud_cli.utils.dates import format_last_updated
from fastapi_cloud_cli.utils.execution import JsonOutputOption

DatabaseProvider = Literal["neon", "redis", "supabase"]


class DatabaseProviderMetadata(BaseModel):
    type: DatabaseProvider
    database_name: str


class LogfireProviderMetadata(BaseModel):
    type: Literal["logfire"]
    project_name: str
    organization_name: str


ProviderMetadata = Annotated[
    DatabaseProviderMetadata | LogfireProviderMetadata,
    Field(discriminator="type"),
]


class EnvironmentVariable(BaseModel):
    name: str


class ConnectedResourceAPIResponse(BaseModel):
    id: str
    name: str
    provider_metadata: ProviderMetadata
    console_url: str
    environment_variables: list[EnvironmentVariable]
    created_at: str
    updated_at: str


class ConnectedResourceBase(BaseModel):
    id: str
    name: str
    provider: Provider
    console_url: str
    environment_variables: list[str]
    created_at: str
    updated_at: str


class DatabaseConnectedResource(ConnectedResourceBase):
    provider: DatabaseProvider
    database_name: str


class LogfireConnectedResource(ConnectedResourceBase):
    provider: Literal["logfire"]
    project_name: str
    organization_name: str


ConnectedResource = DatabaseConnectedResource | LogfireConnectedResource


class ResourceGetOutput(BaseModel):
    app_id: str
    resource: ConnectedResource


def _to_connected_resource(
    resource: ConnectedResourceAPIResponse,
) -> ConnectedResource:
    metadata = resource.provider_metadata
    environment_variables = [
        variable.name for variable in resource.environment_variables
    ]

    match metadata:
        case DatabaseProviderMetadata():
            return DatabaseConnectedResource(
                id=resource.id,
                name=resource.name,
                provider=metadata.type,
                database_name=metadata.database_name,
                console_url=resource.console_url,
                environment_variables=environment_variables,
                created_at=resource.created_at,
                updated_at=resource.updated_at,
            )
        case LogfireProviderMetadata():
            return LogfireConnectedResource(
                id=resource.id,
                name=resource.name,
                provider=metadata.type,
                project_name=metadata.project_name,
                organization_name=metadata.organization_name,
                console_url=resource.console_url,
                environment_variables=environment_variables,
                created_at=resource.created_at,
                updated_at=resource.updated_at,
            )


def _get_resource(
    client: APIClient,
    *,
    app_id: str,
    resource_id: str,
) -> ConnectedResource:
    response = client.get(f"/apps/{app_id}/connected-resources/{resource_id}")
    response.raise_for_status()

    resource = ConnectedResourceAPIResponse.model_validate(response.json())
    return _to_connected_resource(resource)


def _render_resource_get_output(
    data: ResourceGetOutput,
    toolkit: RichToolkit,
) -> None:
    resource = data.resource

    toolkit.print_title("connected resource")
    toolkit.print_line()
    toolkit.print(Text(resource.name, style="bold"), emoji="🔌")
    toolkit.print_line()

    rows: list[tuple[str, RenderableType]] = [
        ("id", resource.id),
        ("provider", PROVIDER_NAMES[resource.provider]),
    ]

    match resource:
        case DatabaseConnectedResource():
            rows.append(("database", resource.database_name))
        case LogfireConnectedResource():
            rows.extend(
                [
                    ("project", resource.project_name),
                    ("organization", resource.organization_name),
                ]
            )

    rows.extend(
        [
            (
                "console",
                Text(resource.console_url, style=f"link {resource.console_url}"),
            ),
            (
                "environment variables",
                Text("\n".join(resource.environment_variables))
                if resource.environment_variables
                else Text("-", style="dim"),
            ),
            ("connected", format_last_updated(resource.created_at)),
            ("last updated", format_last_updated(resource.updated_at)),
        ]
    )

    toolkit.print(get_details_table(rows))


def get_resource(
    resource_id: Annotated[
        str,
        typer.Argument(help="ID of the connected resource to return."),
    ],
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app that owns the connected resource.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get a resource connected to an app.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        app_id = resolve_app_id_or_fail(toolkit, app_id=app_id)

        with APIClient() as client:
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

        toolkit.success(
            ResourceGetOutput(app_id=app_id, resource=resource),
            render_output=_render_resource_get_output,
        )
