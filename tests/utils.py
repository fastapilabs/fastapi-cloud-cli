import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union


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
