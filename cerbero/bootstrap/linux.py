# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import sys

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_system_bootstrapper
from cerbero.enums import Platform, Architecture, Distro, DistroVersion
from cerbero.errors import ConfigurationError, CommandError, FatalError
from cerbero.utils import user_is_root, shell, split_version
from cerbero.utils import messages as m


class UnixBootstrapper(BootstrapperBase):
    tool = []
    command = []
    yes_arg = []
    checks = []
    packages = []

    def __init__(self, config, offline, assume_yes):
        BootstrapperBase.__init__(self, config, offline, 'linux')
        self.assume_yes = assume_yes
        if user_is_root() and 'sudo' in self.tool:  # no need for sudo as root user
            self.tool.remove('sudo')

    async def start(self, jobs=0):
        for c in self.checks:
            c()

        if self.config.distro_packages_install:
            extra_packages = self.config.extra_bootstrap_packages.get(self.config.platform, None)
            override_packages = self.config.override_bootstrap_packages.get(self.config.platform, None)
            if extra_packages and override_packages:
                raise ConfigurationError(
                    'You are setting "extra_bootstrap_packages" and "override_bootstrap_packages" '
                    'on the same CBC. This might cause conflicts.'
                )
            if extra_packages:
                self.packages += extra_packages.get(self.config.distro, [])
                self.packages += extra_packages.get(self.config.distro_version, [])
            if override_packages:
                self.packages = []
                self.packages += override_packages.get(self.config.distro, [])
                self.packages += override_packages.get(self.config.distro_version, [])

            tool = self.tool
            if self.assume_yes:
                tool += self.yes_arg
            tool += self.command
            cmd = tool + self.packages
            m.message("Running command '%s'" % ' '.join(cmd))
            shell.new_call(cmd, interactive=True)


class DebianBootstrapper(UnixBootstrapper):
    tool = ['sudo', 'apt-get']
    command = ['install']
    yes_arg = ['-y']
    packages = [
        'autotools-dev',
        'automake',
        'autoconf',
        'libtool',
        'g++',
        'autopoint',
        'make',
        'cmake',
        'ninja-build',
        'bison',
        'flex',
        'nasm',
        'pkg-config',
        'libxv-dev',
        'libx11-dev',
        'libx11-xcb-dev',
        'libpulse-dev',
        'python3-dev',
        'gettext',
        'build-essential',
        'binutils',
        'pkg-config',
        'libxext-dev',
        'libxi-dev',
        'x11proto-record-dev',
        'libxrender-dev',
        'libgl1-mesa-dev',
        'libxfixes-dev',
        'libxdamage-dev',
        'libxcomposite-dev',
        'libasound2-dev',
        'gperf',
        'libxtst-dev',
        'libxrandr-dev',
        'libglu1-mesa-dev',
        'libegl1-mesa-dev',
        'git',
        'xutils-dev',
        'ccache',
        'python3-setuptools',
        'libssl-dev',
        'libclang-dev',
        'libcurl4-openssl-dev',
        'curl',
    ]

    def __init__(self, config, offline, assume_yes):
        UnixBootstrapper.__init__(self, config, offline, assume_yes)
        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch == Architecture.X86_64:
                self.packages.append('libc6:i386')
                self.checks.append(self.create_debian_arch_check('i386'))
            if self.config.arch in [Architecture.X86_64, Architecture.X86]:
                self.packages += ['wine', 'xvfb']

    def create_debian_arch_check(self, arch):
        def check_arch():
            native_arch = shell.check_output(['dpkg', '--print-architecture'])
            if native_arch == arch:
                return
            foreign_archs = shell.check_output(['dpkg', '--print-foreign-architectures'])
            if arch in foreign_archs.split():
                return
            raise ConfigurationError(
                (
                    'Architecture %s is missing from your setup. '
                    + 'You can add it with: "dpkg --add-architecture %s",'
                    + ' then run "apt-get update."'
                )
                % (arch, arch)
            )

        return check_arch


class RedHatBootstrapper(UnixBootstrapper):
    tool = ['dnf']
    command = ['install']
    yes_arg = ['-y']
    packages = [
        'gcc',
        'gcc-c++',
        'automake',
        'autoconf',
        'libtool',
        'gettext-devel',
        'make',
        'cmake',
        'ninja-build',
        'bison',
        'flex',
        'nasm',
        'pkgconfig',
        'curl',
        'libcurl-devel',
        'rpm-build',
        'redhat-rpm-config',
        'libXrender-devel',
        'pulseaudio-libs-devel',
        'libXv-devel',
        'mesa-libGL-devel',
        'libXcomposite-devel',
        'perl-ExtUtils-MakeMaker',
        'libXi-devel',
        'perl-XML-Simple',
        'gperf',
        'libXrandr-devel',
        'libXtst-devel',
        'git',
        'xorg-x11-util-macros',
        'mesa-libEGL-devel',
        'openssl-devel',
        'alsa-lib-devel',
        'perl-IPC-Cmd',
        'libatomic',
        'clang-devel',
    ]

    def __init__(self, config, offline, assume_yes):
        UnixBootstrapper.__init__(self, config, offline, assume_yes)

        dn, dv = self.config.distro_version.split('_', 1)
        dv = split_version(dv)

        if (dn == 'fedora' and dv < (23,)) or (dn == 'redhat' and dv < (8, 3)):
            self.tool = ['yum']

        if dn == 'redhat' and dv >= (8,):
            if dv < (8, 3):
                self.tool += ['--enablerepo=PowerTools']
            elif dv < (9,):
                self.tool += ['--enablerepo=powertools']
            else:
                self.tool += ['--enablerepo=crb']

        def pkg_available(pkg):
            return shell.new_call(self.tool + ['list', pkg, '-q'], fail=False) == 0

        def add_pkg(names, required=True):
            for pkg in names:
                if pkg_available(pkg):
                    self.packages.append(pkg)
                    return True
            if required:
                raise FatalError('Required package not found, tried: ' + ', '.join(names))
            return False

        if not user_is_root():
            self.tool = ['sudo'] + self.tool

        # In RHEL based distros ccache is only available in the EPEL repo
        if not add_pkg(['ccache'], required=False):
            if pkg_available('epel-release'):
                cmd = self.tool + ['install', 'epel-release'] + (['-y'] if assume_yes else [])
                self.checks.append(
                    lambda: shell.new_call(cmd, interactive=True, fail=False) == 0 and self.packages.append('ccache')
                )
            else:
                m.warning('Compilation will not use ccache since it is not available')
                self.config.use_ccache = False

        # Before RHEL 9 perl-FindBin wasn't a standalone package
        if dn != 'redhat' or dv >= (9,):
            add_pkg(['perl-FindBin'])
        elif dv >= (8,):
            add_pkg(['perl-interpreter'])
        else:
            add_pkg(['perl'])

        # Try to get a better matching python3 library version
        ver = sys.version_info[1]
        add_pkg([f'python3{v}-devel' for v in [ver, f'.{ver}', '']])

        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch == Architecture.X86_64:
                self.packages.append('glibc.i686')
            if self.config.distro_version in ['fedora_24', 'fedora_25']:
                self.packages.append('libncurses-compat-libs.i686')
            if self.config.arch in [Architecture.X86_64, Architecture.X86]:
                self.packages += ['wine', 'which', 'xorg-x11-server-Xvfb']


