import os
from typing import Annotated

import typer

JSON_ENV_VAR = "FASTAPI_CLOUD_JSON"
JsonOutputOption = Annotated[
    bool,
    typer.Option(
        "--json",
        envvar=JSON_ENV_VAR,
        help="Print structured JSON to stdout.",
    ),
]


def _env_enabled(name: str) -> bool:
    return os.environ.get(name) == "1"


def is_json_enabled() -> bool:
    return _env_enabled(JSON_ENV_VAR)
