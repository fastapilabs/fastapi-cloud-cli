from collections.abc import Callable
from datetime import datetime
from typing import BinaryIO


class ProgressFile:
    """Wraps a file object to track read progress."""

    def __init__(
        self,
        file: BinaryIO,
        progress_callback: Callable[[int], None],
        update_interval: float = 0.5,
    ):
        self._file = file
        self._progress_callback = progress_callback
        self._update_interval = update_interval
        self._last_update_time = 0.0
        self._bytes_read = 0

    def read(self, n=-1):
        data = self._file.read(n)
        self._bytes_read += len(data)
        now_ = datetime.now().timestamp()
        is_eof = (len(data) == 0) or (n > 0 and len(data) < n)
        if (now_ - self._last_update_time >= self._update_interval) or is_eof:
            self._progress_callback(self._bytes_read)
            self._last_update_time = now_
        return data

    def __iter__(self):
        return self._file.__iter__()

    @property
    def name(self):
        return self._file.name

    def seek(self, offset: int, whence: int = 0, /):
        return self._file.seek(offset, whence)

    def tell(self):
        return self._file.tell()
