# Blender A/B pilot — blocked before dispatch

Status: `BLOCKED`; certification remains `NOT_CERTIFIED`.

The first authorized pilot call was started for the optimized arm. The Codex process completed a turn and reported provider usage, but it emitted zero `mcp_tool_call` events. The controller therefore rejected the run as route evidence failure and stopped before baseline. No retry was performed.

| Item | Evidence |
|---|---|
| Model | `gpt-5.6-luna` |
| Commit | `00784c906768527993f136190808ec9c1639af94` |
| Run | `optimized-9823d9e4cfbe6d7413f965f0` |
| Pair | `pair-ad731c36abf11522eaab857b` |
| MCP calls | `0` observed |
| Provider input | `230071` |
| Cached input | `178176` |
| Uncached input | `51895` |
| Output | `1528` |
| Reasoning output | `1103` |
| Total | `231599` |
| Retry | No |

The sanitized Codex stderr identifies the immediate failure:

`codex_mcp.rmcp_client: MCP server startup failed server_name=pie-blender-optimized error=os error 3`

The same startup signal appeared for `pie-web-optimized` during MCP initialization. This is a launch/configuration failure, not evidence about PIE compaction or token savings. Because no tool call crossed the gateway, this run cannot be used in an A/B comparison.

The profile forensic check identifies the concrete cause: `command` was set to `C:\Users\phsra\AppData\Local\Temp\pie-phase3-blender-pilot-00784c9\.venv\Scripts\python.exe`, but the isolated worktree does not contain a `.venv` directory. The existing preflight did not validate MCP server command paths. A guard was added so a future run fails before starting the model when a configured MCP command is unavailable.

Forensic files were preserved under the temporary live store referenced in [76-blender-pilot-blocked.json](76-blender-pilot-blocked.json). The disposable Blender process was terminated after the failed pilot; the user’s open Blender instance was not modified.

Next technical action before any additional quota: fix the Windows MCP process-start path in the isolated Codex home/profile, validate `codex mcp list`/server startup without a model, then run one controlled optimized dispatch probe. The previous two-call budget was not retried after this failure.
