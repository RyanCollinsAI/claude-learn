<#
layout.ps1 - the reading surface on the left, the Claude terminal on the right.

    pwsh -File layout.ps1
    pwsh -File layout.ps1 -Surface podium
    pwsh -File layout.ps1 -Surface obsidian -Split 0.6

The learner reads on one side and answers on the other, so a session wants both
visible at once. This tiles them across the primary monitor's working area,
which is not the same as the full screen - the taskbar is excluded, so nothing
sits underneath it.

-Surface picks what goes on the left. Default is `surface` in config.json,
falling back to obsidian:

  podium    the browser window showing the Podium page. Matched by window
            title (-TitleMatch, default "Podium"), across the usual browsers.
  obsidian  the Obsidian window.

-Split is the fraction of the width given to the left pane (default 0.5). Give
it more on a diagram-heavy session: -Split 0.6.

Exit 0 means both windows were placed. Exit 1 means one of them was not found;
the other is still placed, and the message names what is missing.
#>
param(
  [double]$Split = 0.5,
  [string]$Surface = "",
  [string]$TerminalProcess = "",
  [string]$TitleMatch = "Podium"
)

# config.json sits next to SKILL.md, one level up from tools/. Missing is fine -
# the defaults below then apply.
$cfg = $null
$cfgPath = Join-Path (Split-Path -Parent $PSScriptRoot) "config.json"
if (Test-Path -LiteralPath $cfgPath) {
  $cfg = Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json
}
if (-not $TerminalProcess -and $cfg) { $TerminalProcess = $cfg.terminal_process }
if (-not $Surface) {
  if ($env:LEARN_SURFACE) { $Surface = $env:LEARN_SURFACE }
  elseif ($cfg -and $cfg.surface) { $Surface = $cfg.surface }
  else { $Surface = "obsidian" }
}
$Surface = $Surface.ToLower()

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public class LearnLayout {
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int t, bool repaint);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@ -ErrorAction SilentlyContinue

$area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$leftW = [int]($area.Width * $Split)
$rightW = $area.Width - $leftW

function Place($proc, $x, $w, $name) {
  if (-not $proc) { Write-Warning "$name is not running - nothing to place."; return $false }
  $h = $proc.MainWindowHandle
  if ($h -eq [IntPtr]::Zero) { Write-Warning "$name has no window."; return $false }
  # A maximised window ignores MoveWindow, so restore it first.
  if ([LearnLayout]::IsZoomed($h)) { [LearnLayout]::ShowWindow($h, 9) | Out-Null; Start-Sleep -Milliseconds 200 }
  [LearnLayout]::ShowWindow($h, 9) | Out-Null
  [LearnLayout]::MoveWindow($h, $x, $area.Y, $w, $area.Height, $true) | Out-Null
  # Write-Host, not Write-Output: the caller assigns this function's result, and
  # Write-Output would be captured into that variable instead of printed. The
  # script reported nothing at all on success until this was changed.
  Write-Host ("{0,-22} {1}x{2} at {3},{4}  [{5}]" -f
              $name, $w, $area.Height, $x, $area.Y, $proc.MainWindowTitle)
  return $true
}

function FindByTitle($match) {
  # Podium is a page in whatever browser opened it, so it is found by window
  # title rather than by process name. `lavish-axi` is patched to put "Podium"
  # in the title, which is what makes this reliable.
  Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$match*" } |
    Select-Object -First 1
}

if ($Surface -eq "podium") {
  $left = FindByTitle $TitleMatch
  if (-not $left) {
    # Fall back to any browser window at all, so a page whose title was not
    # patched still gets placed rather than silently skipped.
    foreach ($n in @("chrome", "msedge", "firefox", "brave")) {
      $left = Get-Process $n -ErrorAction SilentlyContinue |
              Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
      if ($left) { break }
    }
  }
  $leftName = "Podium (left)"
} else {
  $left = Get-Process Obsidian -ErrorAction SilentlyContinue |
          Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
  $leftName = "Obsidian (left)"
}

# The terminal running Claude, most specific first. Nothing here is
# machine-specific: set terminal_process in config.json, or pass
# -TerminalProcess, to pin one.
$candidates = if ($TerminalProcess) { @($TerminalProcess) }
              else { @("WindowsTerminal", "wezterm-gui", "alacritty", "conhost") }
$terminal = $null
foreach ($name in $candidates) {
  $terminal = Get-Process $name -ErrorAction SilentlyContinue |
              Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
  if ($terminal) { break }
}

$okL = Place $left 0 $leftW $leftName
$okR = Place $terminal $leftW $rightW "Terminal (right)"

# Leave the focus in the terminal - that is where the session is driven from.
if ($okR) { [LearnLayout]::SetForegroundWindow($terminal.MainWindowHandle) | Out-Null }

if ($okL -and $okR) { exit 0 } else { exit 1 }
