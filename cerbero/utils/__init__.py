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
import shutil
import sys
try:
    import sysconfig
except:
    from distutils import sysconfig
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from lxml import etree
from distutils.version import StrictVersion
import gettext
import platform as pplatform
import re
import asyncio
from pathlib import Path
from collections.abc import Iterable

from cerbero.enums import Platform, Architecture, Distro, DistroVersion
from cerbero.errors import FatalError
from cerbero.utils import messages as m

_ = gettext.gettext
N_ = lambda x: x


class ArgparseArgument(object):

    def __init__(self, *name, **kwargs):
        self.name = name
        self.args = kwargs

    def add_to_parser(self, parser):
        parser.add_argument(*self.name, **self.args)


def user_is_root():
        ''' Check if the user running the process is root '''
        return hasattr(os, 'getuid') and os.getuid() == 0


def determine_num_of_cpus():
    ''' Number of virtual or logical CPUs on this system '''

    # Python 2.6+
    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except (ImportError, NotImplementedError):
        return 1


def to_winpath(path):
    if path.startswith('/'):
        path = '%s:%s' % (path[1], path[2:])
    return path.replace('/', '\\')


def to_unixpath(path):
    if path[1] == ':':
        path = '/%s%s' % (path[0], path[2:])
    return path


def to_winepath(path):
        path = path.replace('/', '\\\\')
        # wine maps the filesystem root '/' to 'z:\'
        path = 'z:\\%s' % path
        return path


def fix_winpath(path):
    return path.replace('\\', '/')


def windows_arch():
    """
    Detecting the 'native' architecture of Windows is not a trivial task. We
    cannot trust that the architecture that Python is built for is the 'native'
    one because you can run 32-bit apps on 64-bit Windows using WOW64 and
    people sometimes install 32-bit Python on 64-bit Windows.
    """
    # These env variables are always available. See:
    # https://msdn.microsoft.com/en-us/library/aa384274(VS.85).aspx
    # https://blogs.msdn.microsoft.com/david.wang/2006/03/27/howto-detect-process-bitness/
    arch = os.environ.get('PROCESSOR_ARCHITEW6432', '').lower()
    if not arch:
        # If this doesn't exist, something is messing with the environment
        try:
            arch = os.environ['PROCESSOR_ARCHITECTURE'].lower()
        except KeyError:
            raise FatalError(_('Unable to detect Windows architecture'))
    return arch

