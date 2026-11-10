import logging
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, Field
from rich_toolkit import RichToolkit

from fastapi_cloud_cli._app import cloud_app
from fastapi_cloud_cli.api import APIClient
from fastapi_cloud_cli.utils.auth import Identity, delete_auth_config
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class LogoutOutput(BaseModel):
    logged_out: bool
    revoke_failed: Annotated[bool, Field(exclude=True)] = False


REVOKE_FAILED_MESSAGE = (
    "Couldn't sign out on FastAPI Cloud, so this login stays valid until it expires."
)


def _render_logout_output(data: LogoutOutput, toolkit: RichToolkit) -> None:
    toolkit.print_title("FastAPI Cloud")
    toolkit.print_line()
    toolkit.print("You are now logged out!", emoji="👋")

    if data.revoke_failed:
        toolkit.print_line()
        toolkit.print(REVOKE_FAILED_MESSAGE, emoji="⚠️")


@cloud_app.command()
def logout(json_output: JsonOutputOption = False) -> Any:
    """
    Logout from FastAPI Cloud.
    """
    with get_rich_toolkit(json_output=json_output) as toolkit:
        revoke_failed = False

        if Identity().user_token:
            # Revoke the token on a best-effort basis: logging out must still
            # work when FastAPI Cloud can't be reached.
            try:
                with APIClient() as client:
                    client.logout()
            except httpx.HTTPError as e:
                logger.debug("Could not revoke the token: %s", e)
                revoke_failed = True

        delete_auth_config()

        warnings = []
        if revoke_failed:
            warnings.append(
                {"code": "token_not_revoked", "message": REVOKE_FAILED_MESSAGE}
            )

        toolkit.success(
            LogoutOutput(logged_out=True, revoke_failed=revoke_failed),
            warnings=warnings,
            render_output=_render_logout_output,
        )
