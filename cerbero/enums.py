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
from cerbero.errors import FatalError


# Safest place to define this since this file imports very few modules
CERBERO_VERSION = '1.28.0'


if sys.version_info >= (3, 11) and 'CI' in os.environ:
    _pyproject = os.path.join(__file__, '..', 'pyproject.toml')
    if os.path.exists(_pyproject):
        import tomllib

        with open(_pyproject, 'r', encoding='utf-8') as f:
            d = tomllib.loads(f.read())
            if d['project']['version'] != CERBERO_VERSION:
                raise FatalError("cerbero/enums.py:CERBERO_VERSION doesn't match version in pyproject.toml")


class Platform:
    """Enumeration of supported platforms"""

    LINUX = 'linux'
    WINDOWS = 'windows'
    DARWIN = 'darwin'
    ANDROID = 'android'
    IOS = 'ios'

    def is_apple(platform):
        return platform in (Platform.DARWIN, Platform.IOS)

    def is_mobile(platform):
        return platform in (Platform.ANDROID, Platform.IOS)

    def is_apple_mobile(platform):
        return platform == Platform.IOS


class Architecture:
    """Enumeration of supported acrchitectures"""

    X86 = 'x86'
    X86_64 = 'x86_64'
    UNIVERSAL = 'universal'
    ARM = 'arm'
    ARMv7 = 'armv7'
    ARMv7S = 'armv7s'
    ARM64 = 'arm64'

    @staticmethod
    def is_arm(arch):
        """Returns whether the architecture is an ARM based one.
        Note that it will include 32bit *and* 64bit ARM targets. If you
        wish to do something special for 64bit you should first check for
        that before calling this method."""
        return arch in [Architecture.ARM, Architecture.ARMv7, Architecture.ARMv7S, Architecture.ARM64]

    @staticmethod
    def is_arm32(arch):
        return arch in [Architecture.ARM, Architecture.ARMv7, Architecture.ARMv7S]


class Distro:
    """Enumeration of supported distributions"""

    DEBIAN = 'debian'
    REDHAT = 'redhat'
    SUSE = 'suse'
    WINDOWS = 'windows'  # To be used as target_distro
    MSYS = 'msys'  # When running on a native Windows with MSYS
    MSYS2 = 'msys2'  # When running on a native Windows with MSYS2
    ARCH = 'arch'
    OS_X = 'osx'
    IOS = 'ios'
    ANDROID = 'android'
    GENTOO = 'gentoo'
    NONE = 'none'


class DistroVersion:
    """Enumeration of supported distribution versions, withing each distro, they must be sortable"""

    DEBIAN_SQUEEZE = 'debian_06_squeeze'
    DEBIAN_WHEEZY = 'debian_07_wheezy'
    DEBIAN_JESSIE = 'debian_08_jessie'
    DEBIAN_STRETCH = 'debian_09_stretch'
    DEBIAN_BUSTER = 'debian_10_buster'
    DEBIAN_BULLSEYE = 'debian_11_bullseye'
    DEBIAN_SID = 'debian_99_sid'
    # further debian versions are generated automatically
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
    UBUNTU_COSMIC = 'ubuntu_18_10_cosmic'
    UBUNTU_DISCO = 'ubuntu_19_04_disco'
    UBUNTU_EOAN = 'ubuntu_19_10_eoan'
    UBUNTU_FOCAL = 'ubuntu_20_04_focal'
    # fedora versions are generated automatically, like:
    # FEDORA_32 = 'fedora_32'
    REDHAT_6 = 'redhat_6'
    REDHAT_7 = 'redhat_7'
    # further RedHat versions are generated automatically, like:
    # REDHAT_8_1 = 'redhat_8.1'
    AMAZON_LINUX_2023 = 'amazonlinux_2023'
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
    WINDOWS_11 = 'windows_11'
    OS_X_MAVERICKS = 'osx_mavericks'
    OS_X_MOUNTAIN_LION = 'osx_mountain_lion'
    OS_X_YOSEMITE = 'osx_yosemite'
    OS_X_EL_CAPITAN = 'osx_el_capitan'
    OS_X_SIERRA = 'osx_sierra'
    OS_X_HIGH_SIERRA = 'osx_high_sierra'
    OS_X_MOJAVE = 'osx_mojave'
    OS_X_CATALINA = 'osx_catalina'
    OS_X_BIG_SUR = 'osx_big_sur'
    # further osx versions are generated automatically
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
    ANDROID_LOLLIPOP = 'android_21_lollipop'  # API Level 21
    ANDROID_LOLLIPOP_MR1 = 'android_22_lollipop_mr1'  # API Level 22
    ANDROID_MARSHMALLOW = 'android_23_marshmallow'  # API Level 23
    ANDROID_NOUGAT = 'android_24_nougat'  # API Level 24
    ANDROID_NOUGAT_MR1 = 'android_25_nougat_mr1'  # API Level 25
    ANDROID_OREO = 'android_26_oreo'  # API Level 26
    ANDROID_OREO_MR1 = 'android_27_oreo_mr1'  # API Level 27
    ANDROID_PIE = 'android_28_pie'  # API Level 28
    ANDROID_Q = 'android_29_q'  # API Level 29
    NONE_UCLIBC = 'none_uclibc'
    NONE_GLIBC = 'none_glibc'

    @staticmethod
    def get_android_api_version(version):
        """Returns the corresponding android api version"""
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
        elif version == DistroVersion.ANDROID_LOLLIPOP_MR1:
            return 22
        elif version == DistroVersion.ANDROID_MARSHMALLOW:
            return 23
        elif version == DistroVersion.ANDROID_NOUGAT:
            return 24
        elif version == DistroVersion.ANDROID_NOUGAT_MR1:
            return 25
        elif version == DistroVersion.ANDROID_OREO:
            return 26
        elif version == DistroVersion.ANDROID_OREO_MR1:
            return 27
        elif version == DistroVersion.ANDROID_PIE:
            return 28
        elif version == DistroVersion.ANDROID_Q:
            return 29
        else:
            raise FatalError('DistroVersion not supported')

    @staticmethod
    def get_ios_sdk_version(version):
        if not version.startswith('ios_'):
            raise FatalError('Not an iOS version: ' + version)
        return [int(s) for s in version[4:].split('_')]


