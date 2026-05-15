from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect


def to_dict(obj: Any) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    data: dict[str, Any] = {}
    for column in mapper.column_attrs:
        if column.key == "password_encrypted":
            data["has_password"] = bool(getattr(obj, column.key))
            continue
        value = getattr(obj, column.key)
        if isinstance(value, datetime | date):
            value = value.isoformat()
        data[column.key] = value
    return data


def list_dict(items: list[Any]) -> list[dict[str, Any]]:
    return [to_dict(item) for item in items]
