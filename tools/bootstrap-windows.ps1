# vim: set sts=2 sw=2 et :

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;

. "$PSScriptRoot\common.ps1"

# Disable progress bars, which are super slow especially Invoke-WebRequest
# which updates the progress bar for each byte
$ProgressPreference = 'SilentlyContinue'

$cmake_req = '3.10.2'
$git_req = '2.0' # placeholder
$python_req = '3.7'
$wix_req = '5.0.1'
$vs2019_url = 'https://aka.ms/vs/16/release/vs_buildtools.exe'
$vs2022_url = 'https://aka.ms/vs/17/release/vs_buildtools.exe'
$wix_url = 'https://github.com/wixtoolset/wix/releases/download/v5.0.1/wix-cli-x64.msi'
$choco_url = 'https://chocolatey.org/install.ps1'
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"

function Check-VS {
  if (!(Test-Path $vswhere)) {
    return $false
  }

  # Check whether we have VS 2019 or newer with the Windows 11 SDK installed
  $json = (& $vswhere -utf8 -version 16 -nologo -format json -latest -all -prerelease -requires '*Windows11*')
  if ($json) {
    return $true
  }

  # Check whether we have a VS 2019 or newer install at all
  $json = (& $vswhere -utf8 -version 16 -nologo -format json -latest -all -prerelease)
  if (!$json) {
    return $false
  }

  $latest = ConvertFrom-Json -InputObject "$json"
  # VS newer than 2019, nothing special needed
  if (!($latest.installationVersion -clike "16.*")) {
    return $true
  }

  $confirm = Read-Host "Need Windows 11 SDK with Visual Studio 2019, do you want to install it right now? [Y/n] "
  if ($confirm -eq 'n') {
    Write-Host "Please run the Visual Studio installer, click 'modify' and install the 'Windows 11 SDK' workload"
    return $true
  }

  & $latest.properties.setupEngineFilePath modify `
    --productId $latest.productId `
    --channelId $latest.channelId `
    --add Microsoft.VisualStudio.Component.Windows11SDK.22000 `
    --quiet --nocache --norestart

  return $true
}

function Install-VS {
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
      return $true
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
    return $false
  }
  Remove-Item "$env:TEMP\vs_buildtools.exe" -Force
  return $true
}

Get-Date

$choco_psm = "$env:ProgramData\chocolatey\helpers\chocolateyProfile.psm1"
if (Test-Path $choco_psm) {
  Import-Module $choco_psm
  Update-SessionEnvironment
  Write-Host "Found Chocolatey, upgrading it first"
  choco upgrade -y chocolatey
} else {
  Write-Host "Installing Chocolatey"
  Invoke-Expression ((New-Object System.Net.WebClient).DownloadString($choco_url))
  Import-Module $choco_psm
  Update-SessionEnvironment
}

choco feature enable --name="'useEnhancedExitCodes'"
choco list vcredist140
if (!$?) {
  Write-Host "Installing vcredist140"
  choco install -y vcredist140
}

if (!(Is-Newer 'cmake' $cmake_req)) {
  Write-Host "CMake >= $cmake_req not found, installing..."
  choco install -y cmake --installargs 'ADD_CMAKE_TO_PATH=System'
}

if (!(Is-Newer 'git' $git_req)) {
  Write-Host "git >= $git_req not found, installing..."
  choco install -y git --params "/NoAutoCrlf /NoCredentialManager /NoShellHereIntegration /NoGuiHereIntegration /NoShellIntegration"
}

if (!(Is-Newer 'git-lfs' $git_req)) {
  Write-Host "git-lfs not found, installing..."
  choco install -y git-lfs
}

if (!(Is-Newer 'py' $python_req)) {
  Write-Host "Python >= $python_req not found, installing..."
  choco install -y python3
}
python -m pip install setuptools

if (!(Is-Newer 'wix' $wix_req) -and !(Is-Newer "$env:WIX5\wix" $wix_req)) {
  Write-Host "WiX >= $wix_req not found, installing..."
  Invoke-WebRequest -Uri $wix_url -OutFile "$env:TEMP\wix-tools-x64.msi"

  Get-Date
  Write-Host "Installing .NET Core 8"
  choco install -y dotnet-8.0-runtime
  if (!$?) {
    Write-Host "Failed to install .NET Core 8"
    return $false
  }
  Write-Host "Installing WiX"
  Start-Process -NoNewWindow -Wait "msiexec" -ArgumentList "/I $env:TEMP\wix-tools-x64.msi /Qn /norestart"
  if (!$?) {
    Write-Host "Failed to install WiX"
    return $false
  }
  Remove-Item "$env:TEMP\wix-tools-x64.msi" -Force
}

$MSYS2_Dir = (Get-MSYS2)
if (!$MSYS2_Dir) {
  Write-Host "MSYS2 not found, installing..."
  choco install msys2 --params "/InstallDir:C:\msys64"
  $MSYS2_Dir = "C:\msys64"
}

& $MSYS2_Dir\usr\bin\bash -lc 'pacman -Qq winpty &>/dev/null'
if (!$?) {
  & $MSYS2_Dir\usr\bin\bash -lc 'pacman --noconfirm -S --needed winpty'
}
if (!((Get-Content "$MSYS2_Dir\ucrt64.ini") -clike "MSYS2_PATH_TYPE=inherit")) {
  Add-Content "$MSYS2_Dir\ucrt64.ini" "`nMSYS2_PATH_TYPE=inherit"
}
Copy-Item "$PSScriptRoot\..\data\msys2\profile.d\aliases.sh" -Destination "$MSYS2_Dir\etc\profile.d"

if (!(Check-VS)) {
  $confirm = Read-Host "Visual Studio 2019 or 2022 not found, do you want to Visual Studio build tools now? [Y/n] "
  if ($confirm -ne 'n' -and !(Install-VS)) {
    exit 1
  }
}

Write-Host "Windows Dependencies Installation Completed"