class Subsystem:
    """Enumeration of supported subsystem names, matching Meson:
    https://mesonbuild.com/Reference-tables.html#subsystem-names-since-120"""

    MACOS = 'macos'
    IOS = 'ios'
    IOS_SIMULATOR = 'ios-simulator'


class LicenseDescription:
    def __init__(self, acronym, pretty_name):
        self.acronym = acronym
        self.pretty_name = pretty_name

    def __lt__(self, other):
        return self.acronym < other.acronym

    def __repr__(self):
        return 'LicenseDescription(%s)' % self.acronym


class License:
    """Enumeration of licensesversions.
    Acronyms were sourced from https://spdx.org/licenses/.
    Matches were checked against https://packages.msys2.org and with https://formulae.brew.sh/ as fallback.
    """

    Apachev2 = LicenseDescription('Apache-2.0', 'Apache License, version 2.0')
    BSD_1_Clause = LicenseDescription('BSD 1-Clause License', 'BSD 1-Clause License')
    BSD_2_Clause = LicenseDescription('BSD-2-Clause', 'BSD 2-Clause "Simplified" License')
    BSD_2_Clause_Patent = LicenseDescription('BSD-2-Clause-Patent', 'BSD-2-Clause Plus Patent License')
    BSD_3_Clause = LicenseDescription('BSD-3-Clause', 'BSD 3-Clause "New" or "Revised" License')
    BSD_3_Clause_Clear = LicenseDescription('BSD-3-Clause-Clear', 'BSD 3-Clause Clear License')
    BSD_3_Clause_FLEX = LicenseDescription('BSD-3-Clause-flex', 'BSD 3-Clause Flex variant')
    BSD_like = LicenseDescription('BSD-like', 'BSD-like License')
    BZIP2_1_0_6 = LicenseDescription('bzip2-1.0.6', 'bzip2 and libbzip2 License v1.0.6')
    FreeType = LicenseDescription('FTL', 'FreeType License')
    GPLv2Plus = LicenseDescription('GPL-2.0-or-later', 'GNU General Public License, version 2 or later')
    GPLv3Plus = LicenseDescription('GPL-3.0-or-later', 'GNU General Public License, version 3 or later')
    ISC = LicenseDescription('ISC', 'ISC License')
    LGPLv2Plus = LicenseDescription('LGPL-2.0-or-later', 'GNU Lesser General Public License, version 2 or later')
    LGPLv2_1Plus = LicenseDescription('LGPL-2.1-or-later', 'GNU Lesser General Public License, version 2.1 or later')
    LGPLv3 = LicenseDescription('LGPL-3.0-only', 'GNU Lesser General Public License, version 3')
    LGPLv3Plus = LicenseDescription('LGPL-3.0-or-later', 'GNU Lesser General Public License, version 3 or later')
    Libjpeg = LicenseDescription(
        'IJG AND Zlib AND BSD-3-Clause',
        'Independent JPEG Group License and zlib License and BSD 3-Clause "New" or "Revised" License',
    )
    LibPNG = LicenseDescription('Libpng', 'LibPNG License')
    Libtiff = LicenseDescription('libtiff', 'libtiff License')
    MPLv1_1 = LicenseDescription('MPL-1.1', 'Mozilla Public License Version 1.1')
    MPLv2 = LicenseDescription('MPL-2.0', 'Mozilla Public License Version 2.0')
    MIT = LicenseDescription('MIT', 'MIT License')
    # winpthreads
    MIT_AND_BSD_Clause_Clear = LicenseDescription('MIT AND BSD-3-Clause-Clear', 'MIT and BSD 3-Clause Clear License')
    OPENSSL = LicenseDescription('OpenSSL', 'OpenSSL License')
    CURL = LicenseDescription('curl', 'cURL License')
    Proprietary = LicenseDescription('LicenseRef-Proprietary', 'Proprietary License')
    Sqlite = LicenseDescription('blessing', 'SQLite Blessing')
    Zlib = LicenseDescription('Zlib', 'zlib License')
    ZPL_2_1 = LicenseDescription('ZPL-2.1', 'Zope Public License 2.1')
    Misc = LicenseDescription('Misc', 'Miscellaneous license information')


class LibraryType:
    NONE = 'none'
    STATIC = 'static'
    SHARED = 'shared'
    BOTH = 'both'


class Symbolication:
    SKIP = 'skip'
    MANUAL = 'manual'
