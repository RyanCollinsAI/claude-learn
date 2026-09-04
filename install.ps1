<#
.SYNOPSIS
  Install the learn skill into ~/.claude/skills/learn.

.DESCRIPTION
  Copies the skill, writes a config.json if there is not one already, and reports which
  dependencies are present. Nothing is overwritten without being told to: an existing config.json
  is left alone.

.PARAMETER VaultRoot
  Absolute path to the Markdown vault the skill writes session notes into. Prompted for if
  omitted. Defaults to the current directory if you just press enter.

.PARAMETER VaultName
  The vault's name inside Obsidian, for obsidian:// URIs. Defaults to the last segment of
  VaultRoot.

.PARAMETER LearningDir
  Vault-relative folder for session notes that do not belong to a course. Default: Learning.

.PARAMETER CourseLearningDir
  Vault-relative pattern for a course's notes, with {course} standing in for the course folder
  name. Leave empty if you do not organise by course.

.PARAMETER NoPrompt
  Never ask. Use the flags and the defaults as given.

.EXAMPLE
  .\install.ps1 -VaultRoot C:\Users\me\Vault -LearningDir Learning
#>
[CmdletBinding()]
param(
  [string]$VaultRoot = "",
  [string]$VaultName = "",
  [string]$LearningDir = "",
  [string]$CourseLearningDir = "",
  [switch]$NoPrompt
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$claude = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }
$dest = Join-Path $claude 'skills\learn'

function Say($ok, $label, $detail) {
  $tag = if ($ok -eq $true) { 'OK  ' } elseif ($ok -eq $false) { 'MISS' } else { '--  ' }
  Write-Host ("  {0} {1,-16} {2}" -f $tag, $label, $detail)
}

Write-Host "claude-learn installer"
Write-Host "  repo   $repo"
Write-Host "  target $dest"
Write-Host ""

# ---------------------------------------------------------------- 1. copy the skill
New-Item -ItemType Directory -Force -Path $dest | Out-Null
foreach ($sub in 'tools', 'tools\vendor', 'courses') {
  New-Item -ItemType Directory -Force -Path (Join-Path $dest $sub) | Out-Null
}
Copy-Item (Join-Path $repo 'skills\learn\SKILL.md')            $dest -Force
Copy-Item (Join-Path $repo 'skills\learn\tools\*.py')          (Join-Path $dest 'tools') -Force
Copy-Item (Join-Path $repo 'skills\learn\tools\*.ps1')         (Join-Path $dest 'tools') -Force
Copy-Item (Join-Path $repo 'skills\learn\tools\README.md')     (Join-Path $dest 'tools') -Force
Copy-Item (Join-Path $repo 'skills\learn\tools\vendor\*')      (Join-Path $dest 'tools\vendor') -Force
if (Test-Path (Join-Path $repo 'skills\learn\courses\*.md')) {
  Copy-Item (Join-Path $repo 'skills\learn\courses\*.md')      (Join-Path $dest 'courses') -Force
}
Copy-Item (Join-Path $repo 'config.example.json') $dest -Force
Write-Host "Skill copied."

# ---------------------------------------------------------------- 1b. the /learn command
$commandsDir = Join-Path $claude 'commands'
New-Item -ItemType Directory -Force -Path $commandsDir | Out-Null
Copy-Item (Join-Path $repo 'commands\learn.md') $commandsDir -Force
Write-Host "Command copied: $(Join-Path $commandsDir 'learn.md') - /learn now works."

