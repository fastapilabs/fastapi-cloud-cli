import os
from typing import Annotated

import typer

JsonOutputOption = Annotated[
    bool,
    typer.Option(
        "--json",
        envvar="FASTAPI_CLOUD_JSON",
        help="Print structured JSON to stdout.",
    ),
]


def is_ci_enabled() -> bool:
    value = os.environ.get("CI")

    if value is None:
        return False

    return value.lower() not in {"", "0", "false", "no", "off"}
