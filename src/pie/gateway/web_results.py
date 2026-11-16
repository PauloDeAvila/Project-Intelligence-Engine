"""Conservative Playwright MCP response reduction; page content is UNTRUSTED.

Only allowlisted browser tools returning a recognizable accessibility snapshot
are eligible. Every original ref stays byte-identical when selected, and any
omitted refs must be explicitly recoverable. Navigation/actions are NEVER
replayed; this module processes returned text only.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit
from pie.retrieval.output_pipeline import _redact

# Known core tools from Microsoft Playwright MCP. This is a return-value policy,
# not permission to call any of these tools.
SNAPSHOT_RESULT_TOOLS = frozenset({
    "browser_snapshot", "browser_navigate", "browser_navigate_back",
    "browser_click", "browser_hover", "browser_type", "browser_fill_form",
    "browser_press_key", "browser_select_option", "browser_wait_for",
    "browser_find", "browser_drag", "browser_drop",
})

# Allowlist refuses screenshots, raw network requests, JS execution, uploads,
# dialogs and arbitrary custom tools: those may contain binary, credentials,
# side effects or protocol-specific structure.
_UNSAFE = re.compile(
    r"(?im)(?:^###\s*(?:error|failed)\b|"
    r"\b(?:traceback|timeout(?:error)?|permission denied|"
    r"navigation failed|action failed|error:|failed to)\b)"
)
_SECRET = re.compile(
    r"(?i)(?:authorization\s*:\s*bearer|set-cookie\s*:|"
    r"cookie\s*:|password\s*[=:]|passcode\s*[=:]|"
    r"\b(?:api[_-]?key|access[_-]?token|session[_-]?id)\s*[=:]|"
    r"[?&](?:token|access_token|auth|session|key|apikey|api_key)=|"
    r"\btoken\s*[=:]|"
    r"\b(?:password|passcode|one.time.code|verification.code|cvv|credit.card.number|card.number)\b)"
)
_REF = re.compile(r"(?<!\w)(?:\[\s*ref\s*=\s*(?:[a-z]\d+|f\d+e\d+)\s*\]|\bref\s*=\s*(?:[a-z]\d+|f\d+e\d+))", re.I)
_HEAD = re.compile(r"(?i)^\s*[-*]?\s*(?:heading|title|alert|status|dialog|main|navigation|form|button|link|textbox|searchbox|combobox|checkbox|radio|tab|menuitem|option|listitem|row|cell)\b")
_MARKER = re.compile(r"(?im)^###\s*(?:snapshot|page snapshot|page url|page title|aria snapshot)\b")
_LONG_LINE = 560

WEB_CONTEXT_NAME = "pie_web_context"
WEB_CONTEXT_TOOL = {
    "name": WEB_CONTEXT_NAME,
    "description": "Read-only relevant evidence from the current page; never executes actions.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 512},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def web_result_eligible(text: str, tool: str) -> bool:
    """Fail closed on errors/secrets/unknown formats BEFORE persistent storage."""
    if tool not in SNAPSHOT_RESULT_TOOLS or not isinstance(text, str):
        return False
    if len(text) < 500 or len(text) > 500_000 or _UNSAFE.search(text) or _SECRET.search(text):
        return False
    if not _MARKER.search(text):
        # Reject arbitrary text as a web snapshot: don't lose tool semantics.
        return False
    return bool(_REF.search(text) or _HEAD.search(text))


def _origin(line: str) -> str:
    address=line.strip()
    if not address.lower().startswith(("http://","https://")):
        return "[URL_WITHHELD]"
    parsed=urlsplit(address)
    if parsed.scheme not in ("http","https") or not parsed.netloc or "@" in parsed.netloc:
        return "[URL_WITHHELD]"
    return parsed.scheme+"://"+parsed.netloc.lower()


def web_snapshot_preview(text: str, max_chars: int) -> dict | None:
    """Select actionable elements/headings, without fabricating snapshot completeness.

    The preview is intentionally not a substitute for the page's full tree.
    All raw refs remain available through the existing sanitized output store.
    """
    if type(max_chars) is not int or max_chars < 250:
        return None
    cleaned=_redact(text)
    lines=cleaned.splitlines()
    if not lines or len(lines)>20_000:
        return None
    page_title=None
    page_origin=None
    pool=[]
    saw_snapshot=False
    for idx,raw in enumerate(lines):
        row=raw.strip()
        if row.lower() in ("### snapshot","### page snapshot","### aria snapshot"):
            saw_snapshot=True
        if row.lower().startswith("### page url") and idx+1<len(lines):
            page_origin=_origin(lines[idx+1])
        if row.lower().startswith("### page title") and idx+1<len(lines):
            page_title=lines[idx+1].strip()[:120]
        if row.lower().startswith(("page url:","url:")):
            page_origin=_origin(row.split(":",1)[1].strip())
        if row.lower().startswith(("page title:","title:")):
            page_title=row.split(":",1)[1].strip()[:120]
        if not row.startswith(("-","*")) or len(row)>_LONG_LINE:
            continue
        has_ref=bool(_REF.search(row))
        role=bool(_HEAD.search(row))
        if not has_ref and not role:
            continue
        # Snapshot positions stay in original order within each relevance tier.
        tier=0 if has_ref else 1
        if re.search(r"(?i)\b(?:heading|alert|status|dialog)\b",row):
            tier=-1
        pool.append((tier,idx,row))
    if not saw_snapshot and not pool:
        return None
    pool.sort(key=lambda t:(t[0],t[1]))
    selected=[]
    budget=max_chars-110
    used=0
    for _,_,row in pool:
        # Page text is untrusted even when it looks like an instruction.
        if re.search(r"(?i)\b(?:ignore (?:all )?(?:previous|prior) instructions|"
                     r"system prompt|developer message|reveal the password)\b",row):
            row="[UNTRUSTED_PAGE_INSTRUCTION]"
        size=len(row)+1
        if used+size>budget:
            continue
        used+=size
        selected.append(row)
    preview="\n".join(selected)
    if not preview:
        return None
    return {"preview":preview,"elements_in_preview":len(selected),
            "candidate_lines":len(pool),"omitted_lines":len(pool)-len(selected),
            "page_origin":page_origin,"page_title":page_title,
            "trust":"UNTRUSTED_PAGE_DATA","complete":False,
            "ref_policy":"original_refs_unmodified_if_included",
            "safe_to_execute":False}


def web_context_query(text: str, query: str, max_chars: int) -> dict:
    """Return only source lines relevant to an explicit read-only task query.

    This is deliberately opt-in and does not claim the excerpt is complete.
    Omitted source remains available to the gateway's normal recovery path when
    the snapshot was captured by the compacting pipeline.
    """
    if not isinstance(text, str) or not web_result_eligible(text, "browser_snapshot"):
        raise ValueError("A valid browser snapshot is required")
    if not isinstance(query, str) or not 1 <= len(query) <= 512:
        raise ValueError("query must contain 1..512 characters")
    if type(max_chars) is not int or not 250 <= max_chars <= 16000:
        raise ValueError("max_chars must be 250..16000")
    cleaned = _redact(text)
    terms = tuple(dict.fromkeys(re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]{1,63}", query.lower())))
    lines = cleaned.splitlines()
    ranked: list[tuple[int, int, str]] = []
    for index, raw in enumerate(lines):
        row = raw.strip()
        if not row or len(row) > _LONG_LINE:
            continue
        lowered = row.lower()
        hits = sum(lowered.count(term) for term in terms)
        if hits:
            if re.search(r"(?i)\b(?:ignore (?:all )?(?:previous|prior) instructions|system prompt|developer message|reveal the password)\b", row):
                row = "[UNTRUSTED_PAGE_INSTRUCTION]"
            ranked.append((hits, index, row))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[str] = []
    # Keep the response bounded while restoring original page order.
    budget = max_chars - 260
    used = 0
    for _, _, row in sorted(ranked, key=lambda item: item[1]):
        size = len(row) + 1
        if used + size > budget:
            continue
        used += size
        selected.append(row)
    preview = "\n".join(selected)
    if not preview:
        raise ValueError("query matched no safe snapshot lines")
    return {
        "schema": "pie-web-context-v1",
        "preview": preview,
        "omitted_lines": max(0, len(lines) - len(selected)),
        "complete": False,
        "trust": "UNTRUSTED_PAGE_DATA",
        "safe_to_execute": False,
    }
