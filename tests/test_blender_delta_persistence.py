"""Tests for the SQLite-backed SceneDeltaCache fingerprint store.

The persisted store must contain only fingerprints and metadata
(scene, scope, digest, counts, timestamps) — never snapshot content.
"""

import contextlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pie.integrations.blender_delta import SceneDeltaCache
from pie.storage.database import connect
from pie.storage.locations import workspace_storage


def make_snapshot(scene="Scene", scope="selected", objects=None, materials=None,
                  complete=True, omissions=None):
    return {
        "schema": "pie-blender-scene-snapshot-v1",
        "scene": scene,
        "scope": scope,
        "complete": complete,
        "omissions": omissions if omissions is not None else {"objects": 0, "materials": 0},
        "objects": objects if objects is not None
        else [{"name": "Cube", "type": "MESH", "location": [0.0, 0.0, 0.0]}],
        "materials": materials if materials is not None
        else [{"name": "Material", "nodes": [], "links": []}],
    }


class BlenderDeltaPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._old_env = os.environ.pop("PIE_GLOBAL_STORAGE_ROOT", None)
        # WAL connections from other objects may still be open on Windows;
        # ignore cleanup errors instead of failing the test teardown.
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        # The fingerprint store lives in the existing workspace index DB.
        connect(self.root / ".pie" / "index.sqlite3").close()

    def tearDown(self):
        self.temp.cleanup()
        if self._old_env is not None:
            os.environ["PIE_GLOBAL_STORAGE_ROOT"] = self._old_env

    def _rows(self, root=None):
        database = workspace_storage(root if root is not None else self.root) / "index.sqlite3"
        with contextlib.closing(sqlite3.connect(str(database))) as connection:
            return connection.execute(
                "SELECT scene, scope, digest, counts, updated_at "
                "FROM scene_delta_fingerprints"
            ).fetchall()

    def test_restart_with_same_scene_is_unchanged(self):
        snapshot = make_snapshot()
        first = SceneDeltaCache(root=self.root)
        self.assertEqual(first.observe(snapshot)["state"], "INITIAL")
        second = SceneDeltaCache(root=self.root)
        result = second.observe(snapshot)
        self.assertEqual(result["state"], "UNCHANGED")
        self.assertIsNone(second.persistence_diagnostic)

    def test_changed_scene_after_restart_is_delta(self):
        first = SceneDeltaCache(root=self.root)
        self.assertEqual(first.observe(make_snapshot())["state"], "INITIAL")
        changed = make_snapshot(objects=[{"name": "Cube", "type": "MESH",
                                          "location": [1.0, 0.0, 0.0]}])
        second = SceneDeltaCache(root=self.root)
        result = second.observe(changed)
        self.assertEqual(result["state"], "DELTA")
        # Fingerprints only: no entity-level details survive persistence.
        self.assertNotIn("objects", result)
        self.assertNotIn("materials", result)
        self.assertEqual(result.get("previous_counts"), {"materials": 1, "objects": 1})
        self.assertIn("note", result)

    def test_roots_are_isolated(self):
        snapshot = make_snapshot()
        other = self.root / "other"
        (other / ".pie").mkdir(parents=True)
        connect(other / ".pie" / "index.sqlite3").close()
        first = SceneDeltaCache(root=self.root)
        self.assertEqual(first.observe(snapshot)["state"], "INITIAL")
        second = SceneDeltaCache(root=other)
        self.assertEqual(second.observe(snapshot)["state"], "INITIAL")

    def test_partial_observation_does_not_replace_persisted_baseline(self):
        snapshot = make_snapshot()
        first = SceneDeltaCache(root=self.root)
        self.assertEqual(first.observe(snapshot)["state"], "INITIAL")
        partial = make_snapshot(complete=False, omissions={"objects": 3, "materials": 0})
        self.assertEqual(first.observe(partial)["state"], "PARTIAL")
        second = SceneDeltaCache(root=self.root)
        self.assertEqual(second.observe(snapshot)["state"], "UNCHANGED")

    def test_budget_exceeded_does_not_replace_persisted_baseline(self):
        snapshot = make_snapshot(scene="S".ljust(512, "x"))
        first = SceneDeltaCache(root=self.root)
        self.assertEqual(first.observe(snapshot)["state"], "INITIAL")
        changed = make_snapshot(
            scene="S".ljust(512, "x"),
            objects=[{"name": f"Obj{i}".ljust(512, "x"), "type": "MESH",
                      "location": [float(i)] * 3}
                     for i in range(500)])
        self.assertEqual(first.observe(changed, max_chars=1000)["state"], "BUDGET_EXCEEDED")
        second = SceneDeltaCache(root=self.root)
        self.assertEqual(second.observe(snapshot)["state"], "UNCHANGED")

    def test_missing_database_degrades_to_memory_only(self):
        other = self.root / "nodb"
        other.mkdir()
        cache = SceneDeltaCache(root=other)
        self.assertIsNotNone(cache.persistence_diagnostic)
        self.assertIsNone(cache._db_path)
        self.assertEqual(cache.observe(make_snapshot())["state"], "INITIAL")

    def test_corrupted_database_degrades_to_memory_only(self):
        database = workspace_storage(self.root) / "index.sqlite3"
        database.write_bytes(b"this is not a sqlite database")
        cache = SceneDeltaCache(root=self.root)
        self.assertIsNotNone(cache.persistence_diagnostic)
        self.assertIsNone(cache._db_path)
        self.assertEqual(cache.observe(make_snapshot())["state"], "INITIAL")

    def test_invalid_persisted_row_degrades_to_memory_only(self):
        first = SceneDeltaCache(root=self.root)
        self.assertEqual(first.observe(make_snapshot())["state"], "INITIAL")
        database = workspace_storage(self.root) / "index.sqlite3"
        with contextlib.closing(sqlite3.connect(str(database))) as connection:
            connection.execute("UPDATE scene_delta_fingerprints SET digest = 'zz'")
            connection.commit()
        cache = SceneDeltaCache(root=self.root)
        self.assertIsNotNone(cache.persistence_diagnostic)
        self.assertIsNone(cache._db_path)
        self.assertEqual(cache.observe(make_snapshot())["state"], "INITIAL")

    def test_persisted_table_contains_only_sanitized_fields(self):
        snapshot = make_snapshot(scene="My Scene", scope="all",
                                 objects=[{"name": "Cube", "type": "MESH",
                                           "secret_field": "do-not-persist"}],
                                 materials=[{"name": "Material", "nodes": [], "links": []}])
        SceneDeltaCache(root=self.root).observe(snapshot)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        scene, scope, digest, counts, updated_at = rows[0]
        self.assertEqual((scene, scope), ("My Scene", "all"))
        self.assertEqual(len(digest), 64)
        self.assertEqual(json.loads(counts), {"materials": 1, "objects": 1})
        self.assertTrue(updated_at)
        # No snapshot content (entity names/fields) may ever be persisted.
        raw = " | ".join(" | ".join(row) for row in rows)
        blob = raw.lower()
        for forbidden in ("cube", "mesh", "location", "prompt",
                          "secret", "cookie", "password", "token", "authorization"):
            self.assertNotIn(forbidden, blob)

    def test_store_without_root_stays_memory_only(self):
        cache = SceneDeltaCache()
        self.assertIsNone(cache._db_path)
        self.assertIsNone(cache.persistence_diagnostic)
        self.assertEqual(cache.observe(make_snapshot())["state"], "INITIAL")


if __name__ == "__main__":
    unittest.main()
