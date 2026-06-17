import typer

from fastapi_cloud_cli.commands.env.delete import delete
from fastapi_cloud_cli.commands.env.get import get_variable
from fastapi_cloud_cli.commands.env.list import list_variables
from fastapi_cloud_cli.commands.env.set import set

env_app = typer.Typer(
    no_args_is_help=True,
    help="Manage the environment variables of your app.",
)
env_app.command("list")(list_variables)
env_app.command("get")(get_variable)
env_app.command()(delete)
env_app.command()(set)

__all__ = ["env_app"]
