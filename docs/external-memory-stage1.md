# PIE External Memory — Stage 1: persistent task checkpoints

Status: experimental, explicit task recording. This is **not** automatic capture
of agent conversations, a replacement for model context, or cross-project memory.

## Storage

Uses the existing project-local `.pie/index.sqlite3`, with new additive tables
`pie_tasks` and `pie_task_events`. Each event is appended transactionally;
the task's status and modification time update in the same SQLite transaction.
No source files are modified. Opening existing databases adds missing tables
without deleting the code index or glossary. The database is local and persists
after the CLI/MCP process exits.

Only explicit, user/agent-supplied checkpoints are recorded. Their contents are
**claims**, not independently verified facts. Record evidence references when
possible. Avoid secrets, access tokens and other sensitive contents.

## CLI quick start

```powershell
pie init --root C:\\project
pie task-start --root C:\\project --objective "Fix login regression"
pie task-record --root C:\\project --task-id <uuid> --kind decision --text "Preserve public API" --reference "src/auth.py:42"
pie task-record --root C:\\project --task-id <uuid> --kind checkpoint --text "Need CI rerun" --status blocked
pie task-resume --root C:\\project
pie task-resume --root C:\\project --task-id <uuid> --limit 20
```

MCP operations: `pie_task_start`, `pie_task_record`, `pie_task_resume`.
Latest-resume returns only an unfinished or blocked task. Explicit ID can
retrieve completed tasks, but they are immutable. Events are returned oldest
to newest within the last `limit` events (1..100) and omitted counts are explicit.
Inputs are bounded. Unknown tasks are rejected on writes. All SQL is parameterized.

## Phase boundary

This stage does not implement automatic observation, retrieval ranking, model
context trimming, or benchmarked token savings. Those belong to subsequent
stages, and no token reduction claim should be made from Stage 1 alone.

## Verification

Run `python -m unittest discover -s tests -p test_pie_task_memory.py -v`,
the full unittest suite, Python compilation, and the project's CI verification
matrix on Linux and Windows before marking this stage verified.
