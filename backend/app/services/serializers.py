from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect


# Columns whose presence/absence is fine to expose but whose value isn't.
# Caller gets a boolean flag instead of the raw secret/path so a future
# log/audit/leak doesn't ship credentials or absolute fs paths.
_REDACT_AS_HAS = {
    "password_encrypted": "has_password",
    # Account.session_path is an absolute path to a Telethon .session
    # file with auth_key inside — leaking the path makes it trivial for
    # any same-host actor to grab it. UI doesn't need the path, only
    # whether one exists.
    "session_path": "has_session",
}


def to_dict(obj: Any) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    data: dict[str, Any] = {}
    for column in mapper.column_attrs:
        flag_key = _REDACT_AS_HAS.get(column.key)
        if flag_key:
            data[flag_key] = bool(getattr(obj, column.key))
            continue
        value = getattr(obj, column.key)
        if isinstance(value, datetime | date):
            value = value.isoformat()
        data[column.key] = value
    return data


def list_dict(items: list[Any]) -> list[dict[str, Any]]:
    return [to_dict(item) for item in items]
