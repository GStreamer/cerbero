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
    UNIVERSAL = 'universal'
    ARM = 'arm'
    ARMv7 = 'armv7'
    ARMv7S = 'armv7s'
    ARM64 = 'arm64'

    @staticmethod
    def is_arm(arch):
        '''Returns whether the architecture is an ARM based one.
        Note that it will include 32bit *and* 64bit ARM targets. If you
        wish to do something special for 64bit you should first check for
        that before calling this method.'''
        return arch in [Architecture.ARM, Architecture.ARMv7,
                Architecture.ARMv7S, Architecture.ARM64]

    @staticmethod
    def is_arm32(arch):
        return arch in [Architecture.ARM, Architecture.ARMv7, Architecture.ARMv7S]


class Distro:
    ''' Enumeration of supported distributions '''
    DEBIAN = 'debian'
    REDHAT = 'redhat'
    SUSE = 'suse'
    WINDOWS = 'windows'
    ARCH = 'arch'
    OS_X = 'osx'
    IOS = 'ios'
    ANDROID = 'android'
    GENTOO = 'gentoo'
    NONE = 'none'


class DistroVersion:
    ''' Enumeration of supported distribution versions, withing each distro, they must be sortable'''
    DEBIAN_SQUEEZE = 'debian_06_squeeze'
    DEBIAN_WHEEZY = 'debian_07_wheezy'
    DEBIAN_JESSIE = 'debian_08_jessie'
    DEBIAN_STRETCH = 'debian_09_stretch'
    DEBIAN_BUSTER = 'debian_10_buster'
    DEBIAN_BULLSEYE = 'debian_11_bullseye'
    UBUNTU_LUCID = 'ubuntu_10_04_lucid'
    UBUNTU_MAVERICK = 'ubuntu_10_10_maverick'
    UBUNTU_NATTY = 'ubuntu_11_04_natty'
    UBUNTU_ONEIRIC = 'ubuntu_11_10_oneiric'
    UBUNTU_PRECISE = 'ubuntu_12_04_precise'
    UBUNTU_QUANTAL = 'ubuntu_12_10_quantal'
    UBUNTU_RARING = 'ubuntu_13_04_raring'
    UBUNTU_SAUCY = 'ubuntu_13_10_saucy'
    UBUNTU_TRUSTY = 'ubuntu_14_04_trusty'
    UBUNTU_UTOPIC = 'ubuntu_14_10_utopic'
    UBUNTU_VIVID = 'ubuntu_15_04_vivid'
    UBUNTU_WILY = 'ubuntu_15_10_wily'
    UBUNTU_XENIAL = 'ubuntu_16_04_xenial'
    UBUNTU_ARTFUL = 'ubuntu_17_10_artful'
    UBUNTU_BIONIC = 'ubuntu_18_04_bionic'
    UBUNTU_DISCO = 'ubuntu_19_04_disco'
    FEDORA_16 = 'fedora_16'
    FEDORA_17 = 'fedora_17'
    FEDORA_18 = 'fedora_18'
    FEDORA_19 = 'fedora_19'
    FEDORA_20 = 'fedora_20'
    FEDORA_21 = 'fedora_21'
    FEDORA_22 = 'fedora_22'
    FEDORA_23 = 'fedora_23'
    FEDORA_24 = 'fedora_24'
    FEDORA_25 = 'fedora_25'
    FEDORA_26 = 'fedora_26'
    FEDORA_27 = 'fedora_27'
    FEDORA_28 = 'fedora_28'
    FEDORA_29 = 'fedora_29'
    FEDORA_30 = 'fedora_30'
    FEDORA_31 = 'fedora_31'
    REDHAT_6 = 'redhat_6'
    REDHAT_7 = 'redhat_7'
    # Amazon Linux seems to be RedHat/CentOS-based
    AMAZON_LINUX = 'amazon_linux'
    ARCH_ROLLING = 'rolling'
    GENTOO_VERSION = 'gentoo-version'
    OPENSUSE_42_2 = 'opensuse_42_2'
    OPENSUSE_42_3 = 'opensuse_42_3'
    OPENSUSE_TUMBLEWEED = 'tumbleweed'
    WINDOWS_XP = 'windows_xp'
    WINDOWS_VISTA = 'windows_vista'
    WINDOWS_7 = 'windows_07'
    WINDOWS_8 = 'windows_08'
    WINDOWS_8_1 = 'windows_08_1'
    WINDOWS_10 = 'windows_10'
    OS_X_MAVERICKS = 'osx_mavericks'
    OS_X_MOUNTAIN_LION = 'osx_mountain_lion'
    OS_X_YOSEMITE = 'osx_yosemite'
    OS_X_EL_CAPITAN = 'osx_el_capitan'
    OS_X_SIERRA = 'osx_sierra'
    OS_X_HIGH_SIERRA = 'osx_high_sierra'
    OS_X_MOJAVE = 'osx_mojave'
    OS_X_CATALINA = 'osx_catalina'
    IOS_8_0 = 'ios_08_0'
    IOS_8_1 = 'ios_08_1'
    IOS_8_2 = 'ios_08_2'
    IOS_8_3 = 'ios_08_3'
    IOS_8_4 = 'ios_08_4'
    IOS_9_0 = 'ios_09_0'
    IOS_9_1 = 'ios_09_1'
    IOS_9_2 = 'ios_09_2'
    IOS_9_3 = 'ios_09_3'
    IOS_10_0 = 'ios_10_0'
    IOS_10_1 = 'ios_10_1'
    IOS_10_2 = 'ios_10_2'
    IOS_10_3 = 'ios_10_3'
    IOS_11_0 = 'ios_11_0'
    IOS_11_1 = 'ios_11_1'
    IOS_11_2 = 'ios_11_2'
    IOS_11_3 = 'ios_11_3'
    IOS_11_4 = 'ios_11_4'
    IOS_12_0 = 'ios_12_0'
    IOS_12_1 = 'ios_12_1'
    IOS_12_2 = 'ios_12_2'
    IOS_12_3 = 'ios_12_3'
    IOS_12_4 = 'ios_12_4'
    # further ios versions are generated automatically
    ANDROID_GINGERBREAD = 'android_09_gingerbread'  # API Level 9
    ANDROID_ICE_CREAM_SANDWICH = 'android_14_ice_cream_sandwich'  # API Level 14
    ANDROID_JELLY_BEAN = 'android_16_jelly_bean'  # API Level 16
    ANDROID_KITKAT = 'android_19_kitkat'  # API Level 19
    ANDROID_LOLLIPOP = 'android_21_lollipop' # API Level 21
    ANDROID_MARSHMALLOW = 'android_23_marshmallow' # API Level 23
    ANDROID_NOUGAT = 'android_24_nougat' # API Level 24
    NONE_UCLIBC = 'none_uclibc'
    NONE_GLIBC = 'none_glibc'

    @staticmethod
    def get_android_api_version(version):
        '''Returns the corresponding android api version'''
        if version == DistroVersion.ANDROID_GINGERBREAD:
            return 9
        elif version == DistroVersion.ANDROID_ICE_CREAM_SANDWICH:
            return 14
        elif version == DistroVersion.ANDROID_JELLY_BEAN:
            return 16
        elif version == DistroVersion.ANDROID_KITKAT:
            return 19
        elif version == DistroVersion.ANDROID_LOLLIPOP:
            return 21
        elif version == DistroVersion.ANDROID_MARSHMALLOW:
            return 23
        elif version == DistroVersion.ANDROID_NOUGAT:
            return 24
        else:
            raise FatalError("DistroVersion not supported")

    @staticmethod
    def get_ios_sdk_version(version):
        if not version.startswith('ios_'):
            raise FatalError('Not an iOS version: ' + version)
        return [int(s) for s in version[4:].split('_')]

