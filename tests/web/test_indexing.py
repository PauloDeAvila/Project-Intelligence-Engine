from __future__ import annotations

from dataclasses import replace
import unittest

from pie.web import (
    AccessibilityNode,
    CandidateExtractor,
    LocalWebSearch,
    RegionIndexer,
    SemanticRoleMatcher,
    SnapshotNormalizer,
    SnapshotState,
    WebStateError,
    tokenize,
)


def _snapshot():
    tree = AccessibilityNode(
        role="main",
        name="Conta",
        children=(
            AccessibilityNode(
                role="form",
                name="Login",
                children=(
                    AccessibilityNode(role="textbox", name="Pesquisar"),
                    AccessibilityNode(role="textbox", name="Pesquisar agora"),
                    AccessibilityNode(role="button", name="Entrar"),
                    AccessibilityNode(role="custom-widget", name="Widget externo"),
                ),
            ),
            AccessibilityNode(
                role="navigation",
                name="Menu principal",
                children=(AccessibilityNode(role="link", name="Termos de uso"),),
            ),
            AccessibilityNode(role="table", name="Resultados"),
        ),
    )
    return SnapshotNormalizer().normalize(
        session_id="s1",
        page_id="p1",
        frame_id="main",
        generation=1,
        origin="https://example.test",
        path="/home",
        title="Home",
        tree=tree,
        captured_at="2026-01-01T00:00:00Z",
    ).snapshot


class LocalWebIndexTests(unittest.TestCase):
    def test_tokenization_is_literal_unicode_nfc_and_bounded(self):
        self.assertEqual(tokenize("  PEsquisar\u0301 campo  "), ("pesquisa\u0155", "campo"))
        self.assertEqual(tokenize("[role=button]"), ("role", "button"))
        with self.assertRaises(WebStateError):
            tokenize(" ".join(f"term{i}" for i in range(40)))

    def test_candidate_extractor_keeps_snapshot_binding_and_terms(self):
        snapshot = _snapshot()
        documents = CandidateExtractor().extract(snapshot)
        self.assertEqual(len(documents), len(snapshot.elements))
        self.assertEqual(documents[2].candidate.snapshot_id, snapshot.snapshot_id)
        self.assertIn("pesquisar", documents[2].tokens)
        self.assertIn("login", documents[2].region_tokens)

    def test_region_index_is_sorted_and_literal(self):
        snapshot = _snapshot()
        index = RegionIndexer().build(snapshot)
        self.assertEqual(len(index.refs_for_region("login")), 4)
        self.assertEqual(index.refs_for_role("button"), (snapshot.elements[4].ref,))
        self.assertEqual(index.refs_for_region("[role=button]"), ())

    def test_local_search_finds_field_without_selector_or_external_model(self):
        snapshot = _snapshot()
        search = LocalWebSearch()
        search.register(snapshot)
        field = search.search(snapshot.snapshot_id, "campo de busca")
        self.assertEqual(field.state, SnapshotState.CURRENT)
        self.assertEqual(field.matches[0].candidate.role, "input")
        self.assertIn("semantic_role_match", field.matches[0].reasons)
        self.assertTrue(field.ambiguous)
        self.assertEqual(search.search(snapshot.snapshot_id, "[role=button]").matches, ())

    def test_search_supports_explicit_role_region_and_ambiguity(self):
        snapshot = _snapshot()
        search = LocalWebSearch()
        search.register(snapshot)
        ambiguous = search.search(snapshot.snapshot_id, "pesquisar")
        self.assertTrue(ambiguous.ambiguous)
        self.assertEqual(len(ambiguous.matches), 2)
        login = search.search(
            snapshot.snapshot_id,
            "entrar",
            semantic_role="submit",
            region="login",
        )
        self.assertEqual(login.matches[0].candidate.accessible_name, "Entrar")
        self.assertEqual(login.matches[0].candidate.region, "Login")

    def test_unsupported_are_excluded_by_default_but_not_erased(self):
        snapshot = _snapshot()
        search = LocalWebSearch()
        search.register(snapshot)
        default = search.search(snapshot.snapshot_id, "widget externo")
        self.assertEqual(default.matches, ())
        included = search.search(snapshot.snapshot_id, "widget externo", include_unsupported=True)
        self.assertEqual(len(included.matches), 1)
        self.assertEqual(included.matches[0].candidate.support.value, "UNSUPPORTED")

    def test_stale_snapshot_and_identity_collision_fail_closed(self):
        snapshot = _snapshot()
        search = LocalWebSearch()
        with self.assertRaises(WebStateError):
            search.register(replace(snapshot, state=SnapshotState.STALE))
        search.register(snapshot)
        with self.assertRaises(WebStateError):
            search.register(replace(snapshot, title="Different title"))
        with self.assertRaises(WebStateError):
            search.search(snapshot.snapshot_id, "anything", max_results=0)

    def test_role_matcher_is_closed_and_deterministic(self):
        matcher = SemanticRoleMatcher()
        self.assertEqual(matcher.infer("encontrar o campo de busca"), ("search",))
        self.assertEqual(matcher.matches("botão de enviar", "button"), ("submit",))
        with self.assertRaises(WebStateError):
            matcher.targets_for("eval")


if __name__ == "__main__":
    unittest.main()
