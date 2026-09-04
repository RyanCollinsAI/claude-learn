<#
.SYNOPSIS
  Remove exactly what install.ps1 put down: the skill folder and the /learn command.

.DESCRIPTION
  Deletes ~/.claude/skills/learn (the skill, its tools, config.json, and any courses you
  dropped in) and ~/.claude/commands/learn.md. Your vault - session notes, the learner
  profile, review cards - is never touched, because none of it lives under ~/.claude.

.PARAMETER Force
  Skip the confirmation prompt.

.EXAMPLE
  .\uninstall.ps1
#>
[CmdletBinding()]
param([switch]$Force)

$claude = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }
$dest = Join-Path $claude 'skills\learn'
$cmd  = Join-Path $claude 'commands\learn.md'

Write-Host "claude-learn uninstaller"
Write-Host "  skill folder   $dest"
Write-Host "  command        $cmd"
Write-Host ""

if (-not (Test-Path $dest) -and -not (Test-Path $cmd)) {
  Write-Host "Nothing installed at either path. Nothing to do."
  exit 0
}

if (-not $Force) {
  $reply = Read-Host "Remove both? This deletes config.json and any courses you dropped in. [y/N]"
  if ($reply -notmatch '^[Yy]') { Write-Host "Cancelled."; exit 1 }
}

if (Test-Path $dest) { Remove-Item -Recurse -Force $dest; Write-Host "Removed $dest" }
else { Write-Host "Not present: $dest" }

if (Test-Path $cmd) { Remove-Item -Force $cmd; Write-Host "Removed $cmd" }
else { Write-Host "Not present: $cmd" }

Write-Host ""
Write-Host "Done. Your vault - session notes, the learner profile, review cards - was never touched."
