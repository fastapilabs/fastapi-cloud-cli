import typer

from fastapi_cloud_cli.commands.apps.create import create_app
from fastapi_cloud_cli.commands.apps.get import get_app
from fastapi_cloud_cli.commands.apps.link import link_app
from fastapi_cloud_cli.commands.apps.list import list_apps
from fastapi_cloud_cli.commands.apps.unlink import unlink_app
from fastapi_cloud_cli.commands.logs import logs

apps_app = typer.Typer(
    no_args_is_help=True,
    help="Manage your FastAPI Cloud apps.",
)
apps_app.command("create")(create_app)
apps_app.command("get")(get_app)
apps_app.command("link")(link_app)
apps_app.command("list")(list_apps)
apps_app.command("logs")(logs)
apps_app.command("unlink")(unlink_app)

__all__ = ["apps_app"]
