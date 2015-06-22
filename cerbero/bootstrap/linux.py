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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_bootstrapper
from cerbero.config import Platform, Architecture, Distro, DistroVersion
from cerbero.utils import shell

import subprocess

class UnixBootstrapper (BootstrapperBase):

    tool = ''
    packages = []
    distro_packages = {}

    def start(self):
        if self.config.distro_packages_install:
            packages = self.packages
            if self.config.distro_version in self.distro_packages:
                packages += self.distro_packages[self.config.distro_version]
            shell.call(self.tool % ' '.join(self.packages))


class DebianBootstrapper (UnixBootstrapper):

    tool = 'sudo apt-get install %s'
    packages = ['autotools-dev', 'automake', 'autoconf', 'libtool', 'g++',
                'autopoint', 'make', 'cmake', 'bison', 'flex', 'yasm',
                'pkg-config', 'gtk-doc-tools', 'libxv-dev', 'libx11-dev',
                'libpulse-dev', 'python-dev', 'texinfo', 'gettext',
                'build-essential', 'pkg-config', 'doxygen', 'curl',
                'libxext-dev', 'libxi-dev', 'x11proto-record-dev',
                'libxrender-dev', 'libgl1-mesa-dev', 'libxfixes-dev',
                'libxdamage-dev', 'libxcomposite-dev', 'libasound2-dev',
                'libxml-simple-perl', 'dpkg-dev', 'debhelper',
                'build-essential', 'devscripts', 'fakeroot', 'transfig',
                'gperf', 'libdbus-glib-1-dev', 'wget', 'glib-networking',
                'libxtst-dev', 'libxrandr-dev', 'libglu1-mesa-dev',
                'libegl1-mesa-dev', 'git', 'subversion', 'xutils-dev']
    distro_packages = {
        DistroVersion.DEBIAN_SQUEEZE: ['libgtk2.0-dev'],
        DistroVersion.UBUNTU_MAVERICK: ['libgtk2.0-dev'],
        DistroVersion.UBUNTU_LUCID: ['libgtk2.0-dev'],
        DistroVersion.UBUNTU_NATTY: ['libgtk2.0-dev'],
        DistroVersion.DEBIAN_WHEEZY: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.DEBIAN_JESSIE: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.UBUNTU_ONEIRIC: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.UBUNTU_PRECISE: ['libgdk-pixbuf2.0-dev'],
    }

    def __init__(self, config):
        UnixBootstrapper.__init__(self, config)
        if self.config.target_platform == Platform.WINDOWS:
            self.packages.append('mingw-w64-tools')
            if self.config.arch == Architecture.X86_64:
                self.packages.append('libc6:i386')
        if self.config.target_platform == Platform.LINUX:
            self.packages.append('chrpath')
            self.packages.append('libfuse-dev')
        if self.config.distro_version in [DistroVersion.DEBIAN_SQUEEZE,
                DistroVersion.UBUNTU_MAVERICK, DistroVersion.UBUNTU_LUCID]:
            self.packages.remove('glib-networking')
        if self.config.distro_version in [DistroVersion.UBUNTU_LUCID]:
            self.packages.remove('autopoint')


class RedHatBootstrapper (UnixBootstrapper):

    tool = 'su -c "yum install %s"'
    packages = ['gcc', 'gcc-c++', 'automake', 'autoconf', 'libtool',
                'gettext-devel', 'make', 'cmake', 'bison', 'flex', 'yasm',
                'pkgconfig', 'gtk-doc', 'curl', 'doxygen', 'texinfo',
                'texinfo-tex', 'texlive-dvips', 'docbook-style-xsl',
                'transfig', 'intltool', 'rpm-build', 'redhat-rpm-config',
                'python-devel', 'libXrender-devel', 'pulseaudio-libs-devel',
                'libXv-devel', 'mesa-libGL-devel', 'libXcomposite-devel',
                'alsa-lib-devel', 'perl-ExtUtils-MakeMaker', 'libXi-devel',
                'perl-XML-Simple', 'gperf', 'gdk-pixbuf2-devel', 'wget',
                'docbook-utils-pdf', 'glib-networking', 'help2man',
                'dbus-devel', 'glib2-devel', 'libXrandr-devel',
                'libXtst-devel', 'git', 'subversion', 'xorg-x11-util-macros']

    def __init__(self, config):
        UnixBootstrapper.__init__(self, config)
        if self.config.target_platform == Platform.WINDOWS:
            self.packages.append('mingw-w64-tools')
            if self.config.arch == Architecture.X86_64:
                self.packages.append('glibc.i686')
        if self.config.target_platform == Platform.LINUX:
            self.packages.append('chrpath')
            self.packages.append('fuse-devel')
        # Use sudo to gain root access on everything except RHEL
        if self.config.distro_version != DistroVersion.REDHAT_6:
            self.tool = 'sudo ' + self.tool

class OpenSuseBootstrapper (UnixBootstrapper):

    tool = 'sudo zypper install %s'
    packages = ['gcc', 'automake', 'autoconf', 'gcc-c++', 'libtool',
            'gettext-tools', 'make', 'cmake', 'bison', 'flex', 'yasm',
            'gtk-doc', 'curl', 'doxygen', 'texinfo',
            'texlive', 'docbook-xsl-stylesheets',
            'transfig', 'intltool', 'patterns-openSUSE-devel_rpm_build',
            'python-devel', 'xorg-x11-libXrender-devel', 'libpulse-devel',
            'xorg-x11-libXv-devel', 'Mesa-libGL-devel', 'libXcomposite-devel',
            'alsa-devel', 'libXi-devel', 'Mesa-devel',
            'perl-XML-Simple', 'gperf', 'gdk-pixbuf-devel', 'wget',
            'docbook-utils', 'glib-networkinga', 'git', 'subversion']

class ArchBootstrapper (UnixBootstrapper):

    tool = 'sudo pacman -S %s --needed'
    packages = ['intltool', 'cmake', 'doxygen', 'gtk-doc',
            'libtool', 'bison', 'flex', 'automake', 'autoconf', 'make',
            'curl', 'gettext', 'alsa-lib', 'yasm', 'gperf',
            'docbook-xsl', 'transfig', 'libxrender',
            'libxv', 'mesa', 'python2', 'wget', 'glib-networking', 'git',
            'subversion', 'xorg-util-macros']

    def __init__(self, config):
        UnixBootstrapper.__init__(self, config)

        has_multilib = True
        try:
          subprocess.check_output(["pacman", "-Sp", "gcc-multilib"])
        except subprocess.CalledProcessError:
          has_multilib = False

        if self.config.arch == Architecture.X86_64 and has_multilib:
            self.packages.append('gcc-multilib')
        else:
            self.packages.append('gcc')


def register_all():
    register_bootstrapper(Distro.DEBIAN, DebianBootstrapper)
    register_bootstrapper(Distro.REDHAT, RedHatBootstrapper)
    register_bootstrapper(Distro.SUSE, OpenSuseBootstrapper)
    register_bootstrapper(Distro.ARCH, ArchBootstrapper, DistroVersion.ARCH_ROLLING)
