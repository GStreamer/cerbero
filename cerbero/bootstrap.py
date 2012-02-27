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

from cerbero import utils
from cerbero.config import Distro
from cerbero.errors import FatalError
from cerbero.utils import shell, _


class BootstraperBase (object):

    def start(self):
        raise NotImplemented("'start' must be implemented by subclasess")


class UnixBootstraper (BootstraperBase):

    tool = ''
    packages = []

    def __init__(self):
        if not utils.user_is_root():
            raise FatalError(_("The bootstrap command must be run as root"))

    def start(self):
        shell.call('%s %s' % (self.tool, ' '.join(self.packages)))


class DebianBootstraper (UnixBootstraper):

    tool = 'apt-get install'
    packages = ['autotools-dev', 'automake', 'autoconf', 'libtool', 'g++',
                'autopoint', 'make', 'cmake', 'bison', 'flex', 'yasm',
                'pkg-config', 'gtk-doc-tools', 'libxv-dev', 'libx11-dev',
                'libpulse-dev', 'python2.7-dev', 'texinfo']


class RedHatBootstraper (UnixBootstraper):

    tool = 'yum install'
    packages = ['']


class WindowsBootstraper (BootstraperBase):
    pass


bootstrapers = {Distro.DEBIAN: DebianBootstraper,
                Distro.REDHAT: RedHatBootstraper,
                Distro.WINDOWS_7: WindowsBootstraper,
                Distro.WINDOWS_VISTA: WindowsBootstraper,
                Distro.WINDOWS_XP: WindowsBootstraper,
                }


class Bootstraper (object):

    def __new__(klass, config):
        distro = config.distro
        if distro not in bootstrapers:
            raise FatalError(_("Not bootstrapper for the distro %s" % distro))
        return bootstrapers[distro]()
