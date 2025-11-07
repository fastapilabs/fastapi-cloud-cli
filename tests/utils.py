import base64
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, Union


@contextmanager
def changing_dir(directory: Union[str, Path]) -> Generator[None, None, None]:
    initial_dir = os.getcwd()
    os.chdir(directory)
    try:
        yield
    finally:
        os.chdir(initial_dir)


class Keys:
    RIGHT_ARROW = "\x1b[C"
    DOWN_ARROW = "\x1b[B"
    ENTER = "\r"
    CTRL_C = "\x03"
    TAB = "\t"


def create_jwt_token(payload: Dict[str, Any]) -> str:
    # Note: This creates a JWT with an invalid signature, but that's OK for our tests
    # since we only parse the payload, not verify the signature.

    header = {"alg": "HS256", "typ": "JWT"}
    header_encoded = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    )

    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )

    signature = base64.urlsafe_b64encode(b"signature").decode().rstrip("=")

    return f"{header_encoded}.{payload_encoded}.{signature}"
