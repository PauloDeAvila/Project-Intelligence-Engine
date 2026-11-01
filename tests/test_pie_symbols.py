"""Acceptance tests for the symbol intelligence layer (PIE P0, Etapas A-D).

The tests are written against observable behaviour, not internal helpers: the
golden ``MAX_RETRIES`` scenario is queried end-to-end through the indexer and the
public retrieval API, exactly as an agent would use it.
"""
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.analysis.references import collect_usages
from pie.analysis.resolver import Resolver, analyze_source
from pie.analysis.scopes import build_scopes
from pie.indexing.indexer import index_project
from pie.interfaces.mcp_server import dispatch
from pie.retrieval.symbols import analysis_summary, describe_binding, find_definitions, find_references
from pie.storage.database import connect


def resolve_all(sources):
    """Analyse several modules together and return every reference."""
    analyses = [analyze_source(text, path) for path, text in sources.items()]
    return Resolver([]).resolve_all(analyses)


class GoldenMaxRetriesTests(unittest.TestCase):
    """The scenario that must work for PIE to be worth anything."""

    CONFIG = "MAX_RETRIES = 3\n"
    CLIENT = (
        "from config import MAX_RETRIES\n"
        "\n"
        "def request():\n"
        "    for attempt in range(MAX_RETRIES):\n"
        "        send_request()\n"
    )

    def test_definition_import_and_read_are_linked(self):
        references = resolve_all({"config.py": self.CONFIG, "client.py": self.CLIENT})
        read = next(r for r in references if r.path == "client.py" and r.name == "MAX_RETRIES")
        self.assertEqual(read.context, "load")
        self.assertEqual(read.scope_key, "function:request")
        self.assertEqual(read.resolution, "verified")
        self.assertEqual(read.target_binding_key, "config.py::module::MAX_RETRIES")
        self.assertEqual(read.via, "client.py::module::MAX_RETRIES")
        self.assertIn("config", read.evidence)

    def test_unresolved_call_is_not_fabricated(self):
        references = resolve_all({"config.py": self.CONFIG, "client.py": self.CLIENT})
        call = next(r for r in references if r.name == "send_request")
        self.assertEqual(call.resolution, "unresolved")
        self.assertIsNone(call.target_binding_key)

    def test_reverse_query_lists_the_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "config.py").write_text(self.CONFIG, encoding="utf-8")
            (root / "client.py").write_text(self.CLIENT, encoding="utf-8")
            index_project(root)

            result = find_references(root, "MAX_RETRIES")
            consumers = {(item["path"], item["consumer_symbol"]) for item in result["references"]}
            self.assertIn(("client.py", "request"), consumers)
            read = next(item for item in result["references"] if item["path"] == "client.py")
            self.assertEqual(read["target"], "config.py::module::MAX_RETRIES")
            self.assertEqual(read["resolution"], "verified")

            definitions = find_definitions(root, "MAX_RETRIES")
            by_path = {item["path"]: item for item in definitions["definitions"]}
            self.assertEqual(by_path["config.py"]["kind"], "constant")
            self.assertEqual(by_path["config.py"]["inferred_type"], "int")
            self.assertEqual(by_path["client.py"]["kind"], "import")
            self.assertEqual(by_path["client.py"]["imported_from"], "config")

            report = describe_binding(root, "config.py::module::MAX_RETRIES")
            self.assertIn("client.py", report["consumers"]["files"])
            self.assertIn("request", report["consumers"]["symbols"])
            self.assertEqual(report["unresolved_references"], 0)

    def test_change_is_traceable_through_the_import_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "config.py").write_text(self.CONFIG, encoding="utf-8")
            (root / "client.py").write_text(self.CLIENT, encoding="utf-8")
            index_project(root)
            result = find_references(root, "MAX_RETRIES")
            read = next(item for item in result["references"] if item["path"] == "client.py")
            # The path definition -> import -> read is fully recorded, not implied.
            self.assertEqual(read["target"], "config.py::module::MAX_RETRIES")
            self.assertEqual(read["via_import"], "client.py::module::MAX_RETRIES")
            self.assertEqual(read["consumer_scope"], "function:request")
            self.assertEqual(read["line"], 4)


