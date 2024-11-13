import typer

from .commands.deploy import deploy
from .commands.env import env_app
from .commands.login import login
from .commands.whoami import whoami

app = typer.Typer(rich_markup_mode="rich")


# TODO: use the app structure

# Additional commands
app.command()(deploy)
app.command()(login)
app.command()(whoami)

app.add_typer(env_app, name="env")


def main() -> None:
    app()