def system_info():
    '''
    Get the sysem information.
    Return a tuple with the platform type, the architecture and the
    distribution
    '''
    # Get the platform info
    platform = os.environ.get('OS', '').lower()
    if not platform:
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
        arch = windows_arch()
        if arch in ('x64', 'amd64'):
            arch = Architecture.X86_64
        elif arch == 'x86':
            arch = Architecture.X86
        else:
            raise FatalError(_("Windows arch %s is not supported") % arch)
    else:
        uname = os.uname()
        arch = uname[4]
        if arch == 'x86_64':
            arch = Architecture.X86_64
        elif arch.endswith('86'):
            arch = Architecture.X86
        elif arch.startswith('armv7'):
            arch = Architecture.ARMv7
        elif arch.startswith('arm'):
            arch = Architecture.ARM
        else:
            raise FatalError(_("Architecture %s not supported") % arch)

    # Get the distro info
    if platform == Platform.LINUX:
        d = pplatform.linux_distribution()

        if d[0] == '' and d[1] == '' and d[2] == '':
            if os.path.exists('/etc/arch-release'):
                # FIXME: the python2.7 platform module does not support Arch Linux.
                # Mimic python3.4 platform.linux_distribution() output.
                d = ('arch', 'Arch', 'Linux')
            elif os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    if 'ID="amzn"\n' in f.readlines():
                        d = ('RedHat', 'amazon', '')
                    else:
                        f.seek(0, 0)
                        for line in f:
                            # skip empty lines and comment lines
                            if line.strip() and not line.lstrip().startswith('#'):
                                k,v = line.rstrip().split("=")
                                if k == 'NAME':
                                    name = v.strip('"')
                                elif k == 'VERSION_ID':
                                    version = v.strip('"')
                        d = (name, version, '');

        if d[0] in ['Ubuntu', 'debian', 'LinuxMint']:
            distro = Distro.DEBIAN
            if d[2] in ['maverick', 'isadora']:
                distro_version = DistroVersion.UBUNTU_MAVERICK
            elif d[2] in ['lucid', 'julia']:
                distro_version = DistroVersion.UBUNTU_LUCID
            elif d[2] in ['natty', 'katya']:
                distro_version = DistroVersion.UBUNTU_NATTY
            elif d[2] in ['oneiric', 'lisa']:
                distro_version = DistroVersion.UBUNTU_ONEIRIC
            elif d[2] in ['precise', 'maya']:
                distro_version = DistroVersion.UBUNTU_PRECISE
            elif d[2] in ['quantal', 'nadia']:
                distro_version = DistroVersion.UBUNTU_QUANTAL
            elif d[2] in ['raring', 'olivia']:
                distro_version = DistroVersion.UBUNTU_RARING
            elif d[2] in ['saucy', 'petra']:
                distro_version = DistroVersion.UBUNTU_SAUCY
            elif d[2] in ['trusty', 'qiana', 'rebecca']:
                distro_version = DistroVersion.UBUNTU_TRUSTY
            elif d[2] in ['utopic']:
                distro_version = DistroVersion.UBUNTU_UTOPIC
            elif d[2] in ['vivid']:
                distro_version = DistroVersion.UBUNTU_VIVID
            elif d[2] in ['wily']:
                distro_version = DistroVersion.UBUNTU_WILY
            elif d[2] in ['xenial', 'sarah', 'serena', 'sonya', 'sylvia']:
                distro_version = DistroVersion.UBUNTU_XENIAL
            elif d[2] in ['artful']:
                distro_version = DistroVersion.UBUNTU_ARTFUL
            elif d[2] in ['bionic', 'tara', 'tessa']:
                distro_version = DistroVersion.UBUNTU_BIONIC
            elif d[2] in ['cosmic']:
                distro_version = DistroVersion.UBUNTU_COSMIC
            elif d[2] in ['disco']:
                distro_version = DistroVersion.UBUNTU_DISCO
            elif d[1].startswith('6.'):
                distro_version = DistroVersion.DEBIAN_SQUEEZE
            elif d[1].startswith('7.') or d[1].startswith('wheezy'):
                distro_version = DistroVersion.DEBIAN_WHEEZY
            elif d[1].startswith('8.') or d[1].startswith('jessie'):
                distro_version = DistroVersion.DEBIAN_JESSIE
            elif d[1].startswith('9.') or d[1].startswith('stretch'):
                distro_version = DistroVersion.DEBIAN_STRETCH
            elif d[1].startswith('10.') or d[1].startswith('buster'):
                distro_version = DistroVersion.DEBIAN_BUSTER
            elif d[1].startswith('11.') or d[1].startswith('bullseye'):
                distro_version = DistroVersion.DEBIAN_BULLSEYE
            else:
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0] in ['RedHat', 'Fedora', 'CentOS', 'Red Hat Enterprise Linux Server', 'CentOS Linux']:
            distro = Distro.REDHAT
            if d[1] == '16':
                distro_version = DistroVersion.FEDORA_16
            elif d[1] == '17':
                distro_version = DistroVersion.FEDORA_17
            elif d[1] == '18':
                distro_version = DistroVersion.FEDORA_18
            elif d[1] == '19':
                distro_version = DistroVersion.FEDORA_19
            elif d[1] == '20':
                distro_version = DistroVersion.FEDORA_20
            elif d[1] == '21':
                distro_version = DistroVersion.FEDORA_21
            elif d[1] == '22':
                distro_version = DistroVersion.FEDORA_22
            elif d[1] == '23':
                distro_version = DistroVersion.FEDORA_23
            elif d[1] == '24':
                distro_version = DistroVersion.FEDORA_24
            elif d[1] == '25':
                distro_version = DistroVersion.FEDORA_25
            elif d[1] == '26':
                distro_version = DistroVersion.FEDORA_26
            elif d[1] == '27':
                distro_version = DistroVersion.FEDORA_27
            elif d[1] == '28':
                distro_version = DistroVersion.FEDORA_28
            elif d[1] == '29':
                distro_version = DistroVersion.FEDORA_29
            elif d[1] == '30':
                distro_version = DistroVersion.FEDORA_30
            elif d[1] == '31':
                distro_version = DistroVersion.FEDORA_31
            elif d[1].startswith('6.'):
                distro_version = DistroVersion.REDHAT_6
            elif d[1].startswith('7.'):
                distro_version = DistroVersion.REDHAT_7
            elif d[1] == 'amazon':
                distro_version = DistroVersion.AMAZON_LINUX
            else:
                # FIXME Fill this
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0].strip() in ['openSUSE']:
            distro = Distro.SUSE
            if d[1] == '42.2':
                distro_version = DistroVersion.OPENSUSE_42_2
            elif d[1] == '42.3':
                distro_version = DistroVersion.OPENSUSE_42_3
            else:
                # FIXME Fill this
                raise FatalError("Distribution OpenSuse '%s' "
                                 "not supported" % str(d))
        elif d[0].strip() in ['openSUSE Tumbleweed']:
            distro = Distro.SUSE
            distro_version = DistroVersion.OPENSUSE_TUMBLEWEED
        elif d[0].strip() in ['arch']:
            distro = Distro.ARCH
            distro_version = DistroVersion.ARCH_ROLLING
        elif d[0].strip() in ['Gentoo Base System']:
            distro = Distro.GENTOO
            distro_version = DistroVersion.GENTOO_VERSION
        else:
            raise FatalError("Distribution '%s' not supported" % str(d))
    elif platform == Platform.WINDOWS:
        distro = Distro.WINDOWS
        win32_ver = pplatform.win32_ver()[0]
        dmap = {'xp': DistroVersion.WINDOWS_XP,
                'vista': DistroVersion.WINDOWS_VISTA,
                '7': DistroVersion.WINDOWS_7,
                'post2008Server': DistroVersion.WINDOWS_8,
                '8': DistroVersion.WINDOWS_8,
                'post2012Server': DistroVersion.WINDOWS_8_1,
                '8.1': DistroVersion.WINDOWS_8_1,
                '10': DistroVersion.WINDOWS_10}
        if win32_ver in dmap:
            distro_version = dmap[win32_ver]
        else:
            raise FatalError("Windows version '%s' not supported" % win32_ver)
    elif platform == Platform.DARWIN:
        distro = Distro.OS_X
        ver = pplatform.mac_ver()[0]
        if ver.startswith('10.15'):
            distro_version = DistroVersion.OS_X_CATALINA
        elif ver.startswith('10.14'):
            distro_version = DistroVersion.OS_X_MOJAVE
        elif ver.startswith('10.13'):
            distro_version = DistroVersion.OS_X_HIGH_SIERRA
        elif ver.startswith('10.12'):
            distro_version = DistroVersion.OS_X_SIERRA
        elif ver.startswith('10.11'):
            distro_version = DistroVersion.OS_X_EL_CAPITAN
        elif ver.startswith('10.10'):
            distro_version = DistroVersion.OS_X_YOSEMITE
        elif ver.startswith('10.9'):
            distro_version = DistroVersion.OS_X_MAVERICKS
        elif ver.startswith('10.8'):
            distro_version = DistroVersion.OS_X_MOUNTAIN_LION
        else:
            raise FatalError("Mac version %s not supported" % ver)

    num_of_cpus = determine_num_of_cpus()

    return platform, arch, distro, distro_version, num_of_cpus


