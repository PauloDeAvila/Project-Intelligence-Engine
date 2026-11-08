# Independent review — OpenCode Remote Orchestrator, Stage 1

## Decision

**REQUEST CHANGES before operational approval.** The implementation is suitable for
code review as a local, single-agent foundation, but the real OpenCode server and
NVIDIA account were not available to exercise the external boundary.

## Scope and evidence

The change adds `pie.orchestrator`, isolated from the PIE index database. Its direct
consumers are the `pie-orchestrator` entry point and the loopback HTTP handler. The
queue persists tasks, idempotency keys and events in its own SQLite file; `RUNNING`
tasks become `BLOCKED` after restart. The gateway refuses non-loopback binding and
requires a bearer token for task, status, cancellation and SSE endpoints.

`Orchestrator.submit` accepts only an allowlisted project ID, task type and model;
it never accepts a command, URL or filesystem path. `Orchestrator.run` validates PIE
freshness before the OpenCode adapter creates a new session. Missing provider metrics
remain `null`, rather than being represented as zero.

## Test matrix

| Layer | Evidence |
| --- | --- |
| Unit / persistence / HTTP | `python -m unittest discover -s tests -p test_orchestrator.py -v`: 4 passed |
| Full regression | `python -m unittest discover -s tests -v`: 99 passed |
| Project matrix | `python tools/verify_project.py`: 99 passed |
| Build | `python -m compileall -q src tools tests`; `python tools/check_install.py`: passed |
| External integration | Not run: no isolated OpenCode server, NVIDIA credential, GitLab webhook or authenticated tunnel available |

## Required follow-up

1. Run an isolated `opencode serve --pure` on loopback with an authenticated local
   configuration and verify the OpenCode HTTP request/response schema.
2. Add the authenticated GitLab webhook, replay protection and tunnel only after the
   local path is proven.
3. Add Pyright to CI and resolve its findings before declaring the overall project
   ready. Multi-agent execution remains deliberately deferred.
