import sqlite3
import tempfile
import unittest
from pathlib import Path

from pie.indexing.indexer import index_project
from pie.indexing.multilang import parse_content
from pie.scanning.discovery import discover_files


class MultiLanguageIndexTests(unittest.TestCase):
    def test_adapters_extract_conservative_symbols_and_imports(self):
        result = parse_content(b'#include <vector>\nclass Robot {}\nvoid paint() {}\n', 'robot.cpp', 'cpp')
        self.assertEqual(result.status, 'parsed')
        self.assertEqual([symbol.name for symbol in result.symbols], ['Robot', 'paint'])
        self.assertEqual([item.module for item in result.imports], ['vector'])

    def test_index_inventories_engine_files_and_keeps_python_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'native.cpp').write_text('#include <vector>\nclass Robot {}\n', encoding='utf-8')
            (root / 'tool.py').write_text('def export_arm():\n    return 1\n', encoding='utf-8')
            (root / 'project.godot').write_text('config_version=5\n', encoding='utf-8')
            (root / 'model.arm').write_bytes(b'ARM')
            result = index_project(root)
            self.assertEqual(result['index_state'], 'CURRENT')
            self.assertEqual(result['files'], 4)
            connection = sqlite3.connect(root / '.pie' / 'index.sqlite3')
            try:
                files = dict(connection.execute('SELECT path, language FROM files'))
                self.assertEqual(files['native.cpp'], 'cpp')
                self.assertEqual(files['project.godot'], 'godot_project')
                self.assertEqual(files['model.arm'], 'armorpaint_asset')
                observations = dict(connection.execute('SELECT f.path, p.status FROM parse_observations p JOIN files f ON f.id=p.file_id'))
                self.assertEqual(observations['native.cpp'], 'parsed')
                self.assertEqual(observations['project.godot'], 'metadata_only')
                names = [row[0] for row in connection.execute('SELECT name FROM symbols ORDER BY name')]
                self.assertEqual(names, ['Robot', 'export_arm'])
            finally:
                connection.close()

    def test_reindex_backfills_missing_observation_without_duplicate_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'tool.py'
            source.write_text('def export_arm():\n    return 1\n', encoding='utf-8')
            index_project(root)
            connection = sqlite3.connect(root / '.pie' / 'index.sqlite3')
            try:
                connection.execute('DELETE FROM parse_observations')
                connection.commit()
            finally:
                connection.close()
            index_project(root)
            connection = sqlite3.connect(root / '.pie' / 'index.sqlite3')
            try:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM parse_observations').fetchone()[0], 1)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM symbols WHERE name = "export_arm"').fetchone()[0], 1)
            finally:
                connection.close()

    def test_discovery_maps_3d_ecosystem_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('a.cpp', 'b.cs', 'c.java', 'k.kt', 'd.hx', 'e.gd', 'f.shader', 'g.gdshader', 'h.uproject', 'i.arm', 'j.blend'):
                (root / name).write_text('{}', encoding='utf-8')
            self.assertEqual({record.language for record in discover_files(root)}, {
                'cpp', 'csharp', 'java', 'kotlin', 'haxe', 'gdscript', 'shader', 'unreal_project', 'armorpaint_asset', 'blender_asset'
            })


if __name__ == '__main__':
    unittest.main()
