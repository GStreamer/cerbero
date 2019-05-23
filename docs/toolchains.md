# Toolchain configuration
In cerbero, the toolchain is configured in the platform configuration files (`linux.config`, `windows.config`, `darwing.config`, `android.config`, `ios.config`) by overriding the search path for binaries (eg: `PATH`) and the environment variables used by build systems to select the different toolchain tools to use, for example `CC=x86_64-w64-mingw32-gcc` for the C compiler and `CFLAGS=-m64` for its corresponding C compiler flags.

 The platform's configuration file is selected based on the `target_platform` configuration setting, which is autodetected or can be overriden to cross-compile for a different platform than the build one. Foo example the `config/cross-win64.cbc` configuration is overriding `target_platform` to configure the build as a Windows x86_64 cross-compilation build in the following way:
 ```
from cerbero.config import Platform, Architecture, Distro, DistroVersion

target_platform=Platform.WINDOWS
target_arch=Architecture.X86_64
target_distro=Distro.WINDOWS
target_distro_version=DistroVersion.WINDOWS_7
 ```
## Changing the default toolchain
When working with embedded devices, chip vendors can provide custom toolchains for the platform, usually in the form of a tarball where the tarball is extracted in a directory in the filesystem. A quick way to use the new toolchain is with the configuration option `toolchain_prefix`, changing it to the path where the new toolchain is extracted
```
toolchain_prefix='/opt/mstar-2019/'
```

If it is installed by the operating system, a different way to change the toolchain is by setting the `tools_prefix` configuration option, with the triplet prefix used by the toolchain. This will prefix the value defined to all tools, so `gcc` will become `arm-linux-gnueabi-gcc`:
```
tools_prefix='arm-linux-gnueabi'
```

# Windows
On Windows, cerbero can be built with GCC+MinGW (native and cross-compilation) or with the Visual Studio toolchain (native only).

The final goal on Windows is to use the Visual Studio studio toolchain for all the projects as it provides binaries with Visual Studio debug symbols that integrates pefectly with all the Windows tooling such as debugger or profilers. The current satus is that many projects can be built with the Visual Studio toolchain, but others are still peding to be fixed.

## GCC + MinGW
The GCC + MinGW toolchain is a multilib toolchain that can generate 32 and 64 bits binaries.

It uses the following versions and configurations:
 * GCC: 8.2.0
 * MinGW: 6.0.0
 * Threads: posix
 * Exception handling:
   * 32 bits: SJLJ
   * 64 bits: SEH
 * CRT: Universal CRT

The toolchain now links against the Universal CRT, which is the default CRT used starting from [Visual Studio 2015](https://docs.microsoft.com/en-us/cpp/ide/universal-crt-deployment), making it easier to deploy and to combine libraries built with Visual Studio without having to worry about [cross-CRT issues](https://docs.microsoft.com/en-us/cpp/c-runtime-library/potential-errors-passing-crt-objects-across-dll-boundaries).

### Building the toolchain
The toolchain can be built with cerbero in a Linux x86_64 machine with a helper script that will build first the cross-compilation toolchain and in a second round the native toolchain with the previously generated cross-toolchain and finally generate the toolchain tarballs and checksums:
```
sh tools/build-toolchains.sh
```

The toolchain recipes are kept in a different folder `recipes-toolchain` so that they are not listed with the normal configuration.

### Publishing the toolchain
After building a new toolchain, to make it available to all users the tarballs should be uploaded to `freedesktop.org:/srv/gstreamer.freedesktop.org/www/data/cerbero/toolchain/windows/` and the new sha256 should be updated in `cerbero/bootstrap/windows.py`

## Visual Studio
FIXME: add documentation