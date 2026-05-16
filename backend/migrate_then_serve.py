"""Container entrypoint shim that runs Alembic before handing off to uvicorn.

Three cases to handle:

1. Brand-new database (no `alembic_version` table AND no app tables):
   run `alembic upgrade head` to materialise everything from the baseline.

2. Legacy database — already populated via `Base.metadata.create_all`
   from an earlier deploy (app tables exist, no `alembic_version`):
   run `alembic stamp head` so Alembic considers it caught up without
   re-running the baseline DDL (which would error on duplicate tables).

3. Normal upgrade (alembic_version present): `alembic upgrade head`
   applies any new revisions.

After migration, exec uvicorn so the container PID 1 is the app server.
"""
from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import inspect

from backend.app.core.database import engine


def _has_alembic_version() -> bool:
    return inspect(engine).has_table("alembic_version")


def _has_any_app_table() -> bool:
    # `accounts` is one of the oldest tables; if it exists, the DB was
    # populated by the old create_all flow.
    return inspect(engine).has_table("accounts")


def _run(cmd: list[str]) -> None:
    print(f"[migrate] {' '.join(cmd)}", flush=True)
    subprocess.check_call(cmd)


def main() -> None:
    if _has_alembic_version():
        _run(["alembic", "upgrade", "head"])
    elif _has_any_app_table():
        # Legacy DB — mark current state as the baseline revision so
        # future migrations apply incrementally, but skip re-creating
        # tables that already exist.
        print("[migrate] legacy DB detected; stamping baseline as head", flush=True)
        _run(["alembic", "stamp", "head"])
    else:
        # Fresh DB — run the baseline + any subsequent revisions.
        _run(["alembic", "upgrade", "head"])

    # Hand off to the real CMD. Splitting on whitespace is fine because
    # all our args are simple flags.
    serve_cmd = os.environ.get(
        "TG_SERVE_CMD",
        "uvicorn backend.app.main:app --host 0.0.0.0 --port 8000",
    ).split()
    os.execvp(serve_cmd[0], serve_cmd)


if __name__ == "__main__":
    main()
