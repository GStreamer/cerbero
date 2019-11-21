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

On Linux, you will only need a distribution with python >= 3.5. Cerbero will
use your package manager to install all other required packages during
[bootstrap](#Bootstrap).

### macOS Setup

On macOS you will need to have install the following software:

 * XCode
 * Python 3.5+ https://www.python.org/downloads/

Cerbero will build all other required packages during [bootstrap](#Bootstrap).

### Windows Setup

The initial setup on Windows is somewhat longer since the required packages
must be installed manually. Detailed steps on what you need to install are
**[at the bottom of the page](#installing-minimum-requirements-on-windows)**.

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

Target                 | Config file
:----------------------|:-----------
macOS System Framework | `osx-x86-64.cbc`
iOS Universal          | `cross-ios-universal.cbc`
iOS ARM64              | `cross-ios-arm64.cbc`
iOS ARMv7              | `cross-ios-armv7.cbc`
iOS x86                | `cross-ios-x86.cbc`
iOS x86_64              | `cross-ios-x86-64.cbc`

#### Windows Targets

Target                     | Config file
:--------------------------|:-----------
MinGW 32-bit System Prefix | `win32.cbc`
MinGW 64-bit System Prefix | `win64.cbc`

Currently no cross targets are supported on Windows.


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
$ cerbero-uninstalled -v variantname [-c ...] package gstreamer-1.0
```

* Or, edit `~/.cerbero/cerbero.cbc` and add `variants = ['variantname']` at the
  bottom. Create the file if it doesn't exist.

Multiple variants can either be separated by a comma or with multiple `-v`
arguments, for example the following are equivalent:

```sh
$ cerbero-uninstalled -v variantname1,variantname2 [-c ...] package gstreamer-1.0
$ cerbero-uninstalled -v variantname1 -v variantname2 [-c ...] package gstreamer-1.0
```

To explicitly disable a variant, use `novariantname` instead.

In the case of multiple enabling/disable of the same variant, then the last
condition on the command line will take effect.  e.g. if novariantname is last
then variantname is disabled.

## Enabling Qt5 Support

Starting with version 1.15.2, Cerbero has built-in support for building the Qt5
QML GStreamer plugin. You can toggle that on by
[enabling the `qt5` variant](#enabling-optional-features-with-variants).

You must also tell Cerbero where your Qt5 installation prefix is. You can do it
by setting the `QMAKE` environment variable to point to the `qmake` that you
want to use, f.ex. `/path/to/Qt5.12.0/5.12.0/ios/bin/qmake`

When building for Android Universal, instead of `QMAKE`, you **must** set the
`QT5_PREFIX` environment variable pointed to the directory inside your prefix
which contains all the android targets, f.ex. `/path/to/Qt5.12.0/5.12.0`.

Next, run `package`:

```sh
$ export QMAKE='/path/to/Qt5.12.0/5.12.0/<target>/bin/qmake'
$ ./cerbero-uninstalled -v qt5 [-c ...] package gstreamer-1.0
```

This will try to build the Qt5 QML plugin and error out if Qt5 could not be
found or if the plugin could not be built. The plugin will be automatically
added to the package outputted.

**NOTE:** The package outputted will not contain a copy of the Qt5 libraries in
it. You must link to them while building your app yourself.

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

### Nvidia Hardware Codecs

For Nvidia, the [variant to enable](#enabling-optional-features-with-variants)
is `nvcodec` which will build the `nvenc` and `nvdec` plugins.

If CUDA is not installed into the system prefix, You need to set `CUDA_PATH` to
point to your [CUDA SDK](https://developer.nvidia.com/cuda-downloads) prefix.
On Windows, this is done automatically by the installer.

On Windows, with CUDA v10 and newer, you must also set
`NVIDIA_VIDEO_CODEC_SDK_PATH` to point to your [Video Codec
SDK](https://developer.nvidia.com/nvidia-video-codec-sdk) prefix. There is no
installer for this, so you must extract the SDK zip and set the env var to point
to the path to the extracted folder.

## Enabling Visual Studio Support

Starting with version 1.15.2, Cerbero supports building all GStreamer recipes,
all mandatory dependencies (such as glib, libffi, zlib, etc), and some external
dependencies with Visual Studio. You must explicitly opt-in to this by [enabling
the `visualstudio` variant](#enabling-optional-features-with-variants):

```sh
$ python ./cerbero-uninstalled -v visualstudio package gstreamer-1.0
```

If you already have a Cerbero build, it is highly recommended to run the `wipe`
command before switching to building with Visual Studio.

[Some plugins that require external dependencies will be automatically
disabled](https://gitlab.freedesktop.org/gstreamer/cerbero/issues/121) when
running in this mode.

Currently, most recipes that use Meson (`btype = BuildType.MESON`) and those
that have the `can_msvc` recipe property set to `True` are built with Visual
Studio.


# Installing Minimum Requirements on Windows

These steps are necessary for using Cerbero on Windows.

#### Install Python 3.5 or newer (either 32-bit or 64-bit)

Download the [Windows executable installer](https://www.python.org/downloads/) and run it.

* On the first page of the installer, select the following:

![Enable Add Python to PATH, then click Customize Installation](/data/images/py-installer-page1.png)

* On the second page, the defaults are fine

* Third page, you must select the following options:

![Enable Install for all users, associate files with Python, add Python to environment variables, and customize the install location to not have any spaces in it](/data/images/py-installer-page3.png)

#### Install Git for Windows

Download the [Git for Windows installer](https://gitforwindows.org/) and run it.

* First page is the license

* Next page is `Select Components`, the defaults are fine, enable whatever else you prefer

* Next `Choosing the default editor used by Git`, select whatever you prefer

* Next `Adjusting your PATH environment`, you *must* select as shown in the screenshot

![Select "Git from the command line and also from 3rd-party software"](/data/images/git-installer-PATH.png)

* Next `Choosing HTTPS transport backend`, default is fine

* Next `Configuring the line ending conversions`, you *must* select as shown in the screenshot

![Select "Git from the command line and also from 3rd-party software"](/data/images/git-installer-line-endings.png)

* Next `Configuring the terminal emulator`, default is fine

* Next `Configuring extra options`, defaults are fine

Git will be installed at `C:\Program Files\Git`.

#### Install MSYS/MinGW

Download the [`mingw-get-setup` executable installer](http://sourceforge.net/projects/mingw/files/Installer/mingw-get-setup.exe/download) and run it.

* First page, keep all the options as-is

* Second page will download the latest package catalogue and base packages

* Once done, the MinGW Installation Manager will open, select the following
  packages under Basic Setup:

![Under Basic Setup, select mingw-developer-toolkit, mingw32-base, and msys-base](/data/images/msys-install-packages.png)

Then, click on the `Installation` menu and select `Apply Changes`. MSYS will be
installed at `C:\MinGW`.

**IMPORTANT:** After installation, you must create a shortcut on the desktop to
`C:\MinGW\msys\1.0\msys.bat` which will run the MinGW shell. **You must run
Cerbero from inside that**.

**NOTE**: Cerbero does not use the MinGW compiler toolchain shipped with MSYS.
We download our own custom GCC toolchain during [bootstrap](#Bootstrap).

**NOTE**: MSYS is not the same as [MSYS2](https://www.msys2.org/), and the
GStreamer project does not support running Cerbero inside the MSYS2
environment. Things may work or they may break, and you get to keep the pieces.

#### Install Visual Studio 2015 or newer

This is needed for correctly generating import libraries for recipes built with
MinGW. Both the Community build and the Professional build are supported.

You must install the latest Windows 10 SDK when installing Visual Studio as
shown below. You do not need any older Windows SDKs.

![Select the Desktop development with C++ workload](/data/images/vs2017-installer-workloads.png)

You can find all versions of Visual Studio at:
https://visualstudio.microsoft.com/vs/older-downloads/

#### Install other tools

* CMake: http://www.cmake.org/cmake/resources/software.html

* WiX 3.11.1 installer: https://github.com/wixtoolset/wix3/releases/tag/wix3111rtm

#### Important Windows-specific Notes

You should add the cerbero git directory to the list of excluded folders in your
anti-virus, or you will get random build failures when Autotools does file
operations such as renames and deletions. It will also slow your build by
about 3-4x.

Cerbero must be run in the MingGW shell, which is accessible from the main menu
or desktop. If it is not, create a shortcut on the desktop to `C:\MinGW\msys\1.0\msys.bat`

The path to your `$HOME` must not contain spaces. If your Windows username
contains spaces, you can create a new directory in `/home` and execute:

```cmd
$ echo 'export HOME=/home/newdir' > ~/.profile
```

Then restart your shell and type `cd` to go to the new home directory.

Note that inside the shell, `/` is mapped to `C:\Mingw\msys\1.0\`
