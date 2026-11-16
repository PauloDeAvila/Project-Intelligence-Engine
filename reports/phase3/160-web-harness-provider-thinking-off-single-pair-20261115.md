# Provider control probe — single pair

An isolated second gateway instance was used on port 8081 with an experimental
pass-through for `reasoning_effort`, `thinking`, and `enable_thinking`. The
original provider gateway on port 8080 was not modified or interrupted.

The single pair returned 2,698 baseline tokens and 138 optimized tokens, or
**94.885% savings**, with 2/2 arm oracles passing and zero reasoning tokens in
the optimized response. This is a probe, not a certification result.

The same setup was not stable over three repetitions: reasoning tokens
reappeared and the aggregate fell below the normal 94.119% result. See report
161. The experimental gateway was shut down and its source change reverted.

