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
    [string[]]$BaselineExposeTool = @(),
    [string[]]$OptimizedExposeTool = @(),
    [string[]]$DisableServer = @(),
    [string]$BaselineDisableServer = "",
    [string]$OptimizedDisableServer = "",
    [ValidateSet("all", "blender", "web")][string]$Domain = "all",
    [int]$MaxChars = 2400,
    [string]$PieSource = "",
    [string]$PieCommit = "",
    [int]$BlenderPort = 0
)
$ErrorActionPreference = "Stop"
$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
$resolvedOutput = [IO.Path]::GetFullPath($OutputDirectory)
if ($MaxChars -lt 800 -or $MaxChars -gt 64000) { throw "MaxChars must be 800..64000" }
if ($BlenderPort -ne 0 -and ($BlenderPort -lt 1024 -or $BlenderPort -gt 65535)) { throw "BlenderPort must be 1024..65535 or zero" }
if ($resolvedWorkspace.Contains("'")) { throw "Workspace path cannot contain a single quote for literal TOML" }
foreach ($value in @($PythonExe,$BlenderUpstream,$NpxExe,$PlaywrightVersion)) {
    if ($value.Contains("'")) { throw "Executable/version cannot contain a single quote" }
}
foreach ($value in $OptimizedExposeTool) {
    if (-not $value -or $value.Contains("'")) { throw "Optimized exposed tool cannot be empty or contain a single quote" }
}
foreach ($value in $BaselineExposeTool) {
    if (-not $value -or $value.Contains("'")) { throw "Baseline exposed tool cannot be empty or contain a single quote" }
}
if ($DiagnosticsDirectory -and $DiagnosticsDirectory.Contains("'")) { throw "Diagnostics path cannot contain a single quote" }
$resolvedPieSource = if ($PieSource) { (Resolve-Path -LiteralPath $PieSource).Path } else { Join-Path $resolvedWorkspace "src" }
if (-not (Test-Path -LiteralPath $resolvedPieSource -PathType Container)) { throw "PIE source directory missing" }
if ($resolvedPieSource.Contains("'")) { throw "PIE source path cannot contain a single quote" }
if (-not $PieCommit) {
    $PieCommit = (& git -C $resolvedWorkspace rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $PieCommit -notmatch '^[0-9a-f]{40}$') { throw "Unable to resolve PIE source commit" }
}
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
$optimizedBlenderArgs = @("-m", "pie.gateway.domain", "serve", "--domain", "blender", "--workspace", $root, "--max-chars", "$MaxChars")
foreach ($tool in $OptimizedExposeTool) { $optimizedBlenderArgs += @("--expose-tool", $tool) }
$blenderUpstreamArgs = @("mcp-for-blender")
if ($BlenderPort -ne 0) { $blenderUpstreamArgs += @("--port", "$BlenderPort") }
$optimizedBlenderArgs += @("--", $BlenderUpstream) + $blenderUpstreamArgs
$optimizedWebArgs = @("-m", "pie.gateway.domain", "serve", "--domain", "web", "--workspace", $root, "--max-chars", "$MaxChars")
foreach ($tool in $OptimizedExposeTool) { $optimizedWebArgs += @("--expose-tool", $tool) }
$optimizedWebArgs += @("--", $NpxExe, "--yes", $PlaywrightVersion, "--headless", "--isolated", "--browser", "chrome")
$webBaseline = @(
    "[mcp_servers.playwright-baseline]",
    "enabled = true",
    "enabled_tools = ['browser_navigate', 'browser_snapshot']",
    ("command = '{0}'" -f $NpxExe),
    $(if ($diagnosticsWeb) { "env = { PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsWeb' }" }),
    ("args = {0}" -f (TomlArray @("--yes", $PlaywrightVersion, "--headless", "--isolated", "--browser", "chrome"))),
    "",
    "[mcp_servers.playwright-baseline.tools.browser_navigate]",
    "approval_mode = 'approve'",
    "[mcp_servers.playwright-baseline.tools.browser_snapshot]",
    "approval_mode = 'approve'"
)
$blenderOptimizedEnv = @(
    "PYTHONPATH = '$resolvedPieSource'",
    "PIE_SOURCE_ROOT = '$resolvedPieSource'",
    "PIE_SOURCE_COMMIT = '$PieCommit'"
)
if ($diagnosticsBlender) { $blenderOptimizedEnv += "PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsBlender'" }
$webOptimizedEnv = @(
    "PYTHONPATH = '$resolvedPieSource'",
    "PIE_SOURCE_ROOT = '$resolvedPieSource'",
    "PIE_SOURCE_COMMIT = '$PieCommit'"
)
if ($diagnosticsWeb) { $webOptimizedEnv += "PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsWeb'" }
function EnvLine([string[]]$values) {
    if ($values.Count -eq 0) { return $null }
    return "env = { " + ($values -join ", ") + " }"
}
function DisableServerLines([string[]]$names) {
    $lines = @()
    foreach ($name in ($names | Sort-Object -Unique)) {
        if (-not $name -or $name -notmatch '^[A-Za-z0-9_-]+$') { throw "Invalid server name: $name" }
        $lines += @("[mcp_servers.$name]", "enabled = false", "command = 'disabled'", "")
    }
    return $lines
}
function SplitServerList([string]$value) {
    if (-not $value) { return @() }
    return @($value -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
$baselineEnabledTools = if ($BaselineExposeTool.Count -gt 0) {
    "enabled_tools = " + (TomlArray $BaselineExposeTool)
} elseif ($Domain -eq "blender") {
    "enabled_tools = ['get_scene_info', 'execute_blender_code']"
} elseif ($Domain -eq "web") {
    "enabled_tools = ['browser_navigate', 'browser_snapshot']"
} else {
    "enabled_tools = ['get_scene_info', 'execute_blender_code', 'browser_navigate', 'browser_snapshot']"
}
$optimizedToolNames = if ($OptimizedExposeTool.Count -gt 0) {
    @($OptimizedExposeTool)
} else {
    $defaults = @()
    if ($Domain -in @("all", "blender")) { $defaults += @("get_scene_info", "execute_blender_code") }
    if ($Domain -in @("all", "web")) { $defaults += @("browser_navigate", "browser_snapshot") }
    $defaults
}
$optimizedEnabledTools = "enabled_tools = " + (TomlArray $optimizedToolNames)
$optimizedBlenderToolNames = @()
if ($OptimizedExposeTool.Count -gt 0 -and $Domain -in @("all", "blender")) {
    $optimizedBlenderToolNames += $OptimizedExposeTool
} else {
    $optimizedBlenderToolNames += @("get_scene_info", "execute_blender_code")
}
$baselineBlenderToolNames = @()
if ($BaselineExposeTool.Count -gt 0 -and $Domain -in @("all", "blender")) {
    $baselineBlenderToolNames += $BaselineExposeTool
} else {
    $baselineBlenderToolNames += @("get_scene_info", "execute_blender_code")
}
$blenderBaseline = @(
    "[mcp_servers.blender]",
    "enabled = true",
    ("enabled_tools = {0}" -f (TomlArray $baselineBlenderToolNames)),
    ("command = '{0}'" -f $BlenderUpstream),
    $(if ($diagnosticsBlender) { "env = { PIE_MCP_DIAGNOSTICS_PATH = '$diagnosticsBlender' }" }),
    ("args = {0}" -f (TomlArray $blenderUpstreamArgs)),
    "",
    "[mcp_servers.blender.tools.$($baselineBlenderToolNames[0])]",
    "approval_mode = 'approve'"
)
foreach ($tool in $baselineBlenderToolNames | Select-Object -Skip 1) {
    $blenderBaseline += @(
        "[mcp_servers.blender.tools.$tool]",
        "approval_mode = 'approve'"
    )
}
$blenderOptimized = @(
    "[mcp_servers.pie-blender-optimized]",
    "enabled = true",
    ("enabled_tools = {0}" -f (TomlArray $optimizedBlenderToolNames)),
    ("command = '{0}'" -f $py),
    (EnvLine $blenderOptimizedEnv),
    ("args = {0}" -f (TomlArray $optimizedBlenderArgs)),
    "",
    "[mcp_servers.pie-blender-optimized.tools.$($optimizedBlenderToolNames[0])]",
    "approval_mode = 'approve'"
)
foreach ($tool in $optimizedBlenderToolNames | Select-Object -Skip 1) {
    $blenderOptimized += @(
        "[mcp_servers.pie-blender-optimized.tools.$tool]",
        "approval_mode = 'approve'"
    )
}
$webOptimized = @(
    "[mcp_servers.pie-web-optimized]",
    "enabled = true",
    ("enabled_tools = {0}" -f (TomlArray $(if ($OptimizedExposeTool.Count -gt 0 -and $Domain -in @("all", "web")) { $OptimizedExposeTool } else { @("browser_navigate", "browser_snapshot") }))),
    ("command = '{0}'" -f $py),
    (EnvLine $webOptimizedEnv),
    ("args = {0}" -f (TomlArray $optimizedWebArgs)),
    "",
    "[mcp_servers.pie-web-optimized.tools.browser_navigate]",
    "approval_mode = 'approve'",
    "[mcp_servers.pie-web-optimized.tools.browser_snapshot]",
    "approval_mode = 'approve'"
)
$webOptimizedToolNames = if ($OptimizedExposeTool.Count -gt 0 -and $Domain -in @("all", "web")) { @($OptimizedExposeTool) } else { @("browser_navigate", "browser_snapshot") }
foreach ($tool in $webOptimizedToolNames | Where-Object { $_ -notin @("browser_navigate", "browser_snapshot") }) {
    $webOptimized += @(
        "[mcp_servers.pie-web-optimized.tools.$tool]",
        "approval_mode = 'approve'"
    )
}
$baseline = @(
    "# Generated overlay; no credentials.",
    "model = 'gpt-5.6-luna'",
    "model_reasoning_effort = 'medium'",
    "approval_policy = 'never'",
    "sandbox_mode = 'read-only'",
    "default_tools_approval_mode = 'prompt'",
    ""
) -join "`r`n"
$optimized = @(
    "# Generated overlay; no credentials.",
    "model = 'gpt-5.6-luna'",
    "model_reasoning_effort = 'medium'",
    "approval_policy = 'never'",
    "sandbox_mode = 'read-only'",
    "default_tools_approval_mode = 'prompt'",
    ""
) -join "`r`n"
if ($Domain -in @("all", "blender")) {
    $baseline = ($baseline -join "`r`n") + "`r`n" + (($blenderBaseline -join "`r`n"))
    $optimized = ($optimized -join "`r`n") + "`r`n" + (($blenderOptimized -join "`r`n"))
}
if ($Domain -in @("all", "web")) {
    $baseline = ($baseline -join "`r`n") + "`r`n" + (($webBaseline -join "`r`n"))
    $optimized = ($optimized -join "`r`n") + "`r`n" + (($webOptimized -join "`r`n"))
}
$baselineDisableLines = DisableServerLines @($DisableServer + (SplitServerList $BaselineDisableServer))
$optimizedDisableLines = DisableServerLines @($DisableServer + (SplitServerList $OptimizedDisableServer))
$baseline = ($baseline -join "`r`n") + "`r`n" + (($baselineDisableLines -join "`r`n"))
$optimized = ($optimized -join "`r`n") + "`r`n" + (($optimizedDisableLines -join "`r`n"))
$baselinePath = Join-Path $resolvedOutput "pie-phase3-baseline.config.toml"
$optimizedPath = Join-Path $resolvedOutput "pie-phase3-optimized.config.toml"
[IO.File]::WriteAllText($baselinePath, $baseline + "`r`n", [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($optimizedPath, $optimized + "`r`n", [Text.UTF8Encoding]::new($false))
Get-FileHash -Algorithm SHA256 -LiteralPath $baselinePath,$optimizedPath | Select-Object Path,Hash