def validate_packager(packager):
    # match packager in the form 'Name <email>'
    expr = r'(.*\s)*[<]([a-zA-Z0-9+_\-\.]+@'\
        '[0-9a-zA-Z][.-0-9a-zA-Z]*.[a-zA-Z]+)[>]$'
    return bool(re.match(expr, packager))


def copy_files(origdir, destdir, files, extensions, target_platform):
    for f in files:
        f = f % extensions
        install_dir = os.path.dirname(os.path.join(destdir, f))
        if not os.path.exists(install_dir):
            os.makedirs(install_dir)
        if destdir[1] == ':':
            # windows path
            relprefix = to_unixpath(destdir)[2:]
        else:
            relprefix = destdir[1:]
        orig = os.path.join(origdir, relprefix, f)
        dest = os.path.join(destdir, f)
        m.action("copying %s to %s" % (orig, dest))
        try:
            shutil.copy(orig, dest)
        except IOError:
            m.warning("Could not copy %s to %s" % (orig, dest))


def remove_list_duplicates(seq):
    ''' Remove list duplicates maintaining the order '''
    seen = set()
    seen_add = seen.add
    return [x for x in seq if x not in seen and not seen_add(x)]


def parse_file(filename, dict):
    if '__file__' not in dict:
        dict['__file__'] = filename
    try:
        exec(compile(open(filename).read(), filename, 'exec'), dict)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        raise ex


