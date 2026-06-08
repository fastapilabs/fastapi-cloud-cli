import logging
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class UnlinkOutput(BaseModel):
    unlinked: bool
    path: Path
    removed_path: Path


def _render_unlink_output(data: UnlinkOutput, toolkit: RichToolkit) -> None:
    toolkit.print("Removed app link")
    toolkit.print(f"Deleted {data.removed_path}")


def _fail_not_linked(toolkit: FastAPIRichToolkit) -> None:
    toolkit.fail(
        "not_linked",
        "No app is linked to this directory.",
        hint="Run `fastapi cloud link` to link an app.",
    )


def unlink_app(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path",
            help="Directory to unlink.",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """
    Unlink by deleting the `.fastapicloud/cloud.json` file.
    """
    path_to_unlink = path or Path.cwd()
    config_path = path_to_unlink / ".fastapicloud/cloud.json"

    with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
        if not config_path.exists():
            logger.debug(f"Configuration file not found: {config_path}")
            _fail_not_linked(toolkit)

        config_path.unlink()
        logger.debug(f"Deleted configuration file: {config_path}")

        toolkit.success(
            UnlinkOutput(
                unlinked=True,
                path=path_to_unlink,
                removed_path=config_path,
            ),
            render_output=_render_unlink_output,
        )
