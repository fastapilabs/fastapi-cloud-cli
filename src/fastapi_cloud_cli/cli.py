import logging
from typing import Union

import typer

from .commands.deploy import deploy
from .commands.env import env_app
from .commands.login import login
from .commands.whoami import whoami
from .config import settings
from .logging import setup_logging

app = typer.Typer(rich_markup_mode="rich")


logger = logging.getLogger(__name__)


# TODO: this is not supported in Typer subapps yet, but we might not even need :)


@app.callback()
def callback(
    base_api_url: Union[str, None] = typer.Option(None, help="Base URL of the API"),
    verbose: bool = typer.Option(False, help="Enable verbose output"),
) -> None:
    """
    FastAPI CLI - The [bold]fastapi[/bold] command line app. 😎

    Manage your [bold]FastAPI[/bold] projects, run your FastAPI apps, and more.

    Read more in the docs: [link]https://fastapi.tiangolo.com/fastapi-cli/[/link].
    """
    if base_api_url:
        settings.base_api_url = base_api_url

    log_level = logging.DEBUG if verbose else logging.INFO

    setup_logging(level=log_level)


# Additional commands
app.command()(deploy)
app.command()(login)
app.command()(whoami)

app.add_typer(env_app, name="env")


def main() -> None:
    app()
