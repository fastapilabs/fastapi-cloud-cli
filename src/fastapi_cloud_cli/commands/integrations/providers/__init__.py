import typer

from fastapi_cloud_cli.commands.integrations.providers.get import get_provider
from fastapi_cloud_cli.commands.integrations.providers.list import list_providers

providers_app = typer.Typer(
    no_args_is_help=True,
    help="Manage integration providers for a team.",
)
providers_app.command("get")(get_provider)
providers_app.command("list")(list_providers)

__all__ = ["providers_app"]
