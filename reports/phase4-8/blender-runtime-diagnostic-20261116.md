# Blender runtime diagnostic — 2026-11-16

## Result

`BLOCKED`: Blender 5.3 is installed, but no `blender.exe` process or listener on TCP port `9877` was found.

## Evidence

- `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe` exists.
- `C:\Program Files\Blender Foundation\Blender 5.3\blender-launcher.exe` exists.
- `Get-Process -Name blender,blender-launcher` returned no process.
- `Get-NetTCPConnection -State Listen -LocalPort 9877` returned no listener.
- The previously recorded gateway failure was `Addon handshake failed: Connection to Blender lost: [WinError 10053]`.

## Interpretation

This is a runtime availability problem, not evidence of a PIE compaction or MCP protocol regression. The bridge can start, but the `mcp-for-blender` upstream cannot complete its connection to a running Blender addon.

## Safe next step

Start Blender 5.3 with the PIE/mcp-for-blender addon enabled, confirm that port `9877` is listening, and rerun the read-only handshake and scene probe. No installation, scene mutation, external-page mutation, or configuration change was performed by this diagnostic.

## Limitations

The addon version and Blender-side log were not inspected because Blender was not running. The local PIE index was current for this workspace; the configured app-level PIE connector still points to a different root and was not used as evidence.