class ShadowingAndScopeTests(unittest.TestCase):
    def test_local_binding_wins_over_module_constant(self):
        source = (
            "MAX_RETRIES = 3\n"
            "\n"
            "def exemplo():\n"
            "    MAX_RETRIES = 8\n"
            "    return MAX_RETRIES\n"
        )
        references = resolve_all({"app.py": source})
        read = next(r for r in references if r.context == "load" and r.line == 5)
        self.assertEqual(read.target_binding_key, "app.py::function:exemplo::MAX_RETRIES")
        self.assertEqual(read.resolution, "verified")

    def test_reader_outside_the_function_keeps_the_module_binding(self):
        source = (
            "MAX_RETRIES = 3\n"
            "\n"
            "def exemplo():\n"
            "    MAX_RETRIES = 8\n"
            "    return MAX_RETRIES\n"
            "\n"
            "def outro():\n"
            "    return MAX_RETRIES\n"
        )
        references = resolve_all({"app.py": source})
        read = next(r for r in references if r.line == 8)
        self.assertEqual(read.target_binding_key, "app.py::module::MAX_RETRIES")

    def test_global_declaration_writes_the_module_binding(self):
        source = (
            "COUNTER = 0\n"
            "\n"
            "def bump():\n"
            "    global COUNTER\n"
            "    COUNTER += 1\n"
            "    return COUNTER\n"
        )
        references = resolve_all({"app.py": source})
        inside = [r for r in references if r.path == "app.py" and r.line >= 5]
        self.assertTrue(inside)
        self.assertTrue(all(r.target_binding_key == "app.py::module::COUNTER" for r in inside))
        # AugAssign is both a read and a write.
        contexts = {r.context for r in inside if r.line == 5}
        self.assertEqual(contexts, {"load", "store"})

    def test_nonlocal_resolves_to_the_closing_function(self):
        source = (
            "def outer():\n"
            "    total = 0\n"
            "    def inner():\n"
            "        nonlocal total\n"
            "        total += 1\n"
            "        return total\n"
            "    return inner\n"
        )
        references = resolve_all({"app.py": source})
        inner = [r for r in references if r.scope_key.startswith("function:outer.function:inner")]
        self.assertTrue(inner)
        self.assertTrue(all(r.target_binding_key == "app.py::function:outer::total" for r in inner))
        self.assertTrue(all(r.resolution == "verified" for r in inner))

    def test_comprehension_target_is_private(self):
        source = (
            "values = [1, 2, 3]\n"
            "doubled = [value * 2 for value in values]\n"
            "print(value)\n"
        )
        references = resolve_all({"app.py": source})
        leaked = next(r for r in references if r.name == "value" and r.line == 3)
        # The comprehension variable is gone: ``value`` is not a module binding.
        self.assertEqual(leaked.resolution, "unresolved")
        inside = next(r for r in references if r.name == "value" and r.line == 2)
        self.assertEqual(inside.resolution, "verified")

    def test_walrus_in_comprehension_binds_the_enclosing_function(self):
        source = (
            "def scan(items):\n"
            "    found = [last := item for item in items]\n"
            "    return last\n"
        )
        references = resolve_all({"app.py": source})
        read = next(r for r in references if r.name == "last" and r.line == 3)
        self.assertEqual(read.target_binding_key, "app.py::function:scan::last")

    def test_class_body_is_invisible_to_methods(self):
        source = (
            "class Box:\n"
            "    size = 3\n"
            "    def get(self):\n"
            "        return size\n"
        )
        references = resolve_all({"app.py": source})
        read = next(r for r in references if r.name == "size" and r.context == "load")
        self.assertEqual(read.resolution, "unresolved")
        self.assertIn("class scope", read.evidence)