# ---------------------------------------------------------------- 2. config.json
$configPath = Join-Path $dest 'config.json'
if (Test-Path $configPath) {
  Write-Host "config.json already exists - left untouched. Delete it to regenerate."
} else {
  if (-not $VaultRoot -and -not $NoPrompt) {
    Write-Host ""
    Write-Host "Where do session notes go? Any Markdown folder; Obsidian is what it is built around."
    $VaultRoot = Read-Host "  vault root [$((Get-Location).Path)]"
  }
  if (-not $VaultRoot) { $VaultRoot = (Get-Location).Path }
  $full = [System.IO.Path]::GetFullPath($VaultRoot)

  if (-not $VaultName) { $VaultName = Split-Path -Leaf $full }

  if (-not $LearningDir -and -not $NoPrompt) {
    $LearningDir = Read-Host "  notes folder inside the vault [Learning]"
  }
  if (-not $LearningDir) { $LearningDir = 'Learning' }
  $LearningDir = $LearningDir.Replace('\', '/').Trim('/')

  if (-not $CourseLearningDir -and -not $NoPrompt) {
    Write-Host "  Organise some notes by course? Give a pattern with {course} in it, or press enter to skip."
    $CourseLearningDir = Read-Host "  course notes pattern []"
  }
  $CourseLearningDir = $CourseLearningDir.Replace('\', '/').Trim('/')

  $cfg = [ordered]@{
    vault_root          = $full
    obsidian_vault_name = $VaultName
    learning_dir        = $LearningDir
    course_learning_dir = $CourseLearningDir
    learner_file        = "$LearningDir/LEARNER.md"
    quiz_log_dir        = "$LearningDir/.quiz-log"
    visuals_dir         = "$LearningDir/visuals"
    chrome_path         = ""
    terminal_process    = ""
  }
  $cfg | ConvertTo-Json -Depth 5 | Set-Content -Path $configPath -Encoding utf8
  Write-Host ""
  Write-Host "Wrote $configPath"
  foreach ($k in $cfg.Keys) { Write-Host ("  {0,-20} {1}" -f $k, $cfg[$k]) }

  # The notes folder and the learner profile have to exist before the first session: quiz.py
  # refuses to write into a note that is not there, and the profile is read before every probe.
  $learningFull = Join-Path $full ($LearningDir -replace '/', '\')
  New-Item -ItemType Directory -Force -Path $learningFull | Out-Null
  $learnerFull = Join-Path $full ($cfg.learner_file -replace '/', '\')
  if (-not (Test-Path $learnerFull)) {
    Copy-Item (Join-Path $repo 'templates\LEARNER.md') $learnerFull -Force
    Write-Host "  seeded $learnerFull - fill in who you are before the first session"
  }
}

# ---------------------------------------------------------------- 3. dependencies
Write-Host ""
Write-Host "Dependencies"
$py = Get-Command py, python -ErrorAction SilentlyContinue | Select-Object -First 1
if ($py) {
  $v = & $py.Source -c "import sys;print('%d.%d' % sys.version_info[:2])"
  Say ([version]$v -ge [version]'3.9') 'python' "$v at $($py.Source)"
} else {
  Say $false 'python' 'not on PATH - quiz.py and both render tools need it'
}

$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
Say ($null -ne $claudeCmd) 'claude' $(if ($claudeCmd) { $claudeCmd.Source } else { 'not on PATH - this is a Claude Code skill' })

$chrome = @(
  "C:\Program Files\Google\Chrome\Application\chrome.exe",
  "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
  Say $true 'chrome' $chrome
} else {
  Say $null 'chrome' 'optional - only the two render tools need it. Set chrome_path if it is installed elsewhere.'
}

if ($py) {
  $pillow = & $py.Source -c "import importlib.util,sys;sys.stdout.write('1' if importlib.util.find_spec('PIL') else '')"
  if ($pillow) { Say $true 'pillow' 'diagram crops will be exact' }
  else { Say $null 'pillow' 'optional - without it a rendered diagram keeps a little slack, never clipped' }
}

$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
if ($pwshCmd) { Say $true 'pwsh' $pwshCmd.Source }
else { Say $null 'pwsh' 'optional - layout.ps1 and open_note.ps1 tile and raise the windows for you' }

# ---------------------------------------------------------------- 4. done
Write-Host ""
Write-Host "Installed. In Claude Code, try:"
Write-Host '  "teach me the master theorem"'
Write-Host "Read $dest\tools\README.md for what each tool does."
