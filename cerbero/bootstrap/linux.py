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

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Platform, Architecture, Distro, DistroVersion
from cerbero.utils import shell


class UnixBootstraper (BootstraperBase):

    tool = ''
    packages = []
    distro_packages = {}

    def start(self):
        packages = self.packages
        if self.config.distro_version in self.distro_packages:
            packages += self.distro_packages[self.config.distro_version]
        shell.call(self.tool % ' '.join(self.packages))


class DebianBootstraper (UnixBootstraper):

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
                'gperf', 'libdbus-glib-1-dev', 'wget', 'glib-networking']
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
        UnixBootstraper.__init__(self, config)
        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch == Architecture.X86_64:
                self.packages.append('ia32-libs')
        if self.config.distro_version in [DistroVersion.DEBIAN_SQUEEZE,
                DistroVersion.UBUNTU_MAVERICK, DistroVersion.UBUNTU_LUCID]:
            self.packages.remove('glib-networking')
        if self.config.distro_version in [DistroVersion.UBUNTU_LUCID]:
            self.packages.remove('autopoint')


class RedHatBootstraper (UnixBootstraper):

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
                'docbook-utils-pdf', 'glib-networking']


class OpenSuseBootstraper (UnixBootstraper):

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
            'docbook-utils', 'glib-networking']


def register_all():
    register_bootstraper(Distro.DEBIAN, DebianBootstraper)
    register_bootstraper(Distro.REDHAT, RedHatBootstraper)
    register_bootstraper(Distro.SUSE, OpenSuseBootstraper)
