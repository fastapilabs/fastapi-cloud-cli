import logging
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.api import APIClient, DeploymentStatus
from fastapi_cloud_cli.utils.apps import get_app_config
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0


class Deployment(BaseModel):
    id: str
    app_id: str
    slug: str
    status: DeploymentStatus
    created_at: str
    url: str | None = None
    dashboard_url: str | None = None


class DeploymentsListAPIResponse(BaseModel):
    data: list[Deployment]
    count: int


class DeploymentsListOutput(BaseModel):
    deployments: list[Deployment]
    total_count: int
    limit: int
    offset: int


class DeploymentGetOutput(BaseModel):
    deployment: Deployment


def _get_deployments(
    client: APIClient, *, app_id: str, limit: int, offset: int
) -> DeploymentsListOutput:
    response = client.get(
        f"/apps/{app_id}/deployments/",
        params={
            "limit": limit,
            "skip": offset,
        },
    )
    response.raise_for_status()

    data = DeploymentsListAPIResponse.model_validate(response.json())

    return DeploymentsListOutput(
        deployments=data.data,
        total_count=data.count,
        limit=limit,
        offset=offset,
    )


def _get_deployment(
    client: APIClient, *, app_id: str, deployment_id: str
) -> DeploymentGetOutput:
    response = client.get(f"/apps/{app_id}/deployments/{deployment_id}")
    response.raise_for_status()

    return DeploymentGetOutput(deployment=Deployment.model_validate(response.json()))


def _render_deployments_list_output(
    data: DeploymentsListOutput, toolkit: RichToolkit
) -> None:
    toolkit.console.print(Padding(Text(" deployments ", style="tag"), (0, 0, 0, 1)))
    toolkit.console.print()

    if not data.deployments:
        toolkit.console.print(Padding("No deployments found.", (0, 0, 0, 2)))
        return

    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column("ID", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_row("[bold]ID[/bold]", "[bold]Status[/bold]")
    table.add_row("", "")

    for deployment in data.deployments:
        table.add_row(
            deployment.id,
            deployment.status.value,
        )

    toolkit.console.print(Padding(table, (0, 0, 0, 2)))


def _render_deployment_get_output(
    data: DeploymentGetOutput, toolkit: RichToolkit
) -> None:
    deployment = data.deployment

    toolkit.print(f"[bold]{deployment.id}[/bold]", tag="deployment")
    toolkit.print_line()
    toolkit.print(deployment.app_id, tag="app id", tag_style="text")
    toolkit.print(deployment.slug, tag="slug", tag_style="text")
    toolkit.print(deployment.status.value, tag="status", tag_style="text")
    toolkit.print(
        deployment.url if deployment.url is not None else Text("-", style="dim"),
        tag="url",
        tag_style="text",
    )
    toolkit.print(
        (
            Text(deployment.dashboard_url, style=f"link {deployment.dashboard_url}")
            if deployment.dashboard_url is not None
            else Text("-", style="dim")
        ),
        tag="dashboard",
        tag_style="text",
    )


def _get_app_id(app_id: str | None) -> str | None:
    if app_id is not None:
        return app_id

    app_config = get_app_config(Path.cwd())
    if app_config is None:
        return None

    return app_config.app_id


deployments_app = typer.Typer(no_args_is_help=True)


@deployments_app.command("get")
def get_deployment(
    deployment_id: Annotated[
        str,
        typer.Argument(
            help="ID of the deployment to return.",
        ),
    ],
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app that owns the deployment.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Get a FastAPI Cloud deployment by ID.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        target_app_id = _get_app_id(app_id)
        if target_app_id is None:
            toolkit.fail(
                "missing_required_input",
                "App ID is required.",
                hint="Pass --app-id or run `fastapi cloud apps create --link` first.",
            )
        assert target_app_id is not None

        with APIClient() as client:
            with toolkit.progress(
                title="Fetching deployment",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error fetching deployment. Please try again later.",
                    not_found_message="Deployment not found.",
                    toolkit=toolkit,
                ):
                    result = _get_deployment(
                        client,
                        app_id=target_app_id,
                        deployment_id=deployment_id,
                    )

        toolkit.success(result, render_output=_render_deployment_get_output)


@deployments_app.command("list")
def list_deployments(
    app_id: Annotated[
        str | None,
        typer.Option(
            "--app-id",
            help="ID of the app whose deployments should be listed.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            help="Maximum number of deployments to return.",
            min=1,
        ),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        typer.Option(
            "--offset",
            help="Offset into the deployment result set.",
            min=0,
        ),
    ] = DEFAULT_OFFSET,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    List FastAPI Cloud deployments for an app.
    """
    identity = Identity()

    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not identity.is_logged_in():
            toolkit.fail(
                "not_logged_in",
                "No credentials found.",
                hint="Run `fastapi cloud login` or set FASTAPI_CLOUD_TOKEN.",
            )

        target_app_id = _get_app_id(app_id)
        if target_app_id is None:
            toolkit.fail(
                "missing_required_input",
                "App ID is required.",
                hint="Pass --app-id or run `fastapi cloud apps create --link` first.",
            )
        assert target_app_id is not None

        with APIClient() as client:
            with toolkit.progress(
                title="Fetching deployments",
                transient=True,
            ) as progress:
                with client.handle_http_errors(
                    progress,
                    default_message="Error fetching deployments. Please try again later.",
                    not_found_message="App not found.",
                    toolkit=toolkit,
                ):
                    result = _get_deployments(
                        client,
                        app_id=target_app_id,
                        limit=limit,
                        offset=offset,
                    )

        toolkit.success(result, render_output=_render_deployments_list_output)
