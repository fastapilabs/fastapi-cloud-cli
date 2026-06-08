import typer

from fastapi_cloud_cli.commands.apps.get import get_app
from fastapi_cloud_cli.commands.apps.list import list_apps

apps_app = typer.Typer(no_args_is_help=True)
apps_app.command("get")(get_app)
apps_app.command("list")(list_apps)

__all__ = ["apps_app"]
