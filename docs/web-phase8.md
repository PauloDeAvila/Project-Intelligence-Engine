# Web Intelligence Phase 8 — Fast Browser Path

Phase 8 optimizes local preparation latency after correctness and safety are established.

## Components

- `PageCache`: bounded LRU cache keyed by session, page, generation, region and task fingerprint;
- `SnapshotDeltaEngine`: compares bounded candidate fingerprints without retaining raw page content;
- `ElementReuseManager`: reuses only unchanged current references from the new snapshot;
- `RegionPrefetcher`: plans local region work without network or model calls;
- `BrowserFastPath`: cache-assisted lookup with `validation_required=True` on every result.

The cache is an optimization, not proof of validity. Page/generation changes invalidate the relevant cache scope, and Action Engine preflight remains mandatory before execution.

The benchmark measures local lookup only. It reports latency, cache hit rate and zero model/network calls; it must not be interpreted as end-to-end browser completion time.
