import logging
from typing import Any

from fastapi_cloud_cli.utils.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity
from fastapi_cloud_cli.utils.cli import get_rich_toolkit

logger = logging.getLogger(__name__)


def whoami() -> Any:
    identity = Identity()

    with get_rich_toolkit(minimal=True) as toolkit:
        if not identity.is_logged_in():
            toolkit.print(
                "No credentials found. Use [blue]`fastapi login`[/] to login."
            )
        else:
            with APIClient() as client:
                with toolkit.progress(
                    title="⚡ Fetching profile",
                    transient=True,
                ) as progress:
                    with client.handle_http_errors(progress, default_message=""):
                        response = client.get("/users/me")
                        response.raise_for_status()

                data = response.json()

                toolkit.print(f"⚡ [bold]{data['email']}[/bold]")

        if identity.has_deploy_token():
            toolkit.print(
                "⚡ [bold]Using API token from environment variable for "
                "[blue]`fastapi deploy`[/blue] command.[/bold]"
            )
