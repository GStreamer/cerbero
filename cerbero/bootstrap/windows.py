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
import logging

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Architecture, Distro, Platform
from cerbero.utils import shell, _


MINGW_DOWNLOAD_SOURCE = \
'''http://downloads.sourceforge.net/project/mingw-w64/Toolchains%20targetting%20Win32/Automated%20Builds/'''
MINGW_TARBALL_TPL = "mingw-w32-bin_%s-%s_%s.tar.bz2"
MINGW_W32_i686_LINUX = MINGW_TARBALL_TPL % ('i686', 'linux', 20111220)
MINGW_W64_i686_LINUX = MINGW_TARBALL_TPL % ('x86_64', 'linux', 20111220)
MINGW_W32_i686_WINDOWS = MINGW_TARBALL_TPL % ('i686', 'mingw', 20111220)
MINGW_W64_i686_WINDOWS = MINGW_TARBALL_TPL % ('x86_64', 'mingw', 20111220)
PTHREADS_URL = \
'''ttp://downloads.sourceforge.net/project/mingw-w64/External%20binary%20packages%20%28Win64%20hosted%29/pthreads/pthreads-20100604.zip'''
PYTHON_URL = \
'''http://hg.python.org/cpython/raw-file/ccd16ad37544/Include'''


class WindowsBootstraper(BootstraperBase):
    '''
    Bootstraper for windows builds.
    Installs the mingw-w64 compiler toolchain and headers for Directx and Python
    '''

    def start(self):
        self.prefix = self.config.toolchain_prefix
        self.target_platform = self.config.target_platform
        self.target_arch = self.config.target_arch
        self.platform = self.config.platform
        self.check_dirs()
        self.install_mingw()
        self.install_directx_headers()
        self.install_python_headers()

    def check_dirs(self):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)

    def install_mingw(self):
        tarball = None
        if self.platform == Platform.LINUX:
            if self.target_arch == Architecture.X86:
                tarball = MINGW_W32_i686_LINUX
            if self.target_arch == Architecture.X86_64:
                tarball = MINGW_W64_i686_LINUX
        if self.platform == Platform.WINDOWS:
            if self.target_arch == Architecture.X86:
                tarball = MINGW_W32_i686_WINDOWS
            if self.target_arch == Architecture.X86_64:
                tarball = MINGW_W64_i686_WINDOWS

        tarfile = os.path.join(self.prefix, tarball)
        shell.download("%s/%s" % (MINGW_DOWNLOAD_SOURCE, tarball), tarfile)
        shell.unpack(tarfile, self.prefix)

    def install_pthreads(self):
        pthreadszip = os.path.join(self.prefix, 'pthreads.zip')
        shell.download(MINGW_DOWNLOAD_SOURCE, pthreadszip)
        shell.unpack(pthreadszip)

    def install_python_headers(self):
        python_headers = os.path.join(self.prefix, 'include', 'Python2.7')
        if not os.path.exists(python_headers):
            os.makedirs(python_headers)
        logging.info(_("Installing Python headers"))
        shell.recursive_download(PYTHON_URL, python_headers)

    def install_directx_headers(self):
        directx_headers = os.path.join(self.prefix, 'include', 'DirectX')
        logging.info(_("Installing DirectX headers"))
        cmd = "svn checkout --trust-server-cert --non-interactive "\
              "--no-auth-cache "\
              "https://mingw-w64.svn.sourceforge.net/svnroot/mingw-w64/trunk/mingw-w64-headers/direct-x/include "\
              "%s" % directx_headers
        shell.call(cmd)


def register_all():
    register_bootstraper(Distro.WINDOWS_7, WindowsBootstraper)
    register_bootstraper(Distro.WINDOWS_VISTA, WindowsBootstraper)
    register_bootstraper(Distro.WINDOWS_XP, WindowsBootstraper)
