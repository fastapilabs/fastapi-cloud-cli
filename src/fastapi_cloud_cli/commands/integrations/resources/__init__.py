import typer

from fastapi_cloud_cli.commands.integrations.resources.connect import connect_resource
from fastapi_cloud_cli.commands.integrations.resources.disconnect import (
    disconnect_resource,
)
from fastapi_cloud_cli.commands.integrations.resources.get import get_resource
from fastapi_cloud_cli.commands.integrations.resources.list import list_resources

resources_app = typer.Typer(
    no_args_is_help=True,
    help="Manage resources connected to an app.",
)
resources_app.command("connect")(connect_resource)
resources_app.command("disconnect")(disconnect_resource)
resources_app.command("get")(get_resource)
resources_app.command("list")(list_resources)

__all__ = ["resources_app"]