class AttributeAndImportTests(unittest.TestCase):
    def test_class_attribute_read_through_self_and_class(self):
        source = (
            "class Box:\n"
            "    size = 3\n"
            "    def grow(self):\n"
            "        self.size = self.size + Box.size\n"
        )
        references = resolve_all({"app.py": source})
        attribute_reads = [r for r in references if r.attribute_base is None and r.name == "size"]
        self.assertTrue(attribute_reads)
        self.assertTrue(all(r.target_binding_key == "app.py::class:Box::size" for r in attribute_reads))
        self.assertTrue(all(r.resolution == "verified" for r in attribute_reads))

    def test_aliased_from_import_points_at_the_original(self):
        sources = {
            "limits.py": "LIMIT = 10\n",
            "user.py": "from limits import LIMIT as CAP\n\ndef f():\n    return CAP\n",
        }
        references = resolve_all(sources)
        read = next(r for r in references if r.path == "user.py" and r.name == "CAP")
        self.assertEqual(read.resolution, "verified")
        self.assertEqual(read.target_binding_key, "limits.py::module::LIMIT")

    def test_aliased_module_import_attribute(self):
        sources = {
            "limits.py": "LIMIT = 10\n",
            "user.py": "import limits as lim\n\ndef f():\n    return lim.LIMIT\n",
        }
        references = resolve_all(sources)
        read = next(r for r in references if r.path == "user.py" and r.name == "LIMIT")
        self.assertEqual(read.target_binding_key, "limits.py::module::LIMIT")
        self.assertEqual(read.resolution, "verified")

    def test_unindexed_module_is_unresolved_not_guessed(self):
        sources = {"user.py": "import requests\n\ndef f():\n    return requests.get\n"}
        references = resolve_all(sources)
        attribute = next(r for r in references if r.name == "get")
        self.assertEqual(attribute.resolution, "unresolved")
        self.assertIsNone(attribute.target_binding_key)

    def test_star_import_is_probable_not_verified(self):
        sources = {
            "limits.py": "LIMIT = 10\n",
            "user.py": "from limits import *\n\ndef f():\n    return LIMIT\n",
        }
        references = resolve_all(sources)
        read = next(r for r in references if r.name == "LIMIT" and r.path == "user.py")
        self.assertEqual(read.resolution, "probable")

    def test_ambiguous_module_name_is_unresolved(self):
        sources = {
            "pkg/limits.py": "LIMIT = 10\n",
            "limits.py": "LIMIT = 99\n",
            "user.py": "from limits import LIMIT\n\ndef f():\n    return LIMIT\n",
        }
        references = resolve_all(sources)
        read = next(r for r in references if r.name == "LIMIT" and r.path == "user.py")
        self.assertEqual(read.resolution, "unresolved")
        self.assertIn("ambiguous", read.evidence)


    def test_from_package_import_module_resolves_to_the_submodule(self):
        sources = {
            "pkg/__init__.py": "",
            "pkg/limits.py": "LIMIT = 10\n",
            "user.py": "from pkg import limits\n\ndef f():\n    return limits.LIMIT\n",
        }
        references = resolve_all(sources)
        attribute = next(r for r in references if r.path == "user.py" and r.name == "LIMIT")
        self.assertEqual(attribute.resolution, "verified")
        self.assertEqual(attribute.target_binding_key, "pkg/limits.py::module::LIMIT")
        self.assertEqual(attribute.via, "user.py::module::limits")

    def test_submodule_used_as_a_plain_name_resolves_to_the_module(self):
        sources = {
            "pkg/__init__.py": "",
            "pkg/limits.py": "LIMIT = 10\n",
            "user.py": "from pkg import limits\n\ndef f():\n    return limits\n",
        }
        references = resolve_all(sources)
        read = next(r for r in references if r.path == "user.py" and r.name == "limits")
        self.assertEqual(read.resolution, "verified")
        self.assertEqual(read.target_name, "pkg.limits")

    def test_attribute_of_a_renamed_submodule_still_resolves(self):
        sources = {
            "pkg/__init__.py": "",
            "pkg/limits.py": "LIMIT = 10\n",
            "user.py": "from pkg import limits as lim\n\ndef f():\n    return lim.LIMIT\n",
        }
        references = resolve_all(sources)
        attribute = next(r for r in references if r.path == "user.py" and r.name == "LIMIT")
        self.assertEqual(attribute.resolution, "verified")
        self.assertEqual(attribute.target_binding_key, "pkg/limits.py::module::LIMIT")

    def test_missing_submodule_reports_the_real_reason(self):
        sources = {
            "pkg/__init__.py": "",
            "user.py": "from pkg import absent\n\ndef f():\n    return absent\n",
        }
        references = resolve_all(sources)
        read = next(r for r in references if r.path == "user.py" and r.name == "absent")
        self.assertEqual(read.resolution, "unresolved")
        self.assertIsNone(read.target_binding_key)


