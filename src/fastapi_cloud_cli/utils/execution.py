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
