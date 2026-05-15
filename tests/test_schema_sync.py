import unittest

import tests.support  # noqa: F401

import sqlalchemy
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, JSON, MetaData, String, Table, func, inspect, text,
)

from backend.app.core.schema_sync import ensure_columns_present


def _make_engine():
    return sqlalchemy.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sqlalchemy.pool.StaticPool,
        future=True,
    )


class SchemaSyncTestCase(unittest.TestCase):
    def test_adds_missing_nullable_column(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t1 (id INTEGER PRIMARY KEY, name VARCHAR(64))"))

        metadata = MetaData()
        Table("t1", metadata,
              Column("id", Integer, primary_key=True),
              Column("name", String(64)),
              Column("notes", String(255), nullable=True))

        added = ensure_columns_present(engine, metadata)
        self.assertEqual(added, [("t1", "notes")])
        cols = {c["name"] for c in inspect(engine).get_columns("t1")}
        self.assertIn("notes", cols)

    def test_adds_column_with_string_default(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

        metadata = MetaData()
        Table("t", metadata,
              Column("id", Integer, primary_key=True),
              Column("kind", String(32), nullable=False, default="broadcast"))

        ensure_columns_present(engine, metadata)
        with engine.connect() as conn:
            conn.execute(text("INSERT INTO t (id) VALUES (1)"))
            conn.commit()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT kind FROM t WHERE id=1")).first()
        self.assertEqual(row[0], "broadcast")

    def test_adds_boolean_column(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE perm (id INTEGER PRIMARY KEY)"))

        metadata = MetaData()
        Table("perm", metadata,
              Column("id", Integer, primary_key=True),
              Column("enabled", Boolean, nullable=False, default=True))

        ensure_columns_present(engine, metadata)
        cols = {c["name"] for c in inspect(engine).get_columns("perm")}
        self.assertIn("enabled", cols)

    def test_idempotent_second_run_is_noop(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

        metadata = MetaData()
        Table("t", metadata,
              Column("id", Integer, primary_key=True),
              Column("extra", String(64)))

        first = ensure_columns_present(engine, metadata)
        second = ensure_columns_present(engine, metadata)
        self.assertEqual(first, [("t", "extra")])
        self.assertEqual(second, [])

    def test_skips_table_not_yet_created(self) -> None:
        engine = _make_engine()
        # Don't create the table; ensure no errors and no ALTER attempted.
        metadata = MetaData()
        Table("ghost", metadata, Column("id", Integer, primary_key=True))
        added = ensure_columns_present(engine, metadata)
        self.assertEqual(added, [])

    def test_supports_json_column(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))

        metadata = MetaData()
        Table("t", metadata,
              Column("id", Integer, primary_key=True),
              Column("extra", JSON, nullable=True))

        added = ensure_columns_present(engine, metadata)
        self.assertEqual(added, [("t", "extra")])

    def test_returns_table_column_pairs_in_order(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE t1 (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE t2 (id INTEGER PRIMARY KEY)"))

        metadata = MetaData()
        Table("t1", metadata,
              Column("id", Integer, primary_key=True),
              Column("a", String(32)),
              Column("b", String(32)))
        Table("t2", metadata,
              Column("id", Integer, primary_key=True),
              Column("c", String(32)))

        added = ensure_columns_present(engine, metadata)
        self.assertEqual(set(added), {("t1", "a"), ("t1", "b"), ("t2", "c")})


if __name__ == "__main__":
    unittest.main()
