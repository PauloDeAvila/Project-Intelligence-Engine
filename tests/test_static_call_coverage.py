"""Regression contracts for local imports, qualified methods and honest coverage."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pie.analysis.resolver import Resolver, analyze_source
from pie.indexing.indexer import index_project
from pie.retrieval.context_pack import build_context_pack
from pie.retrieval.evidence import EvidenceError


class LocalImportResolutionTests(unittest.TestCase):
    def resolve(self, consumer):
        analyses = [analyze_source(source, path) for path, source in {
            'pkg/quality.py': 'def audit(value):\n    return value\n',
            'pkg/consumer.py': consumer,
        }.items()]
        return [r for r in Resolver([]).resolve_all(analyses)
                if r.path == 'pkg/consumer.py' and r.name == 'audit']

    def test_function_method_closure_comprehension_and_alias_imports(self):
        sources = [
            'def run():\n    from .quality import audit\n    return audit(1)\n',
            'class Runner:\n    def run(self):\n        from .quality import audit\n        return audit(1)\n',
            'def run():\n    from .quality import audit\n    def inner():\n        return audit(1)\n    return inner()\n',
            'def run():\n    from .quality import audit\n    return [audit(x) for x in range(2)]\n',
            'def run():\n    from . import quality as q\n    return q.audit(1)\n',
            'def run():\n    import pkg.quality as q\n    return q.audit(1)\n',
            'def run():\n    from pkg.quality import audit as check\n    return check(1)\n',
        ]
        for source in sources:
            with self.subTest(source=source):
                analyses = [analyze_source('def audit(x):\n    return x\n', 'pkg/quality.py'),
                            analyze_source(source, 'pkg/consumer.py')]
                refs = Resolver([]).resolve_all(analyses)
                target = 'pkg/quality.py::module::audit'
                calls = [r for r in refs if r.path == 'pkg/consumer.py'
                         and r.target_binding_key == target]
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].resolution, 'verified')
                self.assertIsNotNone(calls[0].via)

    def test_rebinding_and_parameter_shadowing_do_not_reach_import(self):
        for source in [
            'def run():\n    from .quality import audit\n    audit = lambda x: x\n    return audit(1)\n',
            'from .quality import audit\ndef run(audit):\n    return audit(1)\n',
            'def run(q):\n    return q.audit(1)\n',
        ]:
            with self.subTest(source=source):
                self.assertFalse(any(r.target_binding_key == 'pkg/quality.py::module::audit'
                                     for r in self.resolve(source)))

    def test_local_import_before_binding_is_not_verified(self):
        for source in [
            'def run():\n    audit(1)\n    from .quality import audit\n',
            'def run():\n    audit(1); from .quality import audit\n',
            'def run():\n    result = [audit(x) for x in range(2)]\n    from .quality import audit\n',
            'def run():\n    result = {audit(x) for x in range(2)}\n    from .quality import audit\n',
            'def run():\n    result = {x: audit(x) for x in range(2)}\n    from .quality import audit\n',
            'def run():\n    q.audit(1); import pkg.quality as q\n',
        ]:
            with self.subTest(source=source):
                refs = self.resolve(source)
                self.assertEqual(refs[0].resolution, 'unresolved')
                self.assertIsNone(refs[0].target_binding_key)

    def test_external_local_import_stays_unresolved(self):
        refs = self.resolve('def run():\n    from missing import audit\n    return audit(1)\n')
        self.assertEqual(refs[0].resolution, 'unresolved')

    def test_import_after_same_line_binding_is_verified(self):
        refs = self.resolve('def run():\n    from .quality import audit; audit(1)\n')
        self.assertEqual(refs[0].resolution, 'verified')

    def test_forward_deferred_closure_is_conservatively_unresolved(self):
        refs = self.resolve('def run():\n    def inner():\n        return audit(1)\n'
                            '    from .quality import audit\n    return inner()\n')
        self.assertEqual(refs[0].resolution, 'unresolved')

    def test_attribute_and_subscript_deletion_do_not_unbind_module_alias(self):
        refs = self.resolve('def run():\n    from . import quality as q\n'
                            '    del q.cache[0], q.cache\n    q.audit(1)\n')
        self.assertEqual(refs[-1].resolution, 'verified')

    def test_deleted_local_import_is_not_a_verified_caller(self):
        for source in [
            'def run():\n    from .quality import audit\n    del audit\n    audit(1)\n',
            'def run():\n    from .quality import audit; del audit; audit(1)\n',
            'def run():\n    import pkg.quality as q\n    del q\n    q.audit(1)\n',
        ]:
            with self.subTest(source=source):
                refs = self.resolve(source)
                self.assertTrue(refs)
                self.assertEqual(refs[-1].resolution, 'unresolved')
                self.assertIsNone(refs[-1].target_binding_key)

    def test_local_reexports_are_followed_and_cycles_are_refused(self):
        for relay, expected in [('from .quality import audit\n', 'verified'),
                                ('from .relay import audit\n', 'unresolved')]:
            with self.subTest(relay=relay):
                analyses = [analyze_source(source, path) for path, source in {
                    'pkg/quality.py': 'def audit(x):\n    return x\n',
                    'pkg/relay.py': relay,
                    'pkg/caller.py': 'def run():\n    from .relay import audit\n    audit(1)\n',
                }.items()]
                refs = Resolver([]).resolve_all(analyses)
                ref = next(r for r in refs if r.path == 'pkg/caller.py' and r.name == 'audit')
                self.assertEqual(ref.resolution, expected)
                if expected == 'unresolved':
                    self.assertIsNone(ref.target_binding_key)

    def test_local_absolute_import_ambiguity_is_not_guessed(self):
        analyses = [analyze_source(source, path) for path, source in {
            'a/quality.py': 'def audit(x):\n    return x\n',
            'b/quality.py': 'def audit(x):\n    return x\n',
            'caller.py': 'def run():\n    from quality import audit\n    audit(1)\n',
        }.items()]
        ref = next(r for r in Resolver([]).resolve_all(analyses)
                   if r.path == 'caller.py' and r.name == 'audit')
        self.assertEqual(ref.resolution, 'unresolved')
        self.assertIn('ambiguous', ref.evidence)


class QualifiedMethodAndCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'cache.py').write_text(
            'class Cache:\n    def get(self, key):\n        return key\n', encoding='utf-8')
        (self.root / 'other.py').write_text(
            'class Other:\n    def get(self, key):\n        return key\n', encoding='utf-8')
        index_project(self.root)

    def test_qualified_method_has_exact_identity_signature_and_partial_coverage(self):
        result = build_context_pack(self.root, 'Cache.get')
        self.assertEqual(result['definition']['path'], 'cache.py')
        self.assertEqual(result['definition']['line'], 2)
        self.assertEqual(result['definition']['signature'], 'def get(self, key):')
        self.assertEqual(result['definition']['binding'], 'cache.py::class:Cache::get')
        coverage = result['coverage']
        self.assertTrue(coverage['returned_verified_call_list_complete'])
        self.assertEqual(coverage['static_analysis_coverage'], 'PARTIAL')
        self.assertFalse(coverage['exhaustive'])
        self.assertNotIn('complete_direct_call_list', coverage)

    def test_bare_and_duplicate_qualified_methods_are_ambiguous(self):
        with self.assertRaisesRegex(EvidenceError, 'AMBIGUOUS'):
            build_context_pack(self.root, 'get')
        (self.root / 'duplicate.py').write_text(
            'class Cache:\n    def get(self, key):\n        return key\n', encoding='utf-8')
        index_project(self.root)
        with self.assertRaisesRegex(EvidenceError, 'AMBIGUOUS'):
            build_context_pack(self.root, 'Cache.get')

    def test_invalid_dotted_queries_fail_closed(self):
        for symbol in ['Cache..get', '.get', 'Cache.get()', 'Cache.get ', 'Cache/ get', 'class.get']:
            with self.subTest(symbol=symbol), self.assertRaises(EvidenceError):
                build_context_pack(self.root, symbol)

    def test_async_method_and_stale_method_refusal(self):
        path = self.root / 'async_cache.py'
        path.write_text('class AsyncCache:\n    async def fetch(self, key):\n        return key\n',
                        encoding='utf-8')
        index_project(self.root)
        pack = build_context_pack(self.root, 'AsyncCache.fetch')
        self.assertEqual(pack['definition']['signature'], 'async def fetch(self, key):')
        path.write_text(path.read_text(encoding='utf-8') + '# changed\n', encoding='utf-8')
        with self.assertRaisesRegex(EvidenceError, 'STALE_PROJECT'):
            build_context_pack(self.root, 'AsyncCache.fetch')

    def test_repeated_method_definition_is_not_silently_selected(self):
        (self.root / 'cache.py').write_text(
            'class Cache:\n    def get(self):\n        return 1\n'
            '    def get(self):\n        return 2\n', encoding='utf-8')
        index_project(self.root)
        with self.assertRaisesRegex(EvidenceError, 'AMBIGUOUS'):
            build_context_pack(self.root, 'Cache.get')

    def test_local_import_call_pack_and_incremental_refresh(self):
        (self.root / 'target.py').write_text('def audit(x):\n    return x\n', encoding='utf-8')
        (self.root / 'caller.py').write_text(
            'def run():\n    from target import audit\n    return [audit(x) for x in range(2)]\n',
            encoding='utf-8')
        index_project(self.root)
        pack = build_context_pack(self.root, 'audit')
        self.assertEqual([(c['path'], c['line']) for c in pack['callers']], [('caller.py', 3)])
        self.assertEqual(len(pack['callers'][0]['source_sha256']), 64)
        (self.root / 'target.py').write_text('def replacement(x):\n    return x\n', encoding='utf-8')
        index_project(self.root)
        with self.assertRaises(EvidenceError):
            build_context_pack(self.root, 'audit')


if __name__ == '__main__':
    unittest.main()
