from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any, BinaryIO


class ProgressFile(BinaryIO):
    """Wraps a file object to track read progress."""

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
        self._bytes_read = 0

    def read(self, n: int = -1) -> bytes:
        data = self._file.read(n)
        self._bytes_read += len(data)
        now_ = datetime.now().timestamp()
        is_eof = (len(data) == 0) or (n > 0 and len(data) < n)
        if (now_ - self._last_update_time >= self._update_interval) or is_eof:
            self._progress_callback(self._bytes_read)
            self._last_update_time = now_
        return data

    def fileno(self) -> int:
        return self._file.fileno()

    @property
    def name(self) -> str:
        return self._file.name

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._file.seek(offset, whence)

    def tell(self) -> int:
        return self._file.tell()

    def __iter__(self) -> Iterator[bytes]:
        return self._file.__iter__()

    def __next__(self) -> bytes:
        return next(self._file)

    @property
    def mode(self) -> str:
        return self._file.mode

    def readable(self) -> bool:
        return self._file.readable()

    def seekable(self) -> bool:
        return self._file.seekable()

    # Methods below are just to satisfy the BinaryIO interface

    def write(self, *_args: Any, **kwargs: Any) -> int:
        raise NotImplementedError()

    def readline(self, *_args: Any, **kwargs: Any) -> bytes:
        raise NotImplementedError()

    def readlines(self, *_args: Any, **kwargs: Any) -> list[bytes]:
        raise NotImplementedError()

    def writelines(self, *_args: Any, **kwargs: Any) -> None:
        raise NotImplementedError()

    def __enter__(self) -> BinaryIO:
        raise NotImplementedError()

    def __exit__(self, *_args: Any) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()

    @property
    def closed(self) -> bool:
        raise NotImplementedError()

    def flush(self) -> None:
        raise NotImplementedError()

    def isatty(self) -> bool:
        raise NotImplementedError()

    def writable(self) -> bool:
        raise NotImplementedError()

    def truncate(self, *_args: Any, **kwargs: Any) -> int:
        raise NotImplementedError()