class NegativeIsolationTests(unittest.TestCase):
    """Same name must never mean same variable."""

    def test_two_same_named_locals_are_distinct(self):
        source = (
            "def first():\n"
            "    counter = 1\n"
            "    return counter\n"
            "\n"
            "def second():\n"
            "    counter = 2\n"
            "    return counter\n"
        )
        references = resolve_all({"app.py": source})
        first = next(r for r in references if r.line == 3)
        second = next(r for r in references if r.line == 7)
        self.assertEqual(first.target_binding_key, "app.py::function:first::counter")
        self.assertEqual(second.target_binding_key, "app.py::function:second::counter")
        self.assertNotEqual(first.target_binding_key, second.target_binding_key)

    def test_same_named_module_constants_in_different_files_are_distinct(self):
        sources = {
            "a.py": "TIMEOUT = 1\n\ndef read():\n    return TIMEOUT\n",
            "b.py": "TIMEOUT = 2\n\ndef read():\n    return TIMEOUT\n",
        }
        references = resolve_all(sources)
        a = next(r for r in references if r.path == "a.py" and r.context == "load")
        b = next(r for r in references if r.path == "b.py" and r.context == "load")
        self.assertEqual(a.target_binding_key, "a.py::module::TIMEOUT")
        self.assertEqual(b.target_binding_key, "b.py::module::TIMEOUT")

    def test_local_shadow_does_not_consume_the_module_constant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "app.py").write_text(
                "MAX_RETRIES = 3\n"
                "\n"
                "def exemplo():\n"
                "    MAX_RETRIES = 8\n"
                "    return MAX_RETRIES\n",
                encoding="utf-8",
            )
            index_project(root)
            report = describe_binding(root, "app.py::module::MAX_RETRIES")
            # The only reader of the module constant is its own assignment.
            consumer_scopes = {item["scope_key"] for item in report["references"]}
            self.assertEqual(consumer_scopes, {"module"})
            local = describe_binding(root, "app.py::function:exemplo::MAX_RETRIES")
            self.assertEqual({item["scope_key"] for item in local["references"]}, {"function:exemplo"})


class DefinitionInventoryTests(unittest.TestCase):
    def test_all_assignment_forms_are_recorded(self):
        source = (
            "LIMIT = 10\n"
            "total: int = 0\n"
            "count = 0\n"
            "count += 1\n"
            "left, right = 1, 2\n"
            "head, *tail = [1, 2, 3]\n"
        )
        definitions = analyze_source(source, "app.py").definitions
        by_name = {}
        for definition in definitions:
            by_name.setdefault(definition.name, []).append(definition)
        self.assertEqual([item.declared_by for item in by_name["LIMIT"]], ["assign"])
        self.assertEqual([item.declared_by for item in by_name["total"]], ["annassign"])
        self.assertEqual(by_name["total"][0].inferred_type, "int")
        self.assertEqual([item.declared_by for item in by_name["count"]], ["assign", "augassign"])
        self.assertEqual([item.declared_by for item in by_name["left"]], ["assign"])
        self.assertEqual([item.declared_by for item in by_name["right"]], ["assign"])
        self.assertEqual([item.declared_by for item in by_name["tail"]], ["assign"])

    def test_rebinding_sites_share_one_identity(self):
        source = "value = 1\nvalue = 2\nprint(value)\n"
        analysis = analyze_source(source, "app.py")
        sites = [item for item in analysis.definitions if item.name == "value"]
        self.assertEqual(len(sites), 2)
        self.assertEqual({item.binding_key for item in sites}, {"app.py::module::value"})
        self.assertEqual([item.line for item in sites], [1, 2])
        references = Resolver([]).resolve_all([analysis])
        read = next(item for item in references if item.context == "load" and item.name == "value")
        # The read after the rebinding is attributed to the later site.
        self.assertEqual(read.target_line, 2)

    def test_parameters_and_attributes_are_recorded(self):
        source = (
            "class Service:\n"
            "    retries = 5\n"
            "    def __init__(self, name: str):\n"
            "        self.name = name\n"
        )
        definitions = analyze_source(source, "service.py").definitions
        kinds = {(item.name, item.kind, item.scope_key) for item in definitions}
        self.assertIn(("retries", "attribute", "class:Service"), kinds)
        self.assertIn(("name", "parameter", "class:Service.function:__init__"), kinds)
        self.assertIn(("name", "instance_attribute", "class:Service"), kinds)
        parameter = next(item for item in definitions if item.kind == "parameter" and item.name == "name")
        self.assertEqual(parameter.inferred_type, "str")

    def test_type_inference_stays_conservative(self):
        source = (
            "flag = True\n"
            "ratio = 1.5\n"
            "name = 'pie'\n"
            "items = [1]\n"
            "mapping = {}\n"
            "opaque = build()\n"
        )
        inferred = {item.name: item.inferred_type for item in analyze_source(source, "app.py").definitions}
        self.assertEqual(inferred["flag"], "bool")
        self.assertEqual(inferred["ratio"], "float")
        self.assertEqual(inferred["name"], "str")
        self.assertEqual(inferred["items"], "list")
        self.assertEqual(inferred["mapping"], "dict")
        self.assertIsNone(inferred["opaque"])

    def test_delete_is_recorded_as_a_usage(self):
        source = "value = 1\ndel value\n"
        references = Resolver([]).resolve_all([analyze_source(source, "app.py")])
        deletion = next(item for item in references if item.context == "del")
        self.assertEqual(deletion.target_binding_key, "app.py::module::value")


