<#
layout.ps1 - Obsidian on the left, the Claude terminal on the right.

    pwsh -File layout.ps1

Obsidian is the reading surface and the terminal is the input surface, so a
learn session wants both visible at once. This tiles them across the primary
monitor's working area, which is not the same as the full screen - the
taskbar is excluded, so nothing sits underneath it.

-Split is the fraction of the width given to Obsidian (default 0.5). Give
Obsidian more when a session is diagram-heavy: -Split 0.6.

Exit 0 means both windows were placed. Exit 1 means one of them was not
running; the other is still placed, and the message names what is missing.
#>
param(
  [double]$Split = 0.5,
  [string]$TerminalProcess = ""
)

# config.json sits next to SKILL.md, one level up from tools/. Missing is fine -
# the candidate list below is then tried in order.
if (-not $TerminalProcess) {
  $cfgPath = Join-Path (Split-Path -Parent $PSScriptRoot) "config.json"
  if (Test-Path -LiteralPath $cfgPath) {
    $TerminalProcess = (Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json).terminal_process
  }
}

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
  Write-Output ("{0,-18} {1}x{2} at {3},{4}" -f $name, $w, $area.Height, $x, $area.Y)
  return $true
}

$obsidian = Get-Process Obsidian -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1

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

$okL = Place $obsidian 0 $leftW "Obsidian (left)"
$okR = Place $terminal $leftW $rightW "Terminal (right)"

# Leave the focus in the terminal - that is where the answers are typed.
if ($okR) { [LearnLayout]::SetForegroundWindow($terminal.MainWindowHandle) | Out-Null }

if ($okL -and $okR) { exit 0 } else { exit 1 }
