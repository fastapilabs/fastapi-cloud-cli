import typer

from fastapi_cloud_cli.commands.ci.print_workflow import (
    print_workflow as print_workflow_command,
)

ci_app = typer.Typer(
    no_args_is_help=True,
    help="Manage CI integration helpers.",
)
ci_app.command("print-workflow")(print_workflow_command)

__all__ = ["ci_app"]