def escape_path(path):
    path = path.replace('\\', '/')
    path = path.replace('(', '\\\(').replace(')', '\\\)')
    path = path.replace(' ', '\\\\ ')
    return path


def get_wix_prefix():
    if 'WIX' in os.environ:
        wix_prefix = os.path.join(os.environ['WIX'], 'bin')
    else:
        wix_prefix = 'C:/Program Files%s/Windows Installer XML v3.5/bin'
        if not os.path.exists(wix_prefix):
            wix_prefix = wix_prefix % ' (x86)'
    if not os.path.exists(wix_prefix):
        raise FatalError("The required packaging tool 'WiX' was not found")
    return escape_path(to_unixpath(wix_prefix))

def add_system_libs(config, new_env, old_env=None):
    '''
    Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
    can be found.
    '''
    arch = config.target_arch
    libdir = 'lib'

    if arch == Architecture.X86_64:
        if config.distro == Distro.REDHAT or config.distro == Distro.SUSE:
            libdir = 'lib64'

    sysroot = '/'
    if config.sysroot:
        sysroot = config.sysroot

    if not old_env:
        old_env = os.environ

    search_paths = []
    if old_env.get('PKG_CONFIG_LIBDIR', None):
       search_paths += [old_env['PKG_CONFIG_LIBDIR']]
    search_paths += [
        os.path.join(sysroot, 'usr', libdir, 'pkgconfig'),
        os.path.join(sysroot, 'usr/share/pkgconfig')]

    if config.target_distro == Distro.DEBIAN:
        host = None
        if arch == Architecture.ARM:
            host = 'arm-linux-gnueabi'
        elif arch == Architecture.ARM64:
            host = 'aarch64-linux-gnu'
        elif arch == Architecture.X86:
            host = 'i386-linux-gnu'
        elif Architecture.is_arm(arch):
            host = 'arm-linux-gnueabihf'
        else:
            host = '%s-linux-gnu' % arch

        search_paths.append(os.path.join(sysroot, 'usr/lib/%s/pkgconfig' % host))

    new_env['PKG_CONFIG_PATH'] = ':'.join(search_paths)

    search_paths = [os.environ.get('ACLOCAL_PATH', ''),
        os.path.join(sysroot, 'usr/share/aclocal')]
    new_env['ACLOCAL_PATH'] = ':'.join(search_paths)

