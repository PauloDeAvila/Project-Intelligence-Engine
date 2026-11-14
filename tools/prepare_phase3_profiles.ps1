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
    [string]$PlaywrightVersion = "@playwright/mcp@0.0.85"
)
$ErrorActionPreference = "Stop"
$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
if ($resolvedWorkspace.Contains("'")) { throw "Workspace path cannot contain a single quote for literal TOML" }
foreach ($value in @($PythonExe,$BlenderUpstream,$NpxExe,$PlaywrightVersion)) {
    if ($value.Contains("'")) { throw "Executable/version cannot contain a single quote" }
}
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$py = $PythonExe
$root = $resolvedWorkspace
function TomlArray([string[]]$values) {
    return "[" + (($values | ForEach-Object { "'" + $_ + "'" }) -join ", ") + "]"
}
$baseline = @(
    "# Generated overlay; no credentials.",
    "[mcp_servers.pie-phase3-blender]",
    ("command = '{0}'" -f $BlenderUpstream),
    ("args = {0}" -f (TomlArray @("mcp-for-blender"))),
    "",
    "[mcp_servers.pie-phase3-web]",
    ("command = '{0}'" -f $NpxExe),
    ("args = {0}" -f (TomlArray @("--yes", $PlaywrightVersion, "--headless", "--browser", "chrome")))
) -join "`r`n"
$optimized = @(
    "# Generated overlay; no credentials.",
    "[mcp_servers.pie-phase3-blender]",
    ("command = '{0}'" -f $py),
    ("args = {0}" -f (TomlArray @("-m", "pie.gateway.domain", "serve", "--domain", "blender", "--workspace", $root, "--max-chars", "2400", "--", $BlenderUpstream, "mcp-for-blender"))),
    "",
    "[mcp_servers.pie-phase3-web]",
    ("command = '{0}'" -f $py),
    ("args = {0}" -f (TomlArray @("-m", "pie.gateway.domain", "serve", "--domain", "web", "--workspace", $root, "--max-chars", "2400", "--", $NpxExe, "--yes", $PlaywrightVersion, "--headless", "--browser", "chrome")))
) -join "`r`n"
$baselinePath = Join-Path $resolvedOutput "pie-phase3-baseline.config.toml"
$optimizedPath = Join-Path $resolvedOutput "pie-phase3-optimized.config.toml"
[IO.File]::WriteAllText($baselinePath, $baseline + "`r`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($optimizedPath, $optimized + "`r`n", [Text.UTF8Encoding]::new($false))
Get-FileHash -Algorithm SHA256 -LiteralPath $baselinePath,$optimizedPath | Select-Object Path,Hash
