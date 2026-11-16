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

from pie.integrations.blender_delta import SceneDeltaCache, _digest
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

    # ------------------------------------------------------------- history/versioning
    def _history_rows(self, root=None):
        database = workspace_storage(root if root is not None else self.root) / "index.sqlite3"
        with contextlib.closing(sqlite3.connect(str(database))) as connection:
            return connection.execute(
                "SELECT scene, scope, version, digest, counts, state, created_at "
                "FROM scene_delta_fingerprint_history ORDER BY version"
            ).fetchall()

    def test_history_records_multiple_versions_in_order(self):
        cache = SceneDeltaCache(root=self.root)
        first = make_snapshot(objects=[{"name": "Cube", "type": "MESH",
                                        "location": [0.0, 0.0, 0.0]}])
        second = make_snapshot(objects=[{"name": "Cube", "type": "MESH",
                                         "location": [1.0, 0.0, 0.0]}])
        self.assertEqual(cache.observe(first)["state"], "INITIAL")
        self.assertEqual(cache.observe(second)["state"], "DELTA")
        self.assertEqual(cache.observe(second)["state"], "UNCHANGED")
        rows = self._history_rows()
        self.assertEqual([row[2] for row in rows], [1, 2, 3])
        self.assertEqual([row[5] for row in rows], ["INITIAL", "DELTA", "UNCHANGED"])
        self.assertEqual(rows[0][3], _digest(first))
        # Counts are stored as JSON metadata only.
        self.assertEqual(json.loads(rows[0][4]), {"materials": 1, "objects": 1})

    def test_history_survives_restart(self):
        cache = SceneDeltaCache(root=self.root)
        cache.observe(make_snapshot())
        cache.observe(make_snapshot(objects=[{"name": "Cube", "type": "MESH",
                                              "location": [2.0, 0.0, 0.0]}]))
        reopened = SceneDeltaCache(root=self.root)
        rows = self._history_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row[5] for row in rows], ["INITIAL", "DELTA"])
        # The read-only accessor works on the restarted instance too.
        versions = reopened.history("Scene", "selected")
        self.assertEqual([item["version"] for item in versions], [2, 1])

    def test_history_is_bounded_per_key(self):
        cache = SceneDeltaCache(root=self.root)
        for index in range(10):
            cache.observe(make_snapshot(
                objects=[{"name": "Cube", "type": "MESH",
                          "location": [float(index), 0.0, 0.0]}]))
        rows = self._history_rows()
        self.assertEqual(len(rows), SceneDeltaCache._HISTORY_LIMIT)
        self.assertEqual([row[2] for row in rows], [6, 7, 8, 9, 10])

    def test_partial_and_budget_exceeded_add_no_history_version(self):
        snapshot = make_snapshot(scene="S".ljust(512, "x"))
        cache = SceneDeltaCache(root=self.root)
        self.assertEqual(cache.observe(snapshot)["state"], "INITIAL")
        partial = make_snapshot(scene="S".ljust(512, "x"), complete=False,
                                omissions={"objects": 3, "materials": 0})
        self.assertEqual(cache.observe(partial)["state"], "PARTIAL")
        changed = make_snapshot(
            scene="S".ljust(512, "x"),
            objects=[{"name": f"Obj{i}".ljust(512, "x"), "type": "MESH",
                      "location": [float(i)] * 3} for i in range(500)])
        self.assertEqual(cache.observe(changed, max_chars=1000)["state"],
                         "BUDGET_EXCEEDED")
        rows = self._history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][5], "INITIAL")

    def test_history_table_contains_only_sanitized_fields(self):
        snapshot = make_snapshot(scene="My Scene", scope="all",
                                 objects=[{"name": "Cube", "type": "MESH",
                                           "secret_field": "do-not-persist"}],
                                 materials=[{"name": "Material", "nodes": [], "links": []}])
        SceneDeltaCache(root=self.root).observe(snapshot)
        rows = self._history_rows()
        self.assertEqual(len(rows), 1)
        raw = " | ".join(" | ".join(str(cell) for cell in row) for row in rows)
        blob = raw.lower()
        for forbidden in ("cube", "mesh", "location", "prompt",
                          "secret", "cookie", "password", "token", "authorization"):
            self.assertNotIn(forbidden, blob)

    # ------------------------------------------------------------- concurrency
    def test_concurrent_instances_do_not_erase_each_others_fingerprints(self):
        """Two caches sharing one store must both survive a flush (regression:
        _flush_store used to DELETE the whole table before re-inserting only
        its own in-memory keys, wiping other instances' rows)."""
        cache_a = SceneDeltaCache(root=self.root)
        cache_b = SceneDeltaCache(root=self.root)
        snapshot_a = make_snapshot(scene="Scene A")
        snapshot_b = make_snapshot(scene="Scene B")
        self.assertEqual(cache_a.observe(snapshot_a)["state"], "INITIAL")
        self.assertEqual(cache_b.observe(snapshot_b)["state"], "INITIAL")
        rows = {(row[0], row[1]) for row in self._rows()}
        self.assertIn(("Scene A", "selected"), rows)
        self.assertIn(("Scene B", "selected"), rows)
        # Repeated flushes from A (e.g. after observing more scenes) must not
        # drop B's row, and vice versa.
        self.assertEqual(cache_a.observe(make_snapshot(scene="Scene A2"))["state"],
                         "INITIAL")
        rows = {(row[0], row[1]) for row in self._rows()}
        self.assertIn(("Scene B", "selected"), rows)
        self.assertIn(("Scene A", "selected"), rows)
        self.assertIn(("Scene A2", "selected"), rows)
        # Both instances still see their own baselines after restart.
        self.assertEqual(SceneDeltaCache(root=self.root).observe(snapshot_a)["state"],
                         "UNCHANGED")
        self.assertEqual(SceneDeltaCache(root=self.root).observe(snapshot_b)["state"],
                         "UNCHANGED")

    def test_concurrent_history_appends_allocate_unique_versions(self):
        """Interleaved appends from two caches for the same (scene, scope)
        must serialize: no duplicate versions, strictly increasing sequence,
        and no IntegrityError silently degrading either instance."""
        import threading

        cache_a = SceneDeltaCache(root=self.root)
        cache_b = SceneDeltaCache(root=self.root)
        errors: list[BaseException] = []

        def observe_many(cache, start):
            for index in range(10):
                try:
                    cache.observe(make_snapshot(
                        objects=[{"name": "Cube", "type": "MESH",
                                  "location": [float(start + index), 0.0, 0.0]}]))
                except BaseException as exc:  # pragma: no cover - surfaced below
                    errors.append(exc)

        threads = [threading.Thread(target=observe_many, args=(cache_a, 0)),
                   threading.Thread(target=observe_many, args=(cache_b, 100))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        # Neither instance may have degraded to memory-only due to a lost
        # version-allocation race.
        self.assertIsNotNone(cache_a._db_path)
        self.assertIsNotNone(cache_b._db_path)
        self.assertIsNone(cache_a.persistence_diagnostic)
        self.assertIsNone(cache_b.persistence_diagnostic)
        rows = self._history_rows()
        versions = [row[2] for row in rows]
        self.assertEqual(len(versions), len(set(versions)), "duplicate versions")
        # All 20 appends succeeded (both instances stayed on the DB), so the
        # retained window is exactly the last _HISTORY_LIMIT contiguous,
        # strictly increasing versions.
        self.assertEqual(len(versions), SceneDeltaCache._HISTORY_LIMIT)
        self.assertEqual(versions, list(range(versions[0], versions[0] + len(versions))),
                         "versions must be unique and contiguous")

    def test_store_without_root_stays_memory_only(self):
        cache = SceneDeltaCache()
        self.assertIsNone(cache._db_path)
        self.assertIsNone(cache.persistence_diagnostic)
        self.assertEqual(cache.observe(make_snapshot())["state"], "INITIAL")
        # History is unavailable without a workspace DB.
        self.assertEqual(cache.history("Scene", "selected"), [])


if __name__ == "__main__":
    unittest.main()
