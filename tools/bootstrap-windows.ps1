[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;

$msvc_2019_url = 'https://aka.ms/vs/16/release/vs_buildtools.exe'
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
C:\msys64\usr\bin\bash -lc 'pacman --noconfirm -S -q --needed winpty perl'
Add-Content C:\msys64\ucrt64.ini "`nMSYS2_PATH_TYPE=inherit"

$confirmation = Read-Host "Visual Studio 2019 build tools will be installed, do you want to proceed:[y/n]"
if ($confirmation -eq 'y') {
  Get-Date
  Write-Host "Downloading Visual Studio 2019 build tools"
  Invoke-WebRequest -Uri $msvc_2019_url -OutFile C:\vs_buildtools.exe

  Get-Date
  Write-Host "Installing Visual Studio 2019"
  Start-Process -NoNewWindow -Wait C:\vs_buildtools.exe -ArgumentList '--wait --quiet --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
  if (!$?) {
    Write-Host "Failed to install Visual Studio tools"
    Exit 1
  }
  Remove-Item C:\vs_buildtools.exe -Force
}


Write-Host "Windows Dependencies Installation Completed"
