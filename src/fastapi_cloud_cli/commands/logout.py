from typing import Any

from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.auth import delete_auth_config
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class LogoutOutput(BaseModel):
    logged_out: bool


def _render_logout_output(data: LogoutOutput, toolkit: RichToolkit) -> None:
    toolkit.print_title("FastAPI Cloud")
    toolkit.print_line()
    toolkit.print("You are now logged out!", emoji="👋")


def logout(json_output: JsonOutputOption = False) -> Any:
    """
    Logout from FastAPI Cloud.
    """
    with get_rich_toolkit(json_output=json_output) as toolkit:
        delete_auth_config()
        toolkit.success(
            LogoutOutput(logged_out=True),
            render_output=_render_logout_output,
        )
