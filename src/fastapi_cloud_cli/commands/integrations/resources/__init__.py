import typer

from fastapi_cloud_cli.commands.integrations.resources.list import list_resources

resources_app = typer.Typer(
    no_args_is_help=True,
    help="Manage resources connected to an app.",
)
resources_app.command("list")(list_resources)

__all__ = ["resources_app"]
