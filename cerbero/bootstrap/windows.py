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
import tempfile

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Architecture, Distro, Platform
from cerbero.utils import shell, _
from cerbero.utils import messages as m


MINGW_DOWNLOAD_SOURCE = {'w32':
'''http://downloads.sourceforge.net/project/mingw-w64/Toolchains%20targetting%20Win32/Automated%20Builds/''',
                         'w64':
'''http://downloads.sourceforge.net/project/mingw-w64/Toolchains%20targetting%20Win64/Automated%20Builds/'''}
MINGW_TARBALL_TPL = "mingw-%s-bin_%s-%s_%s.tar.bz2"
MINGW_W32_i686_LINUX = MINGW_TARBALL_TPL % ('w32', 'i686', 'linux', 20111220)
MINGW_W64_x86_64_LINUX = MINGW_TARBALL_TPL % ('w64', 'x86_64', 'linux', 20111220)
MINGW_W32_i686_WINDOWS = MINGW_TARBALL_TPL % ('w32', 'i686', 'mingw', 20111220)
MINGW_W64_x86_64_WINDOWS = MINGW_TARBALL_TPL % ('w64', 'x86_64', 'mingw', 20111220)
MINGW_SYSROOT = {'w64':
'''/buildslaves/mingw-w64/linux-x86_64-x86_64/build/build/root/x86_64-w64-mingw32/lib/../lib''',
                 'w32':
'''/buildslaves/mingw-w64/linux-x86-x86/build/build/root/i686-w64-mingw32/lib/../lib'''}
W32_x86_64_LINUX_SYSROOT = "/opt/buildbot/linux-x86_64-x86/build/build/root/i686-w64-mingw32/lib"

PTHREADS_URL = \
'''http://downloads.sourceforge.net/project/mingw-w64/External%20binary%20packages%20%28Win64%20hosted%29/pthreads/pthreads-20100604.zip'''

PYTHON_URL = \
'''http://hg.python.org/cpython/raw-file/ccd16ad37544/Include'''


DIRECTX_HEADERS = \
"https://mingw-w64.svn.sourceforge.net/svnroot/mingw-w64/trunk/mingw-w64-headers/direct-x/include"\


SED = "sed -i 's/%s/%s/g' %s"


class WindowsBootstraper(BootstraperBase):
    '''
    Bootstraper for windows builds.
    Installs the mingw-w64 compiler toolchain and headers for Directx and Python
    '''

    def start(self):
        self.prefix = self.config.toolchain_prefix
        self.target_platform = self.config.target_platform
        self.target_arch = self.config.target_arch
        if self.target_arch == Architecture.X86:
            self.version = 'w32'
        else:
            self.version = 'w64'
        self.platform = self.config.platform
        self.check_dirs()
        self.install_mingw()
        self.install_directx_headers()
        self.install_python_headers()
        self.install_pthreads()

    def check_dirs(self):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)

    def install_mingw(self):
        tarball = None
        if self.platform == Platform.LINUX:
            if self.target_arch == Architecture.X86:
                tarball = MINGW_W32_i686_LINUX
            if self.target_arch == Architecture.X86_64:
                tarball = MINGW_W64_x86_64_LINUX
        if self.platform == Platform.WINDOWS:
            if self.target_arch == Architecture.X86:
                tarball = MINGW_W32_i686_WINDOWS
            if self.target_arch == Architecture.X86_64:
                tarball = MINGW_W64_x86_64_WINDOWS

        tarfile = os.path.join(self.prefix, tarball)
        shell.download("%s/%s" % (MINGW_DOWNLOAD_SOURCE[self.version], tarball), tarfile)
        shell.unpack(tarfile, self.prefix)
        self.fix_lib_paths()

    def install_pthreads(self):
        pthreadszip = os.path.join(self.prefix, 'pthreads.zip')
        shell.download(PTHREADS_URL, pthreadszip)
        temp = tempfile.mkdtemp()
        # real pthreads stuff is in a zip file inside the previous zip file
        # under mingwxx/pthreads-xx.zip
        shell.unpack(pthreadszip, temp)
        shell.unpack(os.path.join(temp, 'pthreads-20100604', 'ming%s' % self.version,
                                  'pthreads-%s.zip' % self.version), self.prefix)

    def install_python_headers(self):
        python_headers = os.path.join(self.prefix, 'include', 'Python2.7')
        if not os.path.exists(python_headers):
            os.makedirs(python_headers)
        m.action(_("Installing Python headers"))
        shell.recursive_download(PYTHON_URL, python_headers)

    def install_directx_headers(self):
        directx_headers = os.path.join(self.prefix, 'include', 'DirectX')
        m.action(_("Installing DirectX headers"))
        cmd = "svn checkout --trust-server-cert --non-interactive "\
              "--no-auth-cache %s %s" % (DIRECTX_HEADERS, directx_headers)
        shell.call(cmd)

    def fix_lib_paths(self):

        def escape(s):
            return s.replace('/', '\\/')

        orig_sysroot = MINGW_SYSROOT[self.version]
        if self.target_arch == Architecture.X86:
            new_sysroot = os.path.join(self.prefix, 'i686-w64-mingw32', 'lib')
        else:
            new_sysroot = os.path.join(self.prefix, 'x86_64-w64-mingw32', 'lib')
        lib_path = new_sysroot

        # Replace the old sysroot in all .la files
        for path in [f for f in os.listdir(lib_path) if f.endswith('la')]:
            sed_cmd = SED % (escape(orig_sysroot), escape(new_sysroot),
                             os.path.abspath(os.path.join(lib_path, path)))
            shell.call(sed_cmd)


def register_all():
    register_bootstraper(Distro.WINDOWS, WindowsBootstraper)
