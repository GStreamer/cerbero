. "$PSScriptRoot\tools\common.ps1"

$WD = (Get-MSYS2)
if (!$WD) {
  Write-Host "Could not auto-detect MSYS2 install, please install it or run tools\bootstrap-windows.ps1"
  exit 1
}
Write-Host "Auto-detected MSYS2 install location as $WD"
$CerberoDir = $PSScriptRoot.replace('\', '/')
$args = $args.replace('\', '/')
Invoke-Expression "$WD\msys2_shell.cmd -ucrt64 -defterm -no-start -here -use-full-path -c `"$CerberoDir/cerbero-uninstalled $args`""