class LicenseDescription:

    def __init__(self, acronym, pretty_name):
        self.acronym = acronym
        self.pretty_name = pretty_name

    def __lt__(self, other):
        return self.acronym < other.acronym

    def __repr__(self):
        return "LicenseDescription(%s)" % self.acronym

class License:
    ''' Enumeration of licensesversions '''
    Apachev2 = LicenseDescription('Apache-2.0',
            'Apache License, version 2.0')
    BSD = LicenseDescription('BSD',
            'BSD License')
    BSD_like = LicenseDescription('BSD-like',
            'BSD-like License')
    FreeType = LicenseDescription('FreeType',
            'FreeType License')
    GPLv2Plus = LicenseDescription('GPL-2+',
            'GNU General Public License, version 2 or later')
    GPLv3Plus = LicenseDescription('GPL-3+',
            'GNU General Public License, version 3 or later')
    LGPLv2Plus = LicenseDescription('LGPL-2+',
            'GNU Lesser General Public License, version 2 or later')
    LGPLv2_1Plus = LicenseDescription('LGPL-2.1+',
            'GNU Lesser General Public License, version 2.1 or later')
    LGPLv3Plus = LicenseDescription('LGPL-3+',
            'GNU Lesser General Public License, version 3 or later')
    LibPNG = LicenseDescription('LibPNG',
            'LibPNG License')
    MPLv1_1 = LicenseDescription('MPL-1.1',
            'Mozilla Public License Version 1.1')
    MPLv2 = LicenseDescription('MPL-2',
            'Mozilla Public License Version 2.0')
    MIT = LicenseDescription('MIT',
            'MIT License')
    OPENSSL = LicenseDescription('OpenSSL',
            'OpenSSL License')
    Proprietary = LicenseDescription('Proprietary',
            'Proprietary License')
    Misc = LicenseDescription('Misc',
            'Miscellaneous license information')

class LibraryType:
    NONE = 'none'
    STATIC = 'static'
    SHARED = 'shared'
    BOTH = 'both'
