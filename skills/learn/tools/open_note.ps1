<#
open_note.ps1 - open a vault note in Obsidian AND raise the window.

    pwsh -File open_note.ps1 -Note "<learning_dir>/master-theorem"

-Note is vault-relative, forward slashes, no .md extension. The file must
already exist; the obsidian:// URI navigates but never creates.

-Vault and -VaultRoot default to obsidian_vault_name and vault_root in
config.json next to SKILL.md. Nothing machine-specific is hardcoded here.

Exit 0 means the window title confirms the note is open and in front.
Exit 1 means the note file was not found.
Exit 2 means Obsidian never reported the note in its title inside -TimeoutSec.

Two things this handles that a bare Start-Process does not:
  1. The path is URI-escaped, so spaces and the slashes survive.
  2. The window is actually raised. Windows refuses a background
     SetForegroundWindow on its own, so it is paired with AttachThreadInput.
#>
param(
  [Parameter(Mandatory = $true)][string]$Note,
  [string]$Vault = "",
  [string]$VaultRoot = "",
  [int]$TimeoutSec = 25
)

$ErrorActionPreference = "Stop"

# config.json sits next to SKILL.md, one level up from tools/. A missing file is
# not an error - the defaults below then apply, the same as for the Python tools.
$cfg = @{}
$cfgPath = Join-Path (Split-Path -Parent $PSScriptRoot) "config.json"
if (Test-Path -LiteralPath $cfgPath) {
  $cfg = Get-Content -LiteralPath $cfgPath -Raw | ConvertFrom-Json
}
function CfgValue($key, $fallback) {
  $env = [Environment]::GetEnvironmentVariable("LEARN_" + $key.ToUpper())
  if ($env) { return $env }
  $v = $cfg.$key
  if ([string]::IsNullOrWhiteSpace($v)) { return $fallback }
  return $v
}

if (-not $VaultRoot) { $VaultRoot = CfgValue "vault_root" (Get-Location).Path }
if (-not $Vault)     { $Vault     = CfgValue "obsidian_vault_name" (Split-Path -Leaf $VaultRoot) }

$full = Join-Path $VaultRoot ($Note -replace '/', '\')
if (-not $full.EndsWith(".md")) { $full = "$full.md" }
if (-not (Test-Path -LiteralPath $full)) {
  Write-Error "open_note: no such note - $full. Create the file first; the URI will not."
  exit 1
}

Add-Type @"
using System; using System.Runtime.InteropServices;
public class LearnFg {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  public static void Raise(IntPtr h) {
    ShowWindow(h, 9);
    uint me = GetCurrentThreadId();
    uint other = GetWindowThreadProcessId(GetForegroundWindow(), IntPtr.Zero);
    AttachThreadInput(other, me, true);
    BringWindowToTop(h); SetForegroundWindow(h);
    AttachThreadInput(other, me, false);
  }
}
"@ -ErrorAction SilentlyContinue

$uri = "obsidian://open?vault=$Vault&file=" + [uri]::EscapeDataString($Note)
Start-Process $uri

# The title reads "<note> - <vault> - Obsidian <version>" only once the note is
# open. A title of just "<vault> - Obsidian ..." means Obsidian is still
# starting - wait and re-read rather than calling the navigation failed.
$leaf = Split-Path $Note -Leaf
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
  $p = Get-Process Obsidian -ErrorAction SilentlyContinue |
       Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
  if ($p -and $p.MainWindowTitle -like "$leaf*") {
    [LearnFg]::Raise($p.MainWindowHandle)
    Start-Sleep -Milliseconds 250
    Write-Output "open: $($p.MainWindowTitle)"
    exit 0
  }
  Start-Sleep -Milliseconds 500
}

Write-Error "open_note: Obsidian never showed '$leaf' in its title within ${TimeoutSec}s."
exit 2
