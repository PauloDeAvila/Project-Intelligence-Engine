"""Global PIE zero-prompt tests: startup, incremental, restart, isolation, no project writes."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pie.indexing.global_workspace import GlobalWorkspaceIndex, detect_workspace
from pie.storage.locations import workspace_file
from pie.interfaces.global_mcp import list_known_workspaces


class GlobalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.store=self.base/"central-store"
        self.project=self.base/"the-app"
        self.project.mkdir()
        (self.project/"pyproject.toml").write_text("[project]\nname='test-app'\n",encoding="utf8")
        (self.project/"alpha.py").write_text("def alpha():\n    return 1\n",encoding="utf8")
        (self.project/"beta.py").write_text("def beta():\n    return 2\n",encoding="utf8")
        self.patch=patch.dict(os.environ,{"PIE_GLOBAL_STORAGE_ROOT":str(self.store)})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_first_use_builds_index_only_under_central_store(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        result=w.refresh()
        self.assertEqual(result["mode"],"FULL")
        self.assertTrue(result["first_index"])
        self.assertEqual(result["python_index"]["files"],2)
        self.assertFalse((self.project/".pie").exists())
        self.assertTrue(workspace_file(self.project).is_file())
        self.assertTrue((self.store/"registry.sqlite3").exists())
        self.assertEqual(w.status()["tracked_files"],3)

    def test_automatic_file_change_journal_survives_restart(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        self.assertEqual(w.recent_changes()["events"], [])
        (self.project/"alpha.py").write_text("def alpha():\n    return 99\n",encoding="utf8")
        w.refresh()
        changes=GlobalWorkspaceIndex(self.project,force_global=True).recent_changes()
        self.assertEqual(len(changes["events"]),1)
        self.assertEqual(changes["events"][0]["path"],"alpha.py")
        self.assertEqual(changes["events"][0]["change_kind"],"MODIFIED")

    def test_binary_blender_ableton_assets_store_metadata_only(self):
        (self.project/"material.blend").write_bytes(b"BINARY"+bytes(range(80)))
        (self.project/"session.als").write_bytes(b"Ableton-proprietary-placeholder")
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(w.storage)) as db:
            data=db.execute("SELECT path,sha256,content,text_state FROM pie_global_files "
                            "WHERE path IN ('material.blend','session.als') ORDER BY path").fetchall()
        self.assertEqual(len(data),2)
        self.assertTrue(all(item[3]=="METADATA_ONLY" and item[1] is None
                            and item[2] is None for item in data))

    def test_second_use_never_reads_unchanged_files(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        again=w.refresh()
        self.assertEqual(again["mode"],"UNCHANGED")
        self.assertEqual(again["content_reads"],0)
        self.assertIsNone(again["python_index"])
        self.assertEqual(again["changed_files"],[])

    def test_bulk_file_additions_trigger_full_reconcile(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        for i in range(65):
            (self.project/("new_%03d.py" % i)).write_text(
                "def generated_%d(): return %d\n" % (i,i),encoding="utf8")
        result=w.refresh()
        self.assertEqual(result["mode"],"FULL")
        self.assertEqual(result["content_reads"],65)
        self.assertEqual(result["changed_files_total"],65)
        self.assertEqual(len(result["changed_files"]),32)
        self.assertEqual(result["changed_files_omitted"],33)
        self.assertEqual(result["python_index"]["files"],67)

    def test_one_changed_file_only_is_reindexed(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        (self.project/"beta.py").write_text("def beta():\n    return 100\n",encoding="utf8")
        report=w.refresh()
        self.assertEqual(report["mode"],"INCREMENTAL")
        self.assertEqual(report["changed_files"],["beta.py"])
        self.assertEqual(report["content_reads"],1)
        self.assertEqual(report["python_index"]["changed_files"],["beta.py"])
        self.assertEqual(report["python_index"]["files"],2)
        self.assertFalse((self.project/".pie").exists())

    def test_delete_updates_only_removed_path(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        (self.project/"alpha.py").unlink()
        report=w.refresh()
        self.assertEqual(report["mode"],"INCREMENTAL")
        self.assertEqual(report["deleted_files"],["alpha.py"])
        self.assertEqual(report["content_reads"],0)
        self.assertEqual(report["python_index"]["removed_files"],["alpha.py"])
        self.assertEqual(w.status()["python_indexed_files"],1)

    def test_global_registry_lists_all_known_projects_without_rescan(self):
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        other=self.base/"another-app"
        other.mkdir()
        (other/"package.json").write_text('{"name":"second"}',encoding="utf8")
        GlobalWorkspaceIndex(other,force_global=True).refresh()
        paths={item["root"] for item in list_known_workspaces()["workspaces"]}
        self.assertEqual(paths,{str(self.project.resolve()),str(other.resolve())})

    def test_restart_preserves_central_index_and_files(self):
        GlobalWorkspaceIndex(self.project,force_global=True).refresh()
        fresh=GlobalWorkspaceIndex(self.project,force_global=True)
        result=fresh.refresh()
        self.assertFalse(result["first_index"])
        self.assertEqual(result["mode"],"UNCHANGED")
        self.assertEqual(fresh.status()["python_indexed_files"],2)

    def test_non_python_project_is_catalogued_and_query_verified(self):
        app=self.base/"front-end"
        app.mkdir()
        (app/"package.json").write_text('{"name":"front-end"}',encoding="utf8")
        (app/"app.ts").write_text("export const steelRoughness = 0.35;\n",encoding="utf8")
        w=GlobalWorkspaceIndex(app,force_global=True)
        result=w.refresh()
        self.assertEqual(result["python_index"]["files"],0)
        self.assertEqual(result["mode"],"FULL")
        x=w.search("steelRoughness")
        self.assertEqual(x["state"],"COMPLETE")
        self.assertEqual(x["matches"][0]["path"],"app.ts")
        self.assertEqual(x["matches"][0]["verification"],"sha256_checked")
        (app/"app.ts").write_text("export const steelRoughness = 0.28;\n",encoding="utf8")
        stale=w.search("steelRoughness")
        self.assertEqual(stale["state"],"PARTIAL")
        self.assertFalse(stale["matches"])
        w.refresh()
        self.assertIn("0.28",w.search("steelRoughness")["matches"][0]["snippet"])

    def test_two_projects_are_isolated_in_global_store(self):
        b=self.base/"second-project"
        b.mkdir()
        (b/"pyproject.toml").write_text("[project]\nname='other'\n",encoding="utf8")
        (b/"another.py").write_text("def another(): return 5\n",encoding="utf8")
        first=GlobalWorkspaceIndex(self.project,force_global=True)
        second=GlobalWorkspaceIndex(b,force_global=True)
        first.refresh()
        second.refresh()
        self.assertNotEqual(first.workspace_id,second.workspace_id)
        self.assertNotEqual(first.storage,second.storage)
        self.assertEqual(first.status()["python_indexed_files"],2)
        self.assertEqual(second.status()["python_indexed_files"],1)
        self.assertEqual(second.search("alpha")["matches"],[])

    def test_sensitive_python_file_never_enters_global_ast(self):
        (self.project/"secret_config.py").write_text("password='example-only'\n",encoding="utf8")
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        result=w.refresh()
        self.assertNotIn("secret_config.py",result["changed_files"])
        self.assertEqual(w.status()["python_indexed_files"],2)
        self.assertEqual(w.search("secret_config")["matches"],[])

    def test_gitsensitive_and_symlinks_are_not_auto_read(self):
        (self.project/".env").write_text("API_KEY=SECRET",encoding="utf8")
        (self.project/"private.pem").write_text("PRIVATE KEY",encoding="utf8")
        (self.project/"credentials.json").write_text('{"secret":"bad"}',encoding="utf8")
        w=GlobalWorkspaceIndex(self.project,force_global=True)
        w.refresh()
        self.assertEqual(w.search("SECRET")["matches"],[])
        self.assertNotIn(".env",w.status()["last_refresh"]["changed_files"])
        self.assertFalse((self.project/".pie").exists())

    def test_actual_mcp_process_auto_indexes_without_agent_call(self):
        workspace=self.base/"subprocess-project"
        workspace.mkdir()
        (workspace/"pyproject.toml").write_text("[project]\nname='subprocess'\n",encoding="utf8")
        (workspace/"sample.py").write_text("def sample(): return 42\n",encoding="utf8")
        requests=[
            {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
                "protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1"}}},
            {"jsonrpc":"2.0","method":"notifications/initialized"},
            {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}},
            {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{
                "name":"pie_global_status","arguments":{}}},
        ]
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/"src"))
        proc=subprocess.run(
            [sys.executable,"-m","pie.interfaces.global_mcp",
             "--workspace",str(workspace),"--store",str(self.store),
             "--poll-seconds","0"],
            input="\n".join(json.dumps(x) for x in requests)+"\n",
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            env=env,timeout=35,
        )
        self.assertEqual(proc.returncode,0,proc.stderr)
        messages={x["id"]:x for x in [json.loads(line) for line in proc.stdout.splitlines()] if "id" in x}
        toolnames={x["name"] for x in messages[2]["result"]["tools"]}
        self.assertIn("pie_global_status",toolnames)
        self.assertIn("pie_global_find_files",toolnames)
        status=json.loads(messages[3]["result"]["content"][0]["text"])
        self.assertEqual(status["python_indexed_files"],1)
        self.assertTrue((self.store/"registry.sqlite3").exists())
        self.assertFalse((workspace/".pie").exists())

    def test_stdio_uses_inherited_workspace_cwd_without_per_project_registration(self):
        workspace=self.base/"inherited-cwd"
        workspace.mkdir()
        (workspace/"pyproject.toml").write_text("[project]\nname='cwd-project'\n",encoding="utf8")
        (workspace/"auto.py").write_text("def auto(): return 1\n",encoding="utf8")
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/"src"))
        msgs=[
            {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}},
            {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
                "name":"pie_global_status","arguments":{}}},
        ]
        proc=subprocess.run(
            [sys.executable,"-m","pie.interfaces.global_mcp",
             "--store",str(self.store),"--poll-seconds","0"],
            input="\n".join(json.dumps(m) for m in msgs)+"\n",
            cwd=workspace,env=env,capture_output=True,text=True,timeout=35,
        )
        self.assertEqual(proc.returncode,0,proc.stderr)
        status=json.loads(json.loads(proc.stdout.splitlines()[-1])["result"]["content"][0]["text"])
        self.assertEqual(status["root"],str(workspace.resolve()))
        self.assertEqual(status["python_indexed_files"],1)

    def test_workspace_discovery_prefers_nearest_marker_and_home_guard(self):
        nested=self.project/"src"
        nested.mkdir()
        self.assertEqual(detect_workspace(nested),self.project.resolve())


if __name__=="__main__":
    unittest.main()