def needs_xcode8_sdk_workaround(config):
    '''
    Returns whether the XCode 8 clock_gettime, mkostemp, getentropy workaround
    from https://bugzilla.gnome.org/show_bug.cgi?id=772451 is needed

    These symbols are only available on macOS 10.12+ and iOS 10.0+
    '''
    if config.target_platform == Platform.DARWIN:
        if StrictVersion(config.min_osx_sdk_version) < StrictVersion('10.12'):
            return True
    elif config.target_platform == Platform.IOS:
        if StrictVersion(config.ios_min_version) < StrictVersion('10.0'):
            return True
    return False

def _qmake_or_pkgdir(qmake):
    qmake_path = Path(qmake)
    if not qmake_path.is_file():
        m.warning('QMAKE={!r} does not exist'.format(str(qmake_path)))
        return (None, None)
    pkgdir = (qmake_path.parent.parent / 'lib/pkgconfig')
    if pkgdir.is_dir():
        return (pkgdir.as_posix(), qmake_path.as_posix())
    return (None, qmake_path.as_posix())

def detect_qt5(platform, arch, is_universal):
    '''
    Returns both the path to the pkgconfig directory and the path to qmake:
    (pkgdir, qmake). If `pkgdir` could not be found, it will be None

    Returns (None, None) if nothing was found.
    '''
    path = None
    qt5_prefix = os.environ.get('QT5_PREFIX', None)
    qmake_path = os.environ.get('QMAKE', None)
    if not qt5_prefix and not qmake_path:
        return (None, None)
    if qt5_prefix and not os.path.isdir(qt5_prefix):
        m.warning('QT5_PREFIX={!r} does not exist'.format(qt5_prefix))
        return (None, None)
    if qmake_path:
        if is_universal and platform == Platform.ANDROID:
            if not qt5_prefix:
                m.warning('Please set QT5_PREFIX if you want to build '
                          'the Qt5 plugin for android-universal')
                return (None, None)
        else:
            ret = _qmake_or_pkgdir(qmake_path)
            if ret != (None, None) or not qt5_prefix:
                return ret
    # qmake path is invalid, find pkgdir or qmake from qt5 prefix
    if platform == Platform.ANDROID:
        if arch == Architecture.ARMv7:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'android_armv7/bin/qmake'))
        elif arch == Architecture.ARM64:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'android_arm64_v8a/bin/qmake'))
        elif arch == Architecture.X86:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'android_x86/bin/qmake'))
        elif arch == Architecture.X86_64:
            # Qt binaries do not ship a qmake for android_x86_64
            return (None, None)
    elif platform == Platform.DARWIN:
        if arch == Architecture.X86_64:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'clang_64/bin/qmake'))
    elif platform == Platform.IOS:
        ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'ios/bin/qmake'))
    elif platform == Platform.LINUX:
        if arch == Architecture.X86_64:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'gcc_64/bin/qmake'))
    elif platform == Platform.WINDOWS:
        # There are several msvc and mingw toolchains to pick from, and we
        # can't pick it for the user.
        m.warning('You must set QMAKE instead of QT5_PREFIX on Windows')
        return (None, None)
    if ret == (None, None):
        m.warning('Unsupported arch {!r} on platform {!r}'.format(arch, platform))
    return ret

# asyncio.Semaphore classes set their working event loop internally on
# creation, so we need to ensure the proper loop has already been set by then.
# This is especially important if we create global semaphores that are
# initialized at the very beginning, since on Windows, the default
# SelectorEventLoop is not available.
def CerberoSemaphore(value=1):
    get_event_loop() # this ensures the proper event loop is already created
    return asyncio.Semaphore(value)

def get_event_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # On Windows the default SelectorEventLoop is not available:
    # https://docs.python.org/3.5/library/asyncio-subprocess.html#windows-event-loop
    if sys.platform == 'win32' and \
       not isinstance(loop, asyncio.ProactorEventLoop):
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)

    return loop

def run_until_complete(tasks):
    loop = get_event_loop()

    if isinstance(tasks, Iterable):
        loop.run_until_complete(asyncio.gather(*tasks))
    else:
        loop.run_until_complete(tasks)
