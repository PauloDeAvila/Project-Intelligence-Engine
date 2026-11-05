# PIE External Memory Stage 2 — indexed retrieval (experimental)

Stage 2 adds a **project-local memory search** for task objectives and
explicitly recorded events. It uses SQLite FTS5 with a bounded, quoted
multi-term query, and a parameterized lexical fallback when FTS5 is unavailable.
This is lexical retrieval, **not embedding-based semantic search or natural
language question answering**. Dates are metadata, not yet interpreted from
phrases such as "what did I do yesterday?".

## Usage

```powershell
pie task-search "login authentication" --root C:\\project --limit 10
```

MCP: `pie_task_search` accepts `query`, `limit` (1..20) and
`max_chars` (1000..64000). Search results include originating task ID,
event ID when relevant, status, recorded timestamps, reference, and
`verification=agent_supplied_unverified`. The full event text is returned
or the item is omitted; the system does not slice a fact mid-negation.

First retrieval creates the local FTS index transactionally, backfills existing Stage 1 task
records and installs triggers for subsequent task/event inserts. Parallel clients\nserialize this first-time initialization to avoid duplicate backfills. No third-party
model, account, remote transmission or new database is required.

## Security, freshness and accuracy

- Search matches **recorded claims**, not independent proof of an assertion.
- References are pointers supplied by the agent and may be stale or wrong.
  Verify them against current source before relying on a remembered claim.
- Queries use quoted tokens (no arbitrary FTS operators/SQL execution).
- Each project retains its own SQLite database.
- A max_chars budget can omit entire matches; `omitted` is a **minimum known\n  count** when the result limit was reached. `omission_count_complete=false`\n  explicitly marks that the full omitted count was not enumerated.
- Search is case/term-oriented, not a general memory understanding model.
- No statement of token reduction or overall model accuracy is implied.

## Verification

Run the focused test file `test_pie_task_search.py`, complete unittest
suite and all project CI matrix tiers on Linux and Windows. Benchmark
retrieval latency and recall on realistic tasks before production adoption.
