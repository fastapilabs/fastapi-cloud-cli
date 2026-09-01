import typer

from fastapi_cloud_cli.commands.domains.add import add_domain
from fastapi_cloud_cli.commands.domains.get import get_domain
from fastapi_cloud_cli.commands.domains.list import list_domains

domains_app = typer.Typer(
    no_args_is_help=True,
    help="Manage the custom domains of your app.",
)
domains_app.command("add")(add_domain)
domains_app.command("get")(get_domain)
domains_app.command("list")(list_domains)

__all__ = ["domains_app"]
