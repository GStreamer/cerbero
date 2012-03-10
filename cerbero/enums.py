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


class Platform:
    ''' Enumeration of supported platforms '''
    LINUX = 'linux'
    WINDOWS = 'windows'
    DARWIN = 'darwin'

class Architecture:
    ''' Enumeration of supported acrchitectures '''
    X86 = 'x86'
    X86_64 = 'x86_64'
    PPC = 'ppc'

class Distro:
    ''' Enumeration of supported distributions '''
    DEBIAN = 'debian'
    REDHAT = 'redhat'
    SUSE = 'suse'
    WINDOWS = 'windows'
    OS_X = 'osx'

class DistroVersion:
    ''' Enumeration of supported distribution versions '''
    DEBIAN_SQUEEZE = 'debian_squeeze'
    DEBIAN_WHEEZY = 'debian_wheezy'
    UBUNTU_LUCID = 'ubuntu_lucid'
    UBUNTU_NATTY = 'ubuntu_natty'
    UBUNTU_ONEIRIC = 'ubuntu_oneiric'
    FEDORA_16 = 'fedora_16'
    REDHAT_6 = 'redhat_6'
    OPENSUSE_12_1 = 'opensuse_12_1'
    WINDOWS_XP = 'windows_xp'
    WINDOWS_VISTA = 'windows_vista'
    WINDOWS_7 = 'windows_7'
    OS_X_MOUNTAIN_LION = 'osx_mountain_lion'
    OS_X_LION = 'osx_lion'
    OS_X_SNOW_LEOPARD = 'osx_snow_leopard'
    OS_X_LEOPARD = 'osx_leopard'
