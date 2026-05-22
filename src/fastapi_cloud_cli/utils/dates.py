from datetime import datetime, timezone


def format_last_updated(updated_at: str | None) -> str:
    if updated_at is None:
        return "-"

    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return updated_at

    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    seconds = int((now - updated).total_seconds())

    if seconds < 60:
        return "just now"

    minutes = seconds // 60
    if minutes < 60:
        return _format_time_ago(minutes, "minute")

    hours = minutes // 60
    if hours < 24:
        return _format_time_ago(hours, "hour")

    days = hours // 24
    if days < 30:
        return _format_time_ago(days, "day")

    months = days // 30
    if months < 12:
        return _format_time_ago(months, "month")

    years = days // 365
    return _format_time_ago(years, "year")


def _format_time_ago(value: int, unit: str) -> str:
    suffix = "" if value == 1 else "s"

    return f"{value} {unit}{suffix} ago"
