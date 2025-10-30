import typer

from .commands.deploy import deploy
from .commands.env import env_app
from .commands.login import login
from .commands.logout import logout
from .commands.unlink import unlink
from .commands.whoami import whoami
from .logging import setup_logging
from .utils.sentry import init_sentry

setup_logging()

app = typer.Typer(rich_markup_mode="rich")

cloud_app = typer.Typer(
    rich_markup_mode="rich",
    help="Manage [bold]FastAPI[/bold] Cloud deployments. 🚀",
)

# TODO: use the app structure

# Additional commands

# fastapi cloud [command]
cloud_app.command()(deploy)
cloud_app.command()(login)
cloud_app.command()(logout)
cloud_app.command()(whoami)
cloud_app.command()(unlink)

cloud_app.add_typer(env_app, name="env")

# fastapi [command]
app.command()(deploy)
app.command()(login)

app.add_typer(cloud_app, name="cloud")


def main() -> None:
    init_sentry()
    app()
