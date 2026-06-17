import io
from datetime import datetime, timezone
from unittest.mock import Mock, call

import time_machine

from fastapi_cloud_cli.utils.progress_file import ProgressFile


def _make_file(
    content: bytes = b"hello world", name: str = "test.tar.gz"
) -> io.BytesIO:
    f = io.BytesIO(content)
    f.name = name
    return f


def test_read_with_size() -> None:
    file = _make_file(b"abcdef")
    pf = ProgressFile(file, progress_callback=lambda _: None)

    assert pf.read(3) == b"abc"
    assert pf.read(3) == b"def"


def test_callback_not_called_within_interval() -> None:
    file = _make_file(b"abcdef")
    mock_callback = Mock()
    pf = ProgressFile(file, progress_callback=mock_callback)

    pf.read(3)  # Should trigger callback
    pf.read(3)  # Should NOT trigger

    mock_callback.assert_called_once_with(3)


def test_callback_called_after_interval_elapses() -> None:
    file = _make_file(b"abcdef")
    mock_callback = Mock()

    with time_machine.travel(
        datetime(2026, 1, 1, tzinfo=timezone.utc), tick=False
    ) as traveller:
        pf = ProgressFile(file, progress_callback=mock_callback)

        pf.read(3)
        traveller.shift(0.6)
        pf.read(3)

    mock_callback.assert_has_calls([call(3), call(6)])


def test_callback_tracks_cumulative_bytes() -> None:
    file = _make_file(b"a" * 100)
    mock_callback = Mock()

    with time_machine.travel(
        datetime(2026, 1, 1, tzinfo=timezone.utc), tick=False
    ) as traveller:
        pf = ProgressFile(file, progress_callback=mock_callback)

        pf.read(10)  # Should trigger callback with 10 bytes read
        traveller.shift(0.1)
        pf.read(10)
        traveller.shift(0.5)
        pf.read(10)  # Should trigger callback with 10 + 10 + 10 = 30 bytes read
        traveller.shift(0.6)
        pf.read(10)  # Should trigger callback with 30 + 10 = 40 bytes read

    mock_callback.assert_has_calls([call(10), call(30), call(40)])


def test_callback_called_on_eof() -> None:
    file = _make_file(b"abcd")
    mock_callback = Mock()

    pf = ProgressFile(file, progress_callback=mock_callback)
    pf.read(3)
    pf.read(3)
    mock_callback.assert_has_calls([call(3), call(4)])


def test_name_property() -> None:
    file = _make_file(name="test.tar.gz")
    pf = ProgressFile(file, progress_callback=lambda _: None)

    assert pf.name == "test.tar.gz"


def test_callback_uses_current_file_position_after_seek() -> None:
    file = _make_file(b"abcde")
    mock_callback = Mock()

    pf = ProgressFile(file, progress_callback=mock_callback)

    pf.read(3)

    # Imitate retrying
    pf.seek(0)
    pf.read(3)

    pf.read(3)

    mock_callback.assert_has_calls([call(3), call(5)])
