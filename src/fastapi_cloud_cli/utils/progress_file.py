from collections.abc import Callable
from datetime import datetime
from typing import Any, BinaryIO


class ProgressFile:
    """Wrap a binary file object and report upload progress as it is read."""

    def __init__(
        self,
        file: BinaryIO,
        progress_callback: Callable[[int], None],
        update_interval: float = 0.5,
    ) -> None:
        self._file = file
        self._progress_callback = progress_callback
        self._update_interval = update_interval
        self._last_update_time = 0.0

    def read(self, n: int = -1) -> bytes:
        data = self._file.read(n)
        now_ = datetime.now().timestamp()
        is_eof = (len(data) == 0) or (n > 0 and len(data) < n)
        if (now_ - self._last_update_time >= self._update_interval) or is_eof:
            self._progress_callback(self._file.tell())
            self._last_update_time = now_
        return data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._file, name)
