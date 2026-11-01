import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pie.graph.relationships import build_relationships, get_relationships
from pie.retrieval.context import build_context
from pie.interfaces.mcp_server import dispatch

class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'.pie').mkdir()
        content=b'import os\n\ndef greet():\n    print("hi")\n'
        (self.root/'app.py').write_bytes(content)
        from hashlib import sha256
        conn=sqlite3.connect(self.root/'.pie'/'index.sqlite3')
        conn.executescript('''CREATE TABLE files(id INTEGER PRIMARY KEY,path TEXT,sha256 TEXT);
            CREATE TABLE symbols(id INTEGER PRIMARY KEY,file_id INTEGER,qualified_name TEXT,name TEXT,kind TEXT,start_line INT,end_line INT);
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
            INSERT INTO metadata VALUES('index_state','CURRENT');
            INSERT INTO symbols VALUES(1,1,'greet','greet','function',3,4);''')
        conn.execute('INSERT INTO files VALUES(1,?,?)',('app.py',sha256(content).hexdigest()))
        conn.commit();conn.close()

    def test_graph_and_context(self):
        result=build_relationships(self.root)
        self.assertGreaterEqual(result['stored'],2)
        rels=get_relationships(self.root,'greet')
        self.assertTrue(any(r['target_expression']=='print' and r['resolution_status']=='unresolved' for r in rels['relations']))
        ctx=build_context(self.root,'greet')
        self.assertEqual(ctx['index_state'],'CURRENT')
        self.assertIn('print',ctx['source_ranges'][0]['content'])

    def test_mcp_dispatch(self):
        hello=dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},self.root)
        self.assertEqual(hello['result']['serverInfo']['name'],'pie')
        self.assertIn('pie_build_context',[x['name'] for x in dispatch({'id':2,'method':'tools/list'},self.root)['result']['tools']])
        reply=dispatch({'id':3,'method':'tools/call','params':{'name':'pie_build_context','arguments':{'query':'greet'}}},self.root)
        self.assertIn('greet',reply['result']['content'][0]['text'])

    def test_source_hash_mismatch_does_not_return_code(self):
        (self.root/'app.py').write_text('def changed(): pass')
        self.assertEqual(build_context(self.root,'greet')['source_ranges'],[])
        with self.assertRaisesRegex(ValueError,'Stale source'):
            build_relationships(self.root)


    def test_relationships_report_drift_when_source_changes_after_build(self):
        # get_relationships must not present edges as CURRENT once the underlying
        # file changed on disk without reindexing: those edges carry line numbers
        # and enclosing symbols taken from that very file. The stored index
        # fingerprint cannot notice this because it only reflects database rows.
        build_relationships(self.root)
        fresh = get_relationships(self.root, "greet")
        self.assertEqual(fresh["relations_state"], "CURRENT")
        self.assertEqual(fresh["drifted_sources"], [])

        (self.root / "app.py").write_text(
            'def greet():\n    print("changed")\n    # drift\n', encoding="utf-8"
        )
        stale = get_relationships(self.root, "greet")
        self.assertEqual(stale["drifted_sources"], ["app.py"])
        self.assertEqual(stale["relations_state"], "STALE")
if __name__ == '__main__':
    unittest.main()
