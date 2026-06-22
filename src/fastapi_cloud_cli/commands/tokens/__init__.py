import typer

from fastapi_cloud_cli.commands.tokens.list import list_tokens

tokens_app = typer.Typer(
    no_args_is_help=True,
    help="Manage deploy tokens for your app.",
)
tokens_app.command("list")(list_tokens)

__all__ = ["tokens_app"]
