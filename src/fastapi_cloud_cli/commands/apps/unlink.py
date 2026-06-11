import logging
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, Field
from rich.text import Text
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit, get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption

logger = logging.getLogger(__name__)


class UnlinkOutput(BaseModel):
    unlinked: bool
    path: Annotated[Path, Field(exclude=True)]
    removed_path: Path
    path_provided: Annotated[bool, Field(exclude=True)] = False


def _render_unlink_output(data: UnlinkOutput, toolkit: RichToolkit) -> None:
    removed_path = (
        data.removed_path
        if data.path_provided
        else data.removed_path.relative_to(Path.cwd())
    )

    toolkit.print("Removed app link", emoji="🔗")
    toolkit.print_line()
    toolkit.print(Text(f"Deleted {removed_path}", style="dim"))


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

    with get_rich_toolkit(json_output=json_output) as toolkit:
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
                path_provided=path is not None,
            ),
            render_output=_render_unlink_output,
        )
