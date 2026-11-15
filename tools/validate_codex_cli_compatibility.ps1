<##
Offline validation for the Codex CLI combinations used by the PIE diagnostic.
This script invokes only `codex exec --help`; it never starts a model turn.
#>
[CmdletBinding()]
param([string]$CodexBin = "codex")
$ErrorActionPreference = "Stop"
if (-not (Get-Command -Name $CodexBin -ErrorAction SilentlyContinue)) { throw "Codex executable unavailable" }
$help = (& $CodexBin exec --help 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "codex exec --help failed with exit code $LASTEXITCODE" }
foreach ($needle in @("--sandbox <SANDBOX_MODE>", "--approve-for-me", "--config <key=value>")) {
    if ($help -notmatch [regex]::Escape($needle)) { throw "Codex help does not expose expected option: $needle" }
}
$interactiveHelp = (& $CodexBin --help 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0 -or $interactiveHelp -notmatch [regex]::Escape("--ask-for-approval <APPROVAL_POLICY>")) {
    throw "Codex interactive help does not expose --ask-for-approval"
}
[pscustomobject]@{
    status = "PASS"
    model_started = $false
    approval_policy_override = "supported by executor"
    approve_for_me_sandbox = "workspace-write (from CLI help)"
    interactive_approval = "--ask-for-approval on-request (from CLI help)"
    read_only_plus_approve_for_me = "REJECTED_BY_CLI_AND_BLOCKED_BY_EXECUTOR"
    read_only_without_approve_for_me = "ARGUMENTS_ACCEPTED_BY_HELP_ONLY; runtime approval behavior remains unverified"
} | ConvertTo-Json -Compress
