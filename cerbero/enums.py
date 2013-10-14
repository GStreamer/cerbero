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
    ANDROID = 'android'
    IOS = 'ios'


class Architecture:
    ''' Enumeration of supported acrchitectures '''
    X86 = 'x86'
    X86_64 = 'x86_64'
    PPC = 'ppc'
    UNIVERSAL = 'universal'
    ARM = 'arm'
    ARMv7 = 'armv7'


class Distro:
    ''' Enumeration of supported distributions '''
    DEBIAN = 'debian'
    REDHAT = 'redhat'
    SUSE = 'suse'
    WINDOWS = 'windows'
    OS_X = 'osx'
    IOS = 'ios'
    ANDROID = 'android'


class DistroVersion:
    ''' Enumeration of supported distribution versions '''
    DEBIAN_SQUEEZE = 'debian_squeeze'
    DEBIAN_WHEEZY = 'debian_wheezy'
    DEBIAN_JESSIE = 'debian_jessy'
    UBUNTU_MAVERICK = 'ubuntu_maverick'
    UBUNTU_LUCID = 'ubuntu_lucid'
    UBUNTU_NATTY = 'ubuntu_natty'
    UBUNTU_ONEIRIC = 'ubuntu_oneiric'
    UBUNTU_PRECISE = 'ubuntu_precise'
    UBUNTU_QUANTAL = 'ubuntu_quantal'
    UBUNTU_RARING = 'ubuntu_raring'
    UBUNTU_SAUCY = 'ubuntu_saucy'
    FEDORA_16 = 'fedora_16'
    FEDORA_17 = 'fedora_17'
    FEDORA_18 = 'fedora_18'
    FEDORA_19 = 'fedora_19'
    FEDORA_20 = 'fedora_20'
    REDHAT_6 = 'redhat_6'
    OPENSUSE_12_1 = 'opensuse_12_1'
    OPENSUSE_12_2 = 'opensuse_12_2'
    OPENSUSE_12_3 = 'opensuse_12_3'
    WINDOWS_XP = 'windows_xp'
    WINDOWS_VISTA = 'windows_vista'
    WINDOWS_7 = 'windows_7'
    WINDOWS_8 = 'windows_8'
    OS_X_MAVERICKS = 'osx_mavericks'
    OS_X_MOUNTAIN_LION = 'osx_mountain_lion'
    OS_X_LION = 'osx_lion'
    OS_X_SNOW_LEOPARD = 'osx_snow_leopard'
    OS_X_LEOPARD = 'osx_leopard'
    IOS_6_0 = 'ios_6_0'
    IOS_6_1 = 'ios_6_1'
    IOS_7_0 = 'ios_7_0'
    ANDROID_GINGERBREAD = 'android_gingerbread'  # API Level 9
    ANDROID_ICE_CREAM_SANDWICH = 'android_ice_cream_sandwich'  # API Level 14
    ANDROID_JELLY_BEAN = 'android_jelly_bean'  # API Level 16


class LicenseDescription:

    def __init__(self, acronym, pretty_name):
        self.acronym = acronym
        self.pretty_name = pretty_name


class License:
    ''' Enumeration of licensesversions '''
    AFLv2_1 = LicenseDescription('AFL-2.1',
            'Academic Free License, version 2.1')
    Apachev2 = LicenseDescription('Apache-2.0',
            'Apache License, version 2.0')
    BSD = LicenseDescription('BSD',
            'BSD License')
    BSD_like = LicenseDescription('BSD-like',
            'BSD-like License')
    CC_BY_SA = LicenseDescription('CC-BY-SA',
            'Creative Commons Attribution-ShareAlike')
    FreeType = LicenseDescription('FreeType',
            'FreeType License')
    Jasperv2 = LicenseDescription('Jasper-2.0',
            'JasPer LicenseVersion 2.0')
    JPEG = LicenseDescription('JPEG',
            'JasPer LicenseVersion 2.0')
    GFDL = LicenseDescription('GFDL',
            'GNU Free Documentation License')
    GPL = LicenseDescription('GPL',
            'GNU General Public License')
    GPLv1 = LicenseDescription('GPL-1',
            'GNU General Public License, version 1')
    GPLv1Plus = LicenseDescription('GPL-1+',
            'GNU General Public License, version 1 or later')
    GPLv2 = LicenseDescription('GPL-2',
            'GNU General Public License, version 2')
    GPLv2Plus = LicenseDescription('GPL-2+',
            'GNU General Public License, version 2 or later')
    GPLv3 = LicenseDescription('GPL-3',
            'GNU General Public License, version 3')
    GPLv3Plus = LicenseDescription('GPL-3+',
            'GNU General Public License, version 3 or later')
    LGPL = LicenseDescription('LGPL',
            'GNU Lesser General Public License')
    LGPLv2 = LicenseDescription('LGPL-2',
            'GNU Lesser General Public License, version 2')
    LGPLv2Plus = LicenseDescription('LGPL-2+',
            'GNU Lesser General Public License, version 2 or later')
    LGPLv2_1 = LicenseDescription('LGPL-2.1',
            'GNU Lesser General Public License, version 2.1')
    LGPLv2_1Plus = LicenseDescription('LGPL-2.1+',
            'GNU Lesser General Public License, version 2.1 or later')
    LGPLv3 = LicenseDescription('LGPL-3',
            'GNU Lesser General Public License, version 3')
    LGPLv3Plus = LicenseDescription('LGPL-3+',
            'GNU Lesser General Public License, version 3 or later')
    LibPNG = LicenseDescription('LibPNG',
            'LibPNG License')
    MIT = LicenseDescription('MIT',
            'MIT License')
    Proprietary = LicenseDescription('Proprietary',
            'Proprietary License')
