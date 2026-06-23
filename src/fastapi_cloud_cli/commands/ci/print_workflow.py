from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich_toolkit import RichToolkit

from fastapi_cloud_cli.commands.setup_ci import (
    DEFAULT_WORKFLOW_PATH,
    _get_default_branch,
    _get_workflow_content,
)
from fastapi_cloud_cli.utils.cli import get_rich_toolkit
from fastapi_cloud_cli.utils.execution import JsonOutputOption


class CIWorkflowOutput(BaseModel):
    filename: str
    content: str


def _render_workflow_output(data: CIWorkflowOutput, toolkit: RichToolkit) -> None:
    toolkit.console.print(data.content, markup=False, end="")


def print_workflow(
    branch: Annotated[
        str | None,
        typer.Option(
            "--branch",
            "-b",
            help="Branch that triggers deploys (defaults to the repo's default branch).",
        ),
    ] = None,
    json_output: JsonOutputOption = False,
) -> Any:
    """Prints the GitHub Actions workflow YAML without writing files or secrets."""

    branch = branch or _get_default_branch()
    workflow = CIWorkflowOutput(
        filename=DEFAULT_WORKFLOW_PATH.name,
        content=_get_workflow_content(branch),
    )

    with get_rich_toolkit(minimal=True, json_output=json_output) as toolkit:
        toolkit.success(workflow, render_output=_render_workflow_output)
