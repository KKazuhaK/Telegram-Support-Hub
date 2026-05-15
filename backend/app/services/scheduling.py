from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta


@dataclass
class SendSettingsView:
    success_interval_seconds: int = 60
    failure_interval_seconds: int = 120
    random_min_seconds: int = 0
    random_max_seconds: int = 30
    per_account_concurrency: int = 1
    task_concurrency: int = 5
    max_per_account: int | None = None
    max_per_day: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> "SendSettingsView":
        data = dict(data or {})
        return cls(
            success_interval_seconds=int(data.get("success_interval_seconds", 60)),
            failure_interval_seconds=int(data.get("failure_interval_seconds", 120)),
            random_min_seconds=int(data.get("random_min_seconds", 0)),
            random_max_seconds=int(data.get("random_max_seconds", 30)),
            per_account_concurrency=int(data.get("per_account_concurrency", 1)),
            task_concurrency=int(data.get("task_concurrency", 5)),
            max_per_account=data.get("max_per_account"),
            max_per_day=data.get("max_per_day"),
            quiet_hours_start=data.get("quiet_hours_start"),
            quiet_hours_end=data.get("quiet_hours_end"),
        )


def _parse_hhmm(value: str | None) -> time | None:
    if not value or ":" not in value:
        return None
    try:
        hh, mm = value.split(":", 1)
        return time(int(hh), int(mm))
    except ValueError:
        return None


def in_quiet_hours(now: datetime, start: str | None, end: str | None) -> bool:
    s = _parse_hhmm(start)
    e = _parse_hhmm(end)
    if not s or not e:
        return False
    cur = now.time().replace(microsecond=0)
    if s <= e:
        return s <= cur < e
    # wraps midnight, e.g. 22:00 -> 09:00
    return cur >= s or cur < e


def add_random_jitter(seconds: int, lo: int, hi: int, rng: random.Random | None = None) -> int:
    rng = rng or random
    lo = max(0, lo)
    hi = max(lo, hi)
    return seconds + rng.randint(lo, hi)


def next_run_after_success(now: datetime, view: SendSettingsView) -> datetime:
    delta = add_random_jitter(view.success_interval_seconds, view.random_min_seconds, view.random_max_seconds)
    return now + timedelta(seconds=delta)


def next_run_after_failure(now: datetime, view: SendSettingsView) -> datetime:
    delta = add_random_jitter(view.failure_interval_seconds, view.random_min_seconds, view.random_max_seconds)
    return now + timedelta(seconds=delta)


def lock_ttl_seconds(view: SendSettingsView, padding: int = 30) -> int:
    return view.success_interval_seconds + view.random_max_seconds + max(0, padding)