class OpenSuseBootstrapper(UnixBootstrapper):
    tool = ['sudo', 'zypper']
    command = ['install']
    yes_arg = ['-y']
    packages = [
        'gcc',
        'automake',
        'autoconf',
        'gcc-c++',
        'libtool',
        'gettext-tools',
        'make',
        'cmake',
        'ninja-build',
        'bison',
        'flex',
        'nasm',
        'patterns-openSUSE-devel_rpm_build',
        'python3-devel',
        'xorg-x11-libXrender-devel',
        'libpulse-devel',
        'xorg-x11-libXv-devel',
        'Mesa-libGL-devel',
        'libXcomposite-devel',
        'libX11-devel',
        'alsa-devel',
        'libXi-devel',
        'Mesa-devel',
        'Mesa-libGLESv3-devel',
        'gperf',
        'curl',
        'libcurl4-openssl-dev',
        'git',
        'ccache',
        'openssl-devel',
        'clang',
        'pkg-config',
    ]

    def __init__(self, config, offline, assume_yes):
        UnixBootstrapper.__init__(self, config, offline, assume_yes)
        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch in [Architecture.X86_64, Architecture.X86]:
                self.packages += ['wine', 'xvfb-run']


class ArchBootstrapper(UnixBootstrapper):
    tool = ['sudo', 'pacman']
    command = ['-S', '--needed']
    yes_arg = ['--noconfirm']
    packages = [
        'cmake',
        'ninja',
        'libtool',
        'bison',
        'flex',
        'automake',
        'autoconf',
        'make',
        'gettext',
        'nasm',
        'gperf',
        'libxrender',
        'libxv',
        'mesa',
        'python3',
        'git',
        'xorg-util-macros',
        'ccache',
        'openssl',
        'alsa-lib',
        'which',
        'libpulse',
        'clang',
        'curl',
        'pkgconf',
    ]

    def __init__(self, config, offline, assume_yes):
        UnixBootstrapper.__init__(self, config, offline, assume_yes)

        has_multilib = True
        try:
            shell.check_output(['pacman', '-Sp', 'gcc-multilib'])
        except CommandError:
            has_multilib = False

        if self.config.arch == Architecture.X86_64 and has_multilib:
            self.packages.append('gcc-multilib')
        else:
            self.packages.append('gcc')
        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch in [Architecture.X86_64, Architecture.X86]:
                self.packages += ['wine', 'xorg-server-xvfb']


class GentooBootstrapper(UnixBootstrapper):
    tool = ['sudo', 'emerge']
    command = ['-u']
    yes_arg = []  # Does not seem interactive
    packages = [
        'dev-util/cmake',
        'dev-util/ninja',
        'sys-devel/libtool',
        'sys-devel/bison',
        'sys-devel/flex',
        'sys-devel/automake',
        'sys-devel/autoconf',
        'sys-devel/make',
        'sys-devel/gettext',
        'media-sound/pulseaudio',
        'dev-lang/nasm',
        'dev-util/gperf',
        'x11-libs/libXrender',
        'x11-libs/libXv',
        'media-libs/mesa',
        'net-misc/curl',
        'dev-libs/openssl',
        'media-libs/alsa-lib',
        'sys-devel/clang',
        'dev-util/pkgconf',
    ]

    def __init__(self, config, offline, assume_yes):
        UnixBootstrapper.__init__(self, config, offline, assume_yes)
        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch in [Architecture.X86_64, Architecture.X86]:
                self.packages.append('virtual/wine')


class NoneBootstrapper(BootstrapperBase):
    async def start(self):
        pass


def register_all():
    register_system_bootstrapper(Distro.DEBIAN, DebianBootstrapper)
    register_system_bootstrapper(Distro.REDHAT, RedHatBootstrapper)
    register_system_bootstrapper(Distro.SUSE, OpenSuseBootstrapper)
    register_system_bootstrapper(Distro.ARCH, ArchBootstrapper, DistroVersion.ARCH_ROLLING)
    register_system_bootstrapper(Distro.GENTOO, GentooBootstrapper, DistroVersion.GENTOO_VERSION)
    register_system_bootstrapper(Distro.NONE, NoneBootstrapper)
