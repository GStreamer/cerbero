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
from cerbero.config import Distro
from cerbero.errors import FatalError
from cerbero.utils import shell, _, user_is_root


class UnixBootstraper (BootstraperBase):

    tool = ''
    packages = []

    def start(self):
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
                'libxdamage-dev', 'libxcomposite-dev', 'libasound2-dev']


class RedHatBootstraper (UnixBootstraper):

    tool = 'su -c "yum install %s"'
    packages = ['gcc', 'gcc-c++', 'automake', 'autoconf', 'libtool', 'gettext-devel',
                'make', 'cmake', 'bison', 'flex', 'yasm', 'pkgconfig-0.25',
                'gtk-doc', 'curl', 'doxygen', 'text-info', 'texlive-dvips',
                'docbook-style-xsl', 'transfig', 'intltool', 'rpm-build',
                'redhat-rpm-config', 'python-devel', 'libXrender-devel',
                'pulseaudio-libs-devel', 'libXv-devel', 'mesa-libGL-devel',
                'libXcomposite-devel', 'alsa-lib-devel']

class OpenSuseBootstraper (UnixBootstraper):

    tool = 'sudo zypper install %s'
    packages = ['intltool', 'cmake', 'gcc-c++', 'doxygen', 'gtk-doc', 'libtool',
                'bison', 'flex', 'automake', 'autoconf', 'make', 'gcc', 'curl',
                'gettext-tools', 'alsa-devel', 'yasm', 'docbook-xsl-stylesheets',
                'transfig', 'xorg-x11-libXrender-devel', 'xorg-x11-libXv-devel',
                'Mesa-devel', 'python-devel', 'devel_rpm_build']

def register_all():
    register_bootstraper(Distro.DEBIAN, DebianBootstraper)
    register_bootstraper(Distro.REDHAT, RedHatBootstraper)
    register_bootstraper(Distro.SUSE, OpenSuseBootstraper)
