import typer

from fastapi_cloud_cli.commands.auth import wait as wait_command
from fastapi_cloud_cli.commands.login import login

auth_app = typer.Typer(no_args_is_help=True)

auth_app.command()(login)
auth_app.command("wait")(wait_command.wait)

__all__ = ["auth_app"]
