"""Integrity tests for ``pie.storage.database.connect`` pragmas.

File-backed databases must be safe for concurrency/durability: WAL journal
mode, FULL synchronous mode, and an explicit busy timeout. ``:memory:``
databases must still connect and be usable without assuming WAL (SQLite does
not support WAL for in-memory databases).
"""

import sqlite3
from pathlib import Path

import pytest

from pie.storage.database import connect


def _pragma(connection, name):
    return connection.execute(f"PRAGMA {name}").fetchone()[0]


def test_file_database_enables_durability_pragmas(tmp_path: Path):
    database = tmp_path / "index.sqlite3"
    connection = connect(database)
    try:
        assert _pragma(connection, "journal_mode") == "wal"
        # FULL == 2 in the numeric pragma result.
        assert _pragma(connection, "synchronous") == 2
        assert _pragma(connection, "busy_timeout") == 5000
    finally:
        connection.close()


def test_file_database_is_durable_across_reopen(tmp_path: Path):
    database = tmp_path / "index.sqlite3"
    connection = connect(database)
    try:
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('probe', 'durable')"
        )
        connection.commit()
    finally:
        connection.close()

    reopened = connect(database)
    try:
        row = reopened.execute(
            "SELECT value FROM metadata WHERE key='probe'"
        ).fetchone()
        assert row["value"] == "durable"
    finally:
        reopened.close()


def test_string_filesystem_path_connects(tmp_path: Path):
    # connect() must keep accepting str filesystem paths, not only Path.
    database = tmp_path / "string-path.sqlite3"
    connection = connect(str(database))
    try:
        assert _pragma(connection, "journal_mode") == "wal"
        assert _pragma(connection, "synchronous") == 2
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('probe', 'string-path')"
        )
        connection.commit()
        row = connection.execute(
            "SELECT value FROM metadata WHERE key='probe'"
        ).fetchone()
        assert row["value"] == "string-path"
    finally:
        connection.close()
    assert Path(database).exists()


def test_memory_database_still_connects(tmp_path: Path):
    connection = connect(":memory:")
    try:
        # Schema is usable; do not assume WAL for in-memory databases.
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES ('probe', 'memory')"
        )
        connection.commit()
        row = connection.execute(
            "SELECT value FROM metadata WHERE key='probe'"
        ).fetchone()
        assert row["value"] == "memory"
    finally:
        connection.close()


def test_existing_file_database_is_upgraded_in_place(tmp_path: Path):
    # Simulate a pre-existing database created without WAL/full sync.
    database = tmp_path / "legacy.sqlite3"
    legacy = sqlite3.connect(database)
    try:
        legacy.execute("PRAGMA journal_mode = DELETE")
        legacy.execute(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        legacy.commit()
        assert legacy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        legacy.close()

    connection = connect(database)
    try:
        assert _pragma(connection, "journal_mode") == "wal"
        assert _pragma(connection, "synchronous") == 2
    finally:
        connection.close()


@pytest.mark.parametrize("pragma", ["foreign_keys", "busy_timeout"])
def test_memory_database_keeps_universal_pragmas(pragma):
    connection = connect(":memory:")
    try:
        if pragma == "foreign_keys":
            assert _pragma(connection, pragma) == 1
        else:
            assert _pragma(connection, pragma) == 5000
    finally:
        connection.close()
