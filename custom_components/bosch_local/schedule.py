"""Persistent schedule values and validation, independent of Home Assistant."""
from datetime import datetime, timezone


def validate_start(value: datetime, now: datetime | None = None) -> datetime:
    """Require an unambiguous future instant; never send appliance delay options."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Start time must include a timezone")
    value = value.astimezone(timezone.utc)
    if value <= (now or datetime.now(timezone.utc)):
        raise ValueError("Start time must be in the future")
    return value


def program_payload(program: str, programs: dict[str, int]) -> list[dict]:
    """Build an immediate start using only explicitly configured program IDs."""
    uid = programs.get(program)
    if isinstance(uid, bool) or not isinstance(uid, int) or uid <= 0:
        raise ValueError("Select a configured dishwasher program")
    return [{"program": uid}]
