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
try:
    import sysconfig
except:
    from distutils import sysconfig
import gettext
import platform as pplatform

from cerbero.enums import Platform, Architecture, Distro, DistroVersion
from cerbero.errors import FatalError

_ = gettext.gettext
N_ = lambda x: x


class ArgparseArgument(object):

    def __init__(self, name, **kwargs):
        self.name = name
        self.args = kwargs

    def add_to_parser(self, parser):
        parser.add_argument(self.name, **self.args)


def user_is_root():
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
            arch = Architecture.X86
        else:
            raise FatalError(_("Architecture %s not supported") % arch)

    # Get the distro info
    if platform == Platform.LINUX:
        d = pplatform.linux_distribution()
        if d[0] in ['Ubuntu', 'debian']:
            distro = Distro.DEBIAN
            if d[2] == 'lucid':
                distro_version = DistroVersion.UBUNTU_LUCID
            if d[2] == 'natty':
                distro_version = DistroVersion.UBUNTU_NATTY
            elif d[2] == 'oneiric':
                distro_version = DistroVersion.UBUNTU_ONEIRIC
            elif d[1].startswith('6.'):
                distro_version = DistroVersion.DEBIAN_SQUEEZE
            elif d[1].startswith('7.') or d[1].startswith('wheezy'):
                distro_version = DistroVersion.DEBIAN_WHEEZY
            else:
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0] in ['RedHat', 'Fedora']:
            distro = Distro.REDHAT
            # FIXME Fill this
            raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0] in ['openSUSE']:
            distro = Distro.SUSE
            # FIXME Fill this
            raise FatalError("Distribution '%s' not supported" % str(d))
        else:
            raise FatalError("Distribution '%s' not supported" % str(d))
    elif platform == Platform.WINDOWS:
        distro = Distro.WINDOWS
        win32_ver = platform.win32_ver()
        dmap = {'xp': DistroVersion.WINDOWS_XP, 'vista': DistroVersion.WINDOWS_VISTA, '7': DistroVersion.WINDOWS_7}
        if win32_ver in dmap:
            distro_version = dmap[win32_ver]
        else:
            raise FatalError("Windows version '%s' not supported" % win32_ver)
    elif platform == Platform.DARWIN:
        distro = Distro.OS_X
        ver = pplatform.mac_ver()[0]
        if ver.startswith('10.7'):
            distro_version = DistroVersion.OS_X_LION
        elif ver.startswith('10.6'):
            distro_version = DistroVersion.OS_X_LEOPARD
        else:
            raise FatalError("Mac version %s not supported" % ver)

    return platform, arch, distro, distro_version