class ScopeHelperTests(unittest.TestCase):
    def test_function_scopes_uses_its_own_constants(self):
        from pie.analysis.definitions import function_scopes

        source = "def outer():\n    return [x for x in range(3)]\n"
        analysis = analyze_source(source, "app.py")
        keys = sorted(scope.key for scope in function_scopes(analysis.builder))
        self.assertIn("function:outer", keys)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name).resolve()
        (self.root / "config.py").write_text("MAX_RETRIES = 3\n", encoding="utf-8")
        (self.root / "client.py").write_text(
            "from config import MAX_RETRIES\n\ndef request():\n    return MAX_RETRIES\n",
            encoding="utf-8",
        )

    def test_index_reports_analysis_counts(self):
        result = index_project(self.root)
        self.assertGreater(result["definitions"], 0)
        self.assertGreater(result["references"], 0)
        summary = analysis_summary(self.root)
        self.assertEqual(summary["dangling_targets"], 0)
        self.assertIn("verified", summary["references_by_resolution"])

    def test_referential_integrity_and_foreign_keys(self):
        index_project(self.root)
        connection = connect(self.root / ".pie" / "index.sqlite3")
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            connection.close()

    def test_incremental_update_only_reanalyses_affected_files(self):
        index_project(self.root)
        connection = connect(self.root / ".pie" / "index.sqlite3")
        try:
            before = connection.execute(
                "SELECT COUNT(*) FROM definitions WHERE file_id = (SELECT id FROM files WHERE path='client.py')"
            ).fetchone()[0]
        finally:
            connection.close()
        (self.root / "client.py").write_text(
            "from config import MAX_RETRIES\n\ndef request():\n    return MAX_RETRIES * 2\n",
            encoding="utf-8",
        )
        index_project(self.root)
        connection = connect(self.root / ".pie" / "index.sqlite3")
        try:
            after = connection.execute(
                "SELECT COUNT(*) FROM definitions WHERE file_id = (SELECT id FROM files WHERE path='client.py')"
            ).fetchone()[0]
            # Rows are replaced, never accumulated.
            self.assertEqual(before, after)
        finally:
            connection.close()
        result = find_references(self.root, "MAX_RETRIES")
        self.assertTrue(any(item["path"] == "client.py" for item in result["references"]))

    def test_changing_the_defining_module_updates_dependents(self):
        index_project(self.root)
        # config.py moves the constant: client.py itself is untouched.
        (self.root / "config.py").write_text("\n\nMAX_RETRIES = 9\n", encoding="utf-8")
        index_project(self.root)
        result = find_references(self.root, "MAX_RETRIES")
        read = next(item for item in result["references"] if item["path"] == "client.py")
        self.assertEqual(read["resolution"], "verified")
        definition = next(item for item in result["definitions"] if item["path"] == "config.py")
        self.assertEqual(definition["line"], 3)
        self.assertEqual(read["target"], "config.py::module::MAX_RETRIES")

    def test_removing_the_definition_demotes_dependent_references(self):
        index_project(self.root)
        (self.root / "config.py").write_text("OTHER = 1\n", encoding="utf-8")
        index_project(self.root)
        connection = connect(self.root / ".pie" / "index.sqlite3")
        try:
            row = connection.execute(
                "SELECT resolution, target_binding_key FROM usages WHERE name = 'MAX_RETRIES' AND line = 4"
            ).fetchone()
            self.assertEqual(row["resolution"], "unresolved")
            self.assertIsNone(row["target_binding_key"])
        finally:
            connection.close()
        self.assertEqual(analysis_summary(self.root)["dangling_targets"], 0)

    def test_deleting_a_file_removes_its_references(self):
        index_project(self.root)
        (self.root / "client.py").unlink()
        index_project(self.root)
        result = find_references(self.root, "MAX_RETRIES")
        self.assertFalse([item for item in result["references"] if item["path"] == "client.py"])
        self.assertEqual(analysis_summary(self.root)["dangling_targets"], 0)

    def test_legacy_v02_database_is_migrated_and_reanalysed(self):
        database = self.root / ".pie" / "index.sqlite3"
        database.parent.mkdir()
        connection = sqlite3.connect(database)
        connection.executescript(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, "
            "size INTEGER NOT NULL, language TEXT, parse_status TEXT NOT NULL);"
            "CREATE TABLE symbols (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE, "
            "qualified_name TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, start_line INTEGER NOT NULL, "
            "end_line INTEGER NOT NULL, start_col INTEGER NOT NULL, end_col INTEGER NOT NULL, "
            "UNIQUE(file_id, qualified_name, kind));"
            "CREATE TABLE imports (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE, "
            "module TEXT NOT NULL, imported_name TEXT, alias TEXT, line INTEGER NOT NULL);"
            "INSERT INTO metadata VALUES ('index_state', 'CURRENT');"
            "INSERT INTO metadata VALUES ('root', 'legacy');"
        )
        connection.commit()
        connection.close()

        result = index_project(self.root)
        self.assertEqual(result["index_state"], "CURRENT")
        connection = connect(database)
        try:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            self.assertTrue({"definitions", "usages", "star_imports", "analysis_state"} <= tables)
            self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key='root'").fetchone()[0], str(self.root))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            connection.close()
        self.assertTrue(find_definitions(self.root, "MAX_RETRIES")["definitions"])

    def test_unparseable_file_does_not_break_the_layer(self):
        (self.root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
        result = index_project(self.root)
        self.assertEqual(result["index_state"], "PARTIAL")
        self.assertEqual(result["diagnostics"][0]["code"], "parse_error")
        self.assertTrue(find_definitions(self.root, "MAX_RETRIES")["definitions"])

    def test_query_indexes_exist_for_both_directions(self):
        index_project(self.root)
        connection = connect(self.root / ".pie" / "index.sqlite3")
        try:
            indexes = {row["name"] for row in connection.execute("PRAGMA index_list(usages)")}
            self.assertIn("idx_usages_target", indexes)
            self.assertIn("idx_usages_origin", indexes)
            definition_indexes = {row["name"] for row in connection.execute("PRAGMA index_list(definitions)")}
            self.assertIn("idx_definitions_binding", definition_indexes)
            self.assertIn("idx_definitions_name", definition_indexes)
        finally:
            connection.close()


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name).resolve()
        (self.root / "config.py").write_text("MAX_RETRIES = 3\n", encoding="utf-8")
        (self.root / "client.py").write_text(
            "from config import MAX_RETRIES\n\ndef request():\n    return MAX_RETRIES\n",
            encoding="utf-8",
        )
        index_project(self.root)

    def test_cli_exposes_definitions_and_references(self):
        environment = dict(__import__("os").environ, PYTHONPATH=str(ROOT / "src"))
        for command in ("definitions", "references"):
            completed = subprocess.run(
                [sys.executable, "-m", "pie", command, "MAX_RETRIES", "--root", str(self.root)],
                cwd=ROOT, env=environment, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["query"], "MAX_RETRIES")

    def test_mcp_exposes_symbol_intelligence(self):
        tools = {tool["name"] for tool in dispatch({"id": 1, "method": "tools/list"}, self.root)["result"]["tools"]}
        self.assertTrue({"pie_find_definitions", "pie_find_references", "pie_analysis_summary"} <= tools)
        reply = dispatch(
            {"id": 2, "method": "tools/call", "params": {"name": "pie_find_references", "arguments": {"name": "MAX_RETRIES"}}},
            self.root,
        )
        payload = json.loads(reply["result"]["content"][0]["text"])
        self.assertTrue(payload["references"])


if __name__ == "__main__":
    unittest.main()
