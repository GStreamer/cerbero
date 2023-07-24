# Description

Cerbero is a cross-platform build aggregator for Open Source projects that builds
and creates native packages for different platforms, architectures and distributions.
It supports both native compilation and cross compilation and can run on macOS,
Linux, and Windows.

Projects are defined using recipe files (.recipe), which provide a description
of the project being built such as name, version, licenses, sources and the way
it's built. It also provide listing of files, which is later used for the packaging.

Packages are defined using package files (.package), describing the package name,
version, license, maintainer and other fields used to create the packages. A
package wraps a list of recipes, from which the list of files belonging to the
package will be extracted.

# Minimum Requirements

Cerbero provides bootstrapping facilities for all platforms, but it still needs a
minimum base to bootstrap on top of.

### Linux Setup

On Linux, you will only need a distribution with python >= 3.7. Cerbero will
use your package manager to install all other required packages during
[bootstrap](#Bootstrap).

### macOS Setup

On macOS you will need to have install the following software:

* XCode
* Python 3.7+ https://www.python.org/downloads/

Cerbero will build all other required packages during [bootstrap](#Bootstrap).

### Windows Setup

The initial setup on Windows is automated with the PowerShell script
[bootstrap-windows](tools/bootstrap-windows.ps1). It will auto-detect and
installs the necessary tools with [Chocolatey](https://chocolatey.org/):

* Visual Studio 2019 or 2022 Build Tools
* CMake
* MSYS2
* Git
* Python 3
* WiX

Start an admin PowerShell and run:

```powershell
# Enable running scripts
$ Set-ExecutionPolicy -ExecutionPolicy Unrestricted

# Run the bootstrap script
$ .\tools\bootstrap-windows.ps1
```

**IMPORTANT:** Using cerbero on Windows with the [GCC/MinGW toolchain](docs/toolchains.md#Windows)
requires a 64-bit operating system. The toolchain is only available for 64-bit
and it can produce 32-bit or 64-bit binaries.

# Running Cerbero

Despite the presence of `setup.py` this tool does not need installation. It is invoked via the
cerbero-uninstalled script, which should be invoked as `./cerbero-uninstalled`, or you can add
the cerbero directory in your path and invoke it as `cerbero-uninstalled`.

### Bootstrap

Before using cerbero for the first time, you will need to run the bootstrap
command.  This command installs the missing parts of the build system using the
packages manager when available, and also downloads the necessary toolchains
when building for Windows or Android.

Note that this will take a while (a couple hours or even more on Windows).

```sh
$ ./cerbero-uninstalled bootstrap
```

### Command Reference

```shell
# Help
$ ./cerbero-uninstalled --help

# Command-specific help
$ ./cerbero-uninstalled <command> --help

# List available recipes
$ ./cerbero-uninstalled list

# Build a recipe
$ ./cerbero-uninstalled build glib

# Force-rebuild a single recipe
$ ./cerbero-uninstalled buildone glib

# Run the compile step of a recipe
$ ./cerbero-uninstalled buildone glib --steps compile

# Create a package (this automatically builds all recipes in the package)
$ ./cerbero-uninstalled package gstreamer-1.0
```

## Cross Compilation

If you're using Cerbero to cross-compile to iOS, Android, or Cross-MinGW, you
must select the appropriate config file and pass it to all steps: bootstrap,
build, package, etc.

For example if you're on Linux and you want to build for Android Universal, you
must run:

```sh
# Bootstrap for Android Universal on Linux
$ ./cerbero-uninstalled -c config/cross-android-universal.cbc bootstrap

# Build everything and package for Android Universal
$ ./cerbero-uninstalled -c config/cross-android-universal.cbc package gstreamer-1.0
```

Here's a list of config files for each target machine:

#### Linux Targets

Target            | Config file
:-----------------|:-----------
MinGW 32-bit      | `cross-win32.cbc`
MinGW 64-bit      | `cross-win64.cbc`
Android Universal | `cross-android-universal.cbc`
Android ARM64     | `cross-android-arm64.cbc`
Android ARMv7     | `cross-android-armv7.cbc`
Android x86       | `cross-android-x86.cbc`
Android x86_64    | `cross-android-x86-64.cbc`

#### macOS Targets

Target                         | Config file
:------------------------------|:-----------
macOS Universal (relocatable)  | `cross-macos-universal.cbc`
macOS x86_64 (relocatable)     | `cross-macos-x86-64.cbc`
macOS ARM64 (relocatable)      | `cross-macos-arm64.cbc`
macOS x86_64 (not-relocatable) | `osx-x86-64.cbc`
iOS Universal                  | `cross-ios-universal.cbc`
iOS ARM64                      | `cross-ios-arm64.cbc`
iOS x86_64                     | `cross-ios-x86-64.cbc`

#### Windows Targets

On Windows, config files are used to select the architecture and variants are
used to select the toolchain (MinGW, MSVC, UWP):

Target          | Config file               | Variant
:---------------|:--------------------------|:-------
MSVC x86        | `win32.cbc`               |
MSVC x86_64     | `win64.cbc`               |
MinGW x86       | `win32.cbc`               | mingw
MinGW x86_64    | `win64.cbc`               | mingw
UWP x86         | `win32.cbc`               | uwp
UWP x86_64      | `win64.cbc`               | uwp
UWP ARM64       | `cross-win-arm64.cbc`     | uwp
UWP Universal   | `cross-uwp-universal.cbc` | (implicitly uwp)

Example usage:

```sh
# Target MSVC 64-bit
$ ./cerbero-uninstalled -c config/win64.cbc package gstreamer-1.0

# Target MinGW 32-bit
$ ./cerbero-uninstalled -c config/win32.cbc -v mingw package gstreamer-1.0

# Target UWP, x86_64
$ ./cerbero-uninstalled -c config/win64.cbc -v uwp package gstreamer-1.0

# Target UWP, Cross ARM64
$ ./cerbero-uninstalled -c config/cross-win-arm64.cbc -v uwp package gstreamer-1.0

# Target UWP, All Supported Arches
$ ./cerbero-uninstalled -c config/cross-uwp-universal.cbc package gstreamer-1.0
```

# Enabling Optional Features with Variants

Cerbero controls optional and platform-specific features with `variants`. You
can see a full list of available variants by running:

```sh
$ ./cerbero-uninstalled --list-variants
```

Some variants are enabled by default while others are not. You can enable
a particular variant by doing one of the following:

* Either invoke `cerbero-uninstalled` with the `-v` argument, for example:

```sh
$ ./cerbero-uninstalled -v variantname [-c ...] package gstreamer-1.0
```

* Or, edit `~/.cerbero/cerbero.cbc` and add `variants = ['variantname']` at the
  bottom. Create the file if it doesn't exist.

Multiple variants can either be separated by a comma or with multiple `-v`
arguments, for example the following are equivalent:

```sh
$ ./cerbero-uninstalled -v variantname1,variantname2 [-c ...] package gstreamer-1.0
$ ./cerbero-uninstalled -v variantname1 -v variantname2 [-c ...] package gstreamer-1.0
```

To explicitly disable a variant, use `novariantname` instead.

In the case of multiple enabling/disable of the same variant, then the last
condition on the command line will take effect.  e.g. if novariantname is last
then variantname is disabled.

## Enabling Qt5 or Qt6 Support

Cerbero has built-in support for building the Qt5 and Qt6 QML GStreamer
plugins. You can toggle them on by [enabling the `qt5` and/or `qt6`
variants](#enabling-optional-features-with-variants).

You must also tell Cerbero where your Qt installation prefix is. You can do it
by setting the environment variable `QMAKE` (for Qt5) or `QMAKE6` (for qt6) to
the `qmake` that you want to use, f.ex.
`QMAKE=/path/to/Qt5.12.0/5.12.0/ios/bin/qmake` or
`QMAKE6=C:\Qt\6.5.0\msvc2019_64\bin\qmake6.exe`

When building for Android Universal with Qt < 5.14, instead of `QMAKE`, you
**must** set the `QT5_PREFIX` environment variable pointed to the directory
inside your prefix which contains all the android targets, f.ex.
`/path/to/Qt5.12.0/5.12.0`.

Next, run `package`:

```sh
$ export QMAKE='/path/to/Qt5.12.0/5.12.0/<target>/bin/qmake'
$ ./cerbero-uninstalled -v qt5 [-c ...] package gstreamer-1.0
```

This will try to build the Qt5 QML plugin and error out if Qt5 could not be
found or if the plugin could not be built. The plugin will be automatically
added to the package outputted.

Similarly, if you set `QMAKE6` and enable the `qt6` variant, the same will be
done for Qt6.

**NOTE:** The package outputted will not contain a copy of the Qt libraries in
it. You must link to them while building your app yourself.

## Enabling Rust / Cargo Support

Starting with version 1.22, Cerbero supports bootstrapping Rust toolchains, and
can build Rust gstreamer plugins.

This is enabled by default for the following configurations: native-linux,
cross-macos-universal, native-win64 (msvc), native-win32 (msvc).

More targets will be enabled in the future. If you want to force-enable the
feature, you can use the [`rust` variant](#enabling-optional-features-with-variants)
by invoking cerbero as follows:

```
$ ./cerbero-uninstalled -v rust <command>
```

## Enabling Hardware Codec Support

Starting with version 1.15.2, Cerbero has built-in support for building and
packaging hardware codecs for Intel and Nvidia. If the appropriate variant is
enabled, the plugin will either be built or Cerbero will error out if that's
not possible.

### Intel Hardware Codecs

For Intel, the [variant to enable](#enabling-optional-features-with-variants)
is `intelmsdk` which will build the `msdk` plugin.

You must set the `INTELMEDIASDKROOT` env var to point to your [Intel Media
SDK](https://software.intel.com/en-us/media-sdk) prefix, or you must have the
SDK's pkgconfig prefix in `PKG_CONFIG_PATH`

On Windows, `INTELMEDIASDKROOT` automatically set by the installer. On Linux,
if you need to set this, you must set it to point to the directory that
contains the mediasdk `include` and `lib64` dirs.

For VA-API, the [variant to enable](#enabling-optional-features-with-variants)
is `vaapi` which will build the gstreamer-vaapi plugins with all
options enabled if possible.

### Nvidia Hardware Codecs

Since 1.17.1, the `nvcodec` plugin does not need access to the Nvidia Video SDK
or the CUDA SDK. It now loads everything at runtime. Hence, it is now enabled
by default on all platforms.

## Building without Visual Studio

Starting with version 1.22, Cerbero defaults to building all GStreamer recipes,
all mandatory dependencies (such as glib, libffi, zlib, etc), and some external
dependencies with Visual Studio.

If you want to build only with the MinGW toolchain and without Visual Studio,
you can do so by [enabling the `mingw` variant](#enabling-optional-features-with-variants):

```sh
$ ./cerbero-uninstalled -v mingw package gstreamer-1.0
```

Note that Autotools recipes continue to require MinGW.

#### Important Windows-specific Notes

* MSYS2 comes with different [environments](https://www.msys2.org/docs/environments/).
Cerbero must be run using the UCRT64, since it targets the same CRT as our toolchain.
The UCRT64 shell can be launched with the application : `c:\msys64\ucrt64.exe`

* You should add the cerbero git directory to the list of excluded folders in your
anti-virus, or you will get random build failures when Autotools does file
operations such as renames and deletions. It will also slow your build by
about 3-4x.

* If you are using Windows 10, it is also highly recommended to enable "Developer
Mode" in Windows Settings as shown below.

![Enable Developer Mode in Windows Settings](/data/images/windows-settings-developer-mode.png)

* The path to your `$HOME` must not contain spaces. If your Windows username
contains spaces, you can create a new directory in `/home` and execute:

  ```cmd
  $ echo 'export HOME=/home/newdir' > ~/.profile
  ```

  Then restart your shell and type `cd` to go to the new home directory.

  Note that inside the shell, `/` is mapped to `C:\msys64`

# Customising Cerbero

## How to build a custom GStreamer repository or branch

Create a `localconf.cbc` file and add the following:

```
# Set custom remote and branch for all gstreamer recipes
recipes_remotes = {'gstreamer-1.0': {'custom-remote': '<YOUR_GIT_REPO>'}}
recipes_commits = {'gstreamer-1.0': 'custom-remote/<YOUR_GIT_BRANCH>'}
```

You can then run Cerbero with e.g.:

```cmd
./cerbero-uninstalled -c localconf.cbc -c config/win64.cbc -v visualstudio package gstreamer-1.0
```

This works for all builds of course, not only the Windows one.

## How to force a specific Visual Studio version

Create a `localconf.cbc` file and add the following:

```
# Specify Visual Studio install path and version
vs_install_path = 'C:/Path/To/Install'

# This is the Visual Studio Compiler toolset version, vs16 is for Visual Studio 2019. vs15 is 2017, and so on
vs_install_version = 'vs16'
```
You can then run Cerbero with e.g.:

```cmd
./cerbero-uninstalled -c localconf.cbc -c config/win64.cbc -v visualstudio package gstreamer-1.0
```
