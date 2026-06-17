from datetime import datetime, timezone

import pytest
import time_machine

from fastapi_cloud_cli.utils.dates import format_last_updated


@time_machine.travel(datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc), tick=False)
@pytest.mark.parametrize(
    ("updated_at", "expected"),
    [
        ("2026-05-22T11:59:30Z", "just now"),
        ("2026-05-22T11:59:00Z", "1 minute ago"),
        ("2026-05-22T11:30:00", "30 minutes ago"),
        ("2026-05-22T10:00:00Z", "2 hours ago"),
        ("2025-05-22T12:00:00Z", "1 year ago"),
    ],
)
def test_format_last_updated_formats_relative_time(
    updated_at: str, expected: str
) -> None:
    assert format_last_updated(updated_at) == expected


def test_format_last_updated_returns_invalid_dates_unchanged() -> None:
    assert format_last_updated("not-a-date") == "not-a-date"
