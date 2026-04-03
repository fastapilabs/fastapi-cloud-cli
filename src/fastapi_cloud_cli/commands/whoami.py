import logging
from typing import Any

from rich import print
from rich_toolkit.progress import Progress

from fastapi_cloud_cli.context import ctx
from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.cli import handle_http_errors

logger = logging.getLogger(__name__)


def whoami() -> Any:
    identity = ctx.get_identity()

    if not identity.is_logged_in():
        print("No credentials found. Use [blue]`fastapi login`[/] to login.")
    else:
        with APIClient() as client:
            with Progress(title="⚡ Fetching profile", transient=True) as progress:
                with handle_http_errors(progress, default_message=""):
                    response = client.get("/users/me")
                    response.raise_for_status()

            data = response.json()

            print(f"⚡ [bold]{data['email']}[/bold]")

    # Deplotment token status
    if identity.deploy_token is not None:
        print(
            "⚡ [bold]Using API token from environment variable for "
            "[blue]`fastapi deploy`[/blue] command.[/bold]"
        )
