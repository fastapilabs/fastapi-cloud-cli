from rich.markup import escape
from rich.text import Text

from fastapi_cloud_cli.api import BuildFailure
from fastapi_cloud_cli.utils.cli import FastAPIRichToolkit


def print_build_error(toolkit: FastAPIRichToolkit, error: BuildFailure) -> None:
    toolkit.print(Text(error.error_title, style="bold red"), emoji="🚨")
    toolkit.print_line()
    toolkit.print(Text(error.error_message))
    if error.error_hint:
        toolkit.print_line()
        toolkit.print_hint(escape(error.error_hint))
