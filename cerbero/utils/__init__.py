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

import os
import sys
import sysconfig
import gettext
import platform as pplatform

from cerbero.enums import Platform, Architecture, Distro
from cerbero.errors import FatalError

_ = gettext.gettext
N_ = lambda x: x


class ArgparseArgument(object):

    def __init__ (self, name, **kwargs):
        self.name = name
        self.args = kwargs

    def add_to_parser (self, parser):
        parser.add_argument (self.name, **self.args)


def user_is_root ():
        ''' Check if the user running the process is root '''
        return hasattr(os, 'getuid') and os.getuid() == 0


def system_info():
    '''
    Get the sysem information.
    Return a tuple with the platform type, the architecture and the
    distribution
    '''

    # Get the platform info
    platform = sys.platform
    if platform.startswith('win'):
        platform = Platform.WINDOWS
    elif platform.startswith('darwin'):
        platform = Platform.DARWIN
    elif platform.startswith('linux'):
        platform = Platform.LINUX
    else:
        raise FatalError(_("Platform %s not supported") % platform)

    # Get the architecture info
    if platform == Platform.WINDOWS:
        platform_str = sysconfig.get_platform()
        if platform_str in ['win-amd64', 'win-ia64']:
            arch = Architecture.X86_64
        else:
            arch = Architecture.X86
    else:
        uname = os.uname()
        arch = uname[4]
        if arch == 'x86_64':
            arch = Architecture.X86_64
        elif arch.endswith('86'):
            arch == Architecture.X86

    # Get the distro info
    if platform == Platform.LINUX:
        distro = pplatform.linux_distribution()[0]
        if distro in ['Ubuntu', 'Debian']:
            distro = Distro.DEBIAN
        elif distro in ['RedHat', 'Fedora']:
            distro = Distro.REDHAT
    if platform == Platform.WINDOWS:
        distro = platform.win32_ver()[0]
        dmap = {'xp': Distro.WINDOWS_XP, 'vista': Distro.WINDOWS_VISTA,
                '7': Distro.WINDOWS_7}
        if distro in dmap:
            distro = dmap[distro]
        else:
            raise FatalError ("Windows version '%s' not supported" % distro)
    if platform == Platform.DARWIN:
        raise NotImplemented()

    return platform, arch, distro
