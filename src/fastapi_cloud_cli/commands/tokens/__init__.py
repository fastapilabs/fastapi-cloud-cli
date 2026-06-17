import typer

from fastapi_cloud_cli.commands.tokens.create import create_token
from fastapi_cloud_cli.commands.tokens.delete import delete_token
from fastapi_cloud_cli.commands.tokens.list import list_tokens

tokens_app = typer.Typer(
    no_args_is_help=True,
    help="Manage deploy tokens for your app.",
)
tokens_app.command("create")(create_token)
tokens_app.command("delete")(delete_token)
tokens_app.command("list")(list_tokens)

__all__ = ["tokens_app"]
