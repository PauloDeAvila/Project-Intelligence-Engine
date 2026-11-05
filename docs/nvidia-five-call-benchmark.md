# PIE NVIDIA / 9Router low-volume benchmark

This benchmark is manually triggered only, not an automated recurring task.

## Safety budget

- Four inference requests planned: two preselected code tasks, each once with
  baseline and once with PIE RTK-style evidence.
- A hard cap of **five outbound inference attempts** is enforced before any
  API execution; the planned job count is validated before indexing and again
  before each actual HTTP attempt.
- A minimum **10-second cooldown** separates outbound requests.
- No retries on HTTP 429, 503, timeout, network errors or invalid output.
- HTTP redirects are explicitly disabled to avoid hidden extra requests.
- The zero-call dry run checks indexed test fixtures and evidence before live
  inference, producing a local context audit.
- Results use provider-returned `usage` when present; missing provider token
  counts remain unknown. Correctness is scored using the deterministic fixture.
- Early stop on first failure; no extra 'connectivity probe' request is made.

## GitHub Actions setup

Use the workflow named **PIE - NVIDIA API five-call benchmark**.
It requires an exact NVIDIA model ID from your 9Router instance and these
repository Actions secrets:

- `PIE_API_BASE_URL`: externally reachable HTTPS base URL for 9Router.
  The caller accepts bases with or without `/v1`. GitHub-hosted runners
  cannot reach your local `127.0.0.1:20129` process directly.
- `PIE_API_KEY`: limited-scope inference token. Do not commit or print it.

The workflow has NO fallback to an old Cloudflare tunnel and never starts
automatically on a push. Its single manual run is limited to one repetition
of two questions across two conditions. Disable or cancel the run when the
model has exhausted its external rate limits. The cap is per workflow job/run,
not a global rate limiter across concurrently configured third-party jobs.

No live NVIDIA calls occur during this PR's CI. Enabling Actions inference
requires configuring credentials and manually triggering the workflow.

## CLI dry-run example (no API traffic)

```powershell
python tools/cloud_pie_benchmark.py --dry-run --out benchmark-results \
  --cases MAX_RETRIES,release --modes baseline,pie_rtk \
  --repeats 1 --max-calls 5 --cooldown-seconds 10
```

**Limit:** This is a four-request *smoke test*, not a statistically reliable
benchmark of 90% token savings. A larger task-level comparison requires
explicit separate authorization and a provider-safe budget.
