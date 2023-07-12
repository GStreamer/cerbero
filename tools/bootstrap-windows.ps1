[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;

# Disable progress bars, which are super slow especially Invoke-WebRequest
# which updates the progress bar for each byte
$ProgressPreference = 'SilentlyContinue'

$vs2019_url = 'https://aka.ms/vs/16/release/vs_buildtools.exe'
$vs2022_url = 'https://aka.ms/vs/17/release/vs_buildtools.exe'
$choco_url = 'https://chocolatey.org/install.ps1'

Get-Date
Write-Host "Installing Chocolatey"
Invoke-Expression ((New-Object System.Net.WebClient).DownloadString($choco_url))
Import-Module "$env:ProgramData\chocolatey\helpers\chocolateyProfile.psm1"
Update-SessionEnvironment

Write-Host "Installing vcredist140"
choco install vcredist140

Write-Host "Installing CMake"
choco install cmake --installargs 'ADD_CMAKE_TO_PATH=System'

Write-Host "Installing git"
choco install git --params "/NoAutoCrlf /NoCredentialManager /NoShellHereIntegration /NoGuiHereIntegration /NoShellIntegration"

Write-Host "Installing git-lfs"
choco install git-lfs

Write-Host "Installing Python3"
choco install python3

Write-Host "Installing Wix"
choco install wixtoolset

Write-Host "Installing MSYS2"
choco install msys2 --params "/InstallDir:C:\msys64"
C:\msys64\usr\bin\bash -lc 'pacman --noconfirm -S --needed winpty'
Add-Content C:\msys64\ucrt64.ini "`nMSYS2_PATH_TYPE=inherit"
Copy-Item "data\msys2\profile.d\aliases.sh" -Destination "C:\msys64\etc\profile.d"

$confirmation = Read-Host "Do you want to install Visual Studio build tools? [y/N] "
if ($confirmation -eq 'y') {
  $version = ''
  $vs_arglist = '--wait --quiet --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
  while (1) {
    $version = Read-Host "Pick the Visual Studio version: 2019 or 2022? [2019/2022] "
    if ($version -eq '2022') {
      $vs_url = $vs2022_url
      break
    } elseif ($version -eq '2019') {
      $vs_url = $vs2019_url
      $vs_arglist += ' --add Microsoft.VisualStudio.Component.Windows11SDK.22000'
      break
    } elseif ($version -eq 'q') {
      Write-Host "Windows Dependencies Installation Completed"
      Exit 0
    } else {
      Write-Host "Selected invalid version $version, retry or press 'q' to quit"
    }
  }
  Get-Date
  Write-Host "Downloading Visual Studio $version build tools"
  Invoke-WebRequest -Uri $vs_url -OutFile "$env:TEMP\vs_buildtools.exe"

  Get-Date
  Write-Host "Installing Visual Studio $version build tools"
  Start-Process -NoNewWindow -Wait "$env:TEMP\vs_buildtools.exe" -ArgumentList $vs_arglist
  if (!$?) {
    Write-Host "Failed to install Visual Studio build tools"
    Exit 1
  }
  Remove-Item "$env:TEMP\vs_buildtools.exe" -Force
}

Write-Host "Windows Dependencies Installation Completed"
