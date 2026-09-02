from typing import Annotated

import typer
from rich import print

from fastapi_cloud_cli import __version__

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
