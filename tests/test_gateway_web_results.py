from __future__ import annotations

import pytest

from pie.gateway.web_results import (
    web_context_query,
    web_result_eligible,
    web_snapshot_preview,
)


def _snapshot(*lines: str) -> str:
    return "### Snapshot\n" + "\n".join(lines)


# A small but structurally valid local-page snapshot: marker line plus one
# heading and one ref-bearing element, comfortably under the former 500-char
# floor that rejected genuine snapshots.
SMALL_VALID = _snapshot(
    "- heading \"Notas locais\" [level=1]",
    "- textbox \"Pesquisar\" [ref=e3]",
    "- link \"Ajuda\" [ref=e2]",
)


def test_small_valid_snapshot_is_eligible():
    assert len(SMALL_VALID) < 500
    assert web_result_eligible(SMALL_VALID, "browser_snapshot")


def test_small_valid_snapshot_is_usable_by_web_context():
    result = web_context_query(SMALL_VALID, "pesquisar", 2000)
    assert result["schema"] == "pie-web-context-v1"
    assert result["complete"] is False
    assert result["trust"] == "UNTRUSTED_PAGE_DATA"
    assert "Pesquisar" in result["preview"]


def test_short_structural_neighbour_below_minimum_is_rejected():
    tiny = _snapshot("- heading \"Oi\" [level=1]")
    assert len(tiny) < 80
    assert not web_result_eligible(tiny, "browser_snapshot")


def test_marker_only_text_under_minimum_is_rejected():
    assert not web_result_eligible("### Snapshot\n- ok", "browser_snapshot")


def test_short_arbitrary_text_is_rejected():
    assert not web_result_eligible("All systems nominal, nothing to report here today at all.", "browser_snapshot")
    assert not web_result_eligible("### Notes\n" + "x" * 100, "browser_snapshot")


def test_unknown_tool_is_rejected():
    assert not web_result_eligible(SMALL_VALID, "browser_evaluate")
    assert not web_result_eligible(SMALL_VALID, "browser_take_screenshot")


def test_secret_material_is_rejected():
    assert not web_result_eligible(
        _snapshot("- heading \"Login\" [level=1]", "- textbox \"Senha\" [ref=e4] password= hunter2"),
        "browser_snapshot",
    )
    assert not web_result_eligible(
        _snapshot("- heading \"Login\" [level=1]", "- text \"Authorization: Bearer abcdef123456\""),
        "browser_snapshot",
    )


def test_error_snapshot_is_rejected():
    assert not web_result_eligible(
        _snapshot("- heading \"Notas\" [level=1]", "### Error", "TimeoutError: page did not load"),
        "browser_navigate",
    )
    assert not web_result_eligible(
        _snapshot("- heading \"Notas\" [level=1]", "- status textbox [ref=e9] failed to load"),
        "browser_navigate",
    )


def test_oversized_snapshot_is_rejected():
    huge = _snapshot("- heading \"Notas\" [level=1]", "- textbox \"Pesquisar\" [ref=e3]", "x" * 500_001)
    assert not web_result_eligible(huge, "browser_snapshot")


def test_snapshot_at_upper_bound_stays_eligible():
    payload = _snapshot("- heading \"Notas\" [level=1]", "- textbox \"Pesquisar\" [ref=e3]")
    padded = payload + "\n" + "y" * (500_000 - len(payload) - 1)
    assert len(padded) == 500_000
    assert web_result_eligible(padded, "browser_snapshot")
    assert not web_result_eligible(padded + "y", "browser_snapshot")


def test_minimum_boundary_behaviour():
    from pie.gateway.web_results import _MIN_STRUCTURAL_CHARS

    base = _snapshot("- heading \"Notas locais\" [level=1]", "- textbox \"Pesquisar\" [ref=e3]", "- link \"Ajuda\" [ref=e2]")
    assert len(base) >= _MIN_STRUCTURAL_CHARS
    exact = base[:_MIN_STRUCTURAL_CHARS].rstrip() + "x" * (_MIN_STRUCTURAL_CHARS - len(base[:_MIN_STRUCTURAL_CHARS].rstrip()))
    assert len(exact) == _MIN_STRUCTURAL_CHARS
    assert web_result_eligible(exact, "browser_snapshot")
    assert not web_result_eligible(exact[:-1], "browser_snapshot")


def test_non_snapshot_text_above_minimum_still_rejected():
    assert not web_result_eligible(
        "### Snapshot\n" + "some promise result without refs or roles " * 4,
        "browser_snapshot",
    )


def test_preview_budget_keeps_multiple_interactive_refs():
    snapshot = (
        _snapshot(
            "- heading \"Summary\" [level=1]",
            "- status \"Ready\"",
            "- button \"Open details\" [ref=e5]",
            "- button \"Show summary\" [ref=e6]",
        )
        + "\n"
        + "- listitem \"deterministic row\"\n" * 80
    )
    result = web_snapshot_preview(snapshot, 1200)
    assert result is not None
    assert 'button "Open details" [ref=e5]' in result["preview"]
    assert 'button "Show summary" [ref=e6]' in result["preview"]
