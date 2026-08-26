import typer

from fastapi_cloud_cli.commands.integrations.providers import providers_app
from fastapi_cloud_cli.commands.integrations.resources import resources_app

integrations_app = typer.Typer(
    no_args_is_help=True,
    help="Manage third-party integrations.",
)
integrations_app.add_typer(providers_app, name="providers")
integrations_app.add_typer(resources_app, name="resources")

__all__ = ["integrations_app"]
