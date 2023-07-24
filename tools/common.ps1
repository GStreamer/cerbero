# vim: set sts=2 sw=2 et :

function Get-MSYS2 {
  # Handle some default paths first. This also works if a user installed a
  # system-wide instance of msys64 in these locations, and in that case the
  # shortcuts won't be found by the code in the rest of this function.
  if (Test-Path "C:\msys64") {
    return "C:\msys64"
  }
  if (Test-Path "D:\msys64") {
    return "D:\msys64"
  }

  $Shortcuts = Get-ChildItem -Recurse "$env:AppData\Microsoft\Windows\Start Menu" -Include *.lnk
  $Shell = New-Object -ComObject WScript.Shell
  foreach ($Shortcut in $Shortcuts) {
    $WD = $Shell.CreateShortcut($Shortcut).WorkingDirectory
    if ($WD -clike "*msys64") {
      return $WD
    }
  }
}
