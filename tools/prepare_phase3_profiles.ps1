<#
Generate temporary, credential-free Codex overlays for one exact worktree.
This script writes only the requested output directory; it never copies auth.json
or edits the user's persistent config.toml.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$PythonExe = "python",
    [string]$BlenderUpstream = "uvx",
    [string]$NpxExe = "npx.cmd",
    [string]$PlaywrightVersion = "@playwright/mcp@0.0.85",
    [string]$DiagnosticsDirectory = "",
    [string[]]$OptimizedExposeTool = @()
)
$ErrorActionPreference = "Stop"
$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
if ($resolvedWorkspace.Contains("'")) { throw "Workspace path cannot contain a single quote for literal TOML" }
foreach ($value in @($PythonExe,$BlenderUpstream,$NpxExe,$PlaywrightVersion)) {
    if ($value.Contains("'")) { throw "Executable/version cannot contain a single quote" }
}
foreach ($value in $OptimizedExposeTool) {
    if (-not $value -or $value.Contains("'")) { throw "Optimized exposed tool cannot be empty or contain a single quote" }
}
if ($DiagnosticsDirectory -and $DiagnosticsDirectory.Contains("'")) { throw "Diagnostics path cannot contain a single quote" }
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$py = $PythonExe
$root = $resolvedWorkspace
$diagnosticsBlender = if ($DiagnosticsDirectory) { Join-Path (Resolve-Path -LiteralPath $DiagnosticsDirectory) "blender-mcp.jsonl" } else { "" }
$diagnosticsWeb = if ($DiagnosticsDirectory) { Join-Path (Resolve-Path -LiteralPath $DiagnosticsDirectory) "web-mcp.jsonl" } else { "" }
if ($diagnosticsBlender -and $diagnosticsBlender.Contains("'")) { throw "Diagnostics path cannot contain a single quote" }
if ($diagnosticsWeb -and $diagnosticsWeb.Contains("'")) { throw "Diagnostics path cannot contain a single quote" }
function TomlArray([string[]]$values) {
    return "[" + (($values | ForEach-Object { "'" + $_ + "'" }) -join ", ") + "]"
}
$optimizedBlenderArgs = @("-m", "pie.gateway.domain", "serve", "--domain", "blender", "--workspace", $root, "--max-chars", "2400")
foreach ($tool in $OptimizedExposeTool) { $optimizedBlenderArgs += @("--expose-tool", $tool) }
$optimizedBlenderArgs += @("--", $BlenderUpstream, "mcp-for-blender")
$optimizedWebArgs = @("-m", "pie.gateway.domain", "serve", "--domain", "web", "--workspace", $root, "--max-chars", "2400")
foreach ($tool in $OptimizedExposeTool) { $optimizedWebArgs += @("--expose-tool", $tool) }
$optimizedWebArgs += @("--", $NpxExe, "--yes", $PlaywrightVersion, "--headless", "--browser", "chrome")
$baseline = @(
    "# Generated overlay; no credentials.",
    "model = 'gpt-5.6-luna'",
    "model_reasoning_effort = 'medium'",
    "approval_policy = 'never'",
    "sandbox_mode = 'read-only'",
    "enabled_tools = ['get_scene_info', 'execute_blender_code', 'browser_navigate', 'browser_snapshot']",
    "default_tools_approval_mode = 'prompt'",
    "",
    "[mcp_servers.blender]",
    ("command = '{0}'" -f $BlenderUpstream),
    $(if ($diagnosticsBlender) { "env = { PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsBlender' }" }),
    ("args = {0}" -f (TomlArray @("mcp-for-blender"))),
    "",
    "[mcp_servers.playwright-baseline]",
    ("command = '{0}'" -f $NpxExe),
    $(if ($diagnosticsWeb) { "env = { PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsWeb' }" }),
    ("args = {0}" -f (TomlArray @("--yes", $PlaywrightVersion, "--headless", "--browser", "chrome"))),
    "",
    "[mcp_servers.blender.tools.get_scene_info]",
    "approval_mode = 'approve'",
    "[mcp_servers.blender.tools.execute_blender_code]",
    "approval_mode = 'approve'",
    "[mcp_servers.playwright-baseline.tools.browser_navigate]",
    "approval_mode = 'approve'",
    "[mcp_servers.playwright-baseline.tools.browser_snapshot]",
    "approval_mode = 'approve'"
) -join "`r`n"
$optimized = @(
    "# Generated overlay; no credentials.",
    "model = 'gpt-5.6-luna'",
    "model_reasoning_effort = 'medium'",
    "approval_policy = 'never'",
    "sandbox_mode = 'read-only'",
    "enabled_tools = ['get_scene_info', 'execute_blender_code', 'browser_navigate', 'browser_snapshot']",
    "default_tools_approval_mode = 'prompt'",
    "",
    "[mcp_servers.pie-blender-optimized]",
    ("command = '{0}'" -f $py),
    $(if ($diagnosticsBlender) { "env = { PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsBlender' }" }),
    ("args = {0}" -f (TomlArray $optimizedBlenderArgs)),
    "",
    "[mcp_servers.pie-web-optimized]",
    ("command = '{0}'" -f $py),
    $(if ($diagnosticsWeb) { "env = { PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsWeb' }" }),
    ("args = {0}" -f (TomlArray $optimizedWebArgs)),
    "",
    "[mcp_servers.pie-blender-optimized.tools.get_scene_info]",
    "approval_mode = 'approve'",
    "[mcp_servers.pie-blender-optimized.tools.execute_blender_code]",
    "approval_mode = 'approve'",
    "[mcp_servers.pie-web-optimized.tools.browser_navigate]",
    "approval_mode = 'approve'",
    "[mcp_servers.pie-web-optimized.tools.browser_snapshot]",
    "approval_mode = 'approve'"
) -join "`r`n"
$baselinePath = Join-Path $resolvedOutput "pie-phase3-baseline.config.toml"
$optimizedPath = Join-Path $resolvedOutput "pie-phase3-optimized.config.toml"
[IO.File]::WriteAllText($baselinePath, $baseline + "`r`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($optimizedPath, $optimized + "`r`n", [Text.UTF8Encoding]::new($false))
Get-FileHash -Algorithm SHA256 -LiteralPath $baselinePath,$optimizedPath | Select-Object Path,Hash
