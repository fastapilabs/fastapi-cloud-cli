from typing import Annotated

import typer
from rich import print

from . import __version__
from .commands.apps import apps_app
from .commands.apps.link import link_app
from .commands.apps.unlink import unlink_app
from .commands.auth import auth_app
from .commands.ci import ci_app
from .commands.deploy import deploy
from .commands.deployments import deployments_app
from .commands.env import env_app
from .commands.login import login
from .commands.logout import logout
from .commands.logs import logs
from .commands.setup_ci import setup_ci
from .commands.teams import teams_app
from .commands.tokens import tokens_app
from .commands.whoami import whoami
from .logging import setup_logging
from .utils.sentry import init_sentry

setup_logging()

app = typer.Typer(rich_markup_mode="rich")


def version_callback(value: bool) -> None:
    if value:
        print(f"FastAPI Cloud CLI version: [green]{__version__}[/green]")
        raise typer.Exit()


cloud_app = typer.Typer(
    rich_markup_mode="rich",
    help="Manage [bold]FastAPI[/bold] Cloud deployments.",
    no_args_is_help=True,
)


@cloud_app.callback()
def cloud_main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None: ...


# TODO: use the app structure

# Additional commands

# fastapi cloud [command]
cloud_app.command()(deploy)
cloud_app.command("link")(link_app)
cloud_app.command()(login)
cloud_app.command()(logs)
cloud_app.command()(logout)
cloud_app.command()(whoami)
cloud_app.command("unlink")(unlink_app)
cloud_app.command()(setup_ci)

cloud_app.add_typer(env_app, name="env")
cloud_app.add_typer(auth_app, name="auth")
cloud_app.add_typer(apps_app, name="apps")
cloud_app.add_typer(ci_app, name="ci")
cloud_app.add_typer(deployments_app, name="deployments")
cloud_app.add_typer(teams_app, name="teams")
cloud_app.add_typer(tokens_app, name="tokens")

# fastapi [command]
app.command()(deploy)
app.command()(login)

app.add_typer(cloud_app, name="cloud")


def main() -> None:
    init_sentry()
    app()
