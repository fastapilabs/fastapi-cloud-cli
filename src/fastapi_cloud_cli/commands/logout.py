from typing import Any

from fastapi_cloud_cli.utils.auth import delete_auth_config
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


def logout(
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Logout from FastAPI Cloud.
    """
    with get_rich_toolkit(json_output=json_output) as toolkit:
        if not json_output:
            toolkit.print_title("FastAPI Cloud")
            toolkit.print_line()

        delete_auth_config()

        if json_output:
            toolkit.success({"logged_out": True})
            return

        toolkit.print("You are now logged out!", emoji="👋")
