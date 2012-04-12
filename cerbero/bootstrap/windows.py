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
MINGW_TARBALL_TPL = "mingw-%s-bin_%s-%s_%s.%s"
MINGW_W32_i686_LINUX = MINGW_TARBALL_TPL % ('w32', 'i686', 'linux', 20111220, 'tar.bz2')
MINGW_W64_i686_LINUX = MINGW_TARBALL_TPL % ('w64', 'i686', 'linux', 20111220, 'tar.bz2')
MINGW_W32_i686_WINDOWS = MINGW_TARBALL_TPL % ('w32', 'i686', 'mingw', 20111219, 'zip')
MINGW_W64_x86_64_WINDOWS = MINGW_TARBALL_TPL % ('w64', 'i686', 'mingw', 20111220, 'zip')
MINGW_SYSROOT = {'w64':
'''/hdd/m64bs/linux-x86-x86_64/build/build/root/x86_64-w64-mingw32/lib/../lib''',
                 'w32':
'''/buildslaves/mingw-w64/linux-x86-x86/build/build/root/i686-w64-mingw32/lib/../lib'''}

PTHREADS_URL = \
'''http://downloads.sourceforge.net/project/mingw-w64/External%20binary%20packages%20%28Win64%20hosted%29/pthreads/pthreads-20100604.zip'''

PYTHON_URL = \
'''http://hg.python.org/cpython/raw-file/ccd16ad37544/Include'''

DIRECTX_HEADERS = \
"https://mingw-w64.svn.sourceforge.net/svnroot/mingw-w64/trunk/mingw-w64-headers/direct-x/include"\

MINGWGET_DEPS = ['msys-wget']

SVN = 'http://downloads.sourceforge.net/project/win32svn/1.7.2/svn-win32-1.7.2.zip'

WINDOWS_BIN_DEPS = [
                    'http://ftp.gnome.org/pub/gnome/binaries/win32/glib/2.28/glib_2.28.8-1_win32.zip',
                    'http://ftp.gnome.org/pub/gnome/binaries/win32/dependencies/gettext-runtime_0.18.1.1-2_win32.zip',
                    'http://ftp.gnome.org/pub/gnome/binaries/win32/dependencies/pkg-config-dev_0.26-1_win32.zip',
                    'http://ftp.gnome.org/pub/gnome/binaries/win32/dependencies/pkg-config_0.26-1_win32.zip']

GL_HEADERS = ["http://cgit.freedesktop.org/mesa/mesa/plain/include/GL/gl.h",
              "http://www.opengl.org/registry/api/glext.h"]

GENDEF = 'http://mingw-w64.svn.sourceforge.net/viewvc/mingw-w64/trunk/mingw-w64-tools/gendef/?view=tar'

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
        if self.platform == Platform.WINDOWS:
            # For wget
            self.install_mingwget_deps()
        self.install_mingw()
        if self.platform == Platform.WINDOWS:
            # After mingw is beeing installed
            self.install_bin_deps()
        self.install_directx_headers()
        self.install_gl_headers()
        self.install_python_sdk()
        self.install_pthreads()
        self.install_gendef()

    def check_dirs(self):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)
        etc_path = os.path.join(self.config.prefix, 'etc')
        if not os.path.exists(etc_path):
            os.makedirs(etc_path)

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
                tarball = MINGW_W64_x86_64_WINDOWS

        tarfile = os.path.join(self.prefix, tarball)
        shell.download("%s%s" % (MINGW_DOWNLOAD_SOURCE[self.version], tarball), tarfile)
        shell.unpack(tarfile, self.prefix)
        self.fix_lib_paths()

    def install_gendef(self):
        gendeftar = os.path.join(self.prefix, 'gendef.tar.gz')
        shell.download(GENDEF, gendeftar)
        temp = tempfile.mkdtemp()
        shell.unpack(gendeftar, temp)
        if self.platform != Platform.WINDOWS:
            sudo = 'sudo'
        else:
            sudo = ''
        shell.call('CC=gcc ./configure; make; %s make install' % sudo,
                os.path.join(temp, 'gendef'))

    def install_pthreads(self):
        pthreadszip = os.path.join(self.prefix, 'pthreads.zip')
        shell.download(PTHREADS_URL, pthreadszip)
        temp = tempfile.mkdtemp()
        # real pthreads stuff is in a zip file inside the previous zip file
        # under mingwxx/pthreads-xx.zip
        shell.unpack(pthreadszip, temp)
        shell.unpack(os.path.join(temp, 'pthreads-20100604', 'ming%s' % self.version,
                                  'pthreads-%s.zip' % self.version), self.prefix)

    def install_python_sdk(self):
        m.action(_("Installing Python headers"))
        temp = tempfile.mkdtemp()
        shell.call("git clone %s" % os.path.join(self.config.git_root,
                                                 'windows-external-sdk'),
                   temp)

        python_headers = os.path.join(self.prefix, 'include', 'Python2.7')
        if not os.path.exists(python_headers):
            os.makedirs(python_headers)
        python_libs = os.path.join(self.prefix, 'lib')

        shell.call('cp -f %s/windows-external-sdk/python27/%s/include/* %s' %
                  (temp, self.version, python_headers))
        shell.call('cp -f %s/windows-external-sdk/python27/%s/lib/* %s' %
                  (temp, self.version, python_libs))

    def install_directx_headers(self):
        m.action(_("Installing DirectX headers"))
        directx_headers = os.path.join(self.prefix, 'include', 'DirectX')
        cmd = "svn checkout --trust-server-cert --non-interactive "\
              "--no-auth-cache %s %s" % (DIRECTX_HEADERS, directx_headers)
        shell.call(cmd)

    def install_mingwget_deps(self):
        for dep in MINGWGET_DEPS:
            shell.call('mingw-get install %s' % dep)

    def install_bin_deps(self):
        # On windows, we need to install first wget than SVN, for the DirectX headers,
        # and pkg-config. pkg-config can't be installed otherwise because it depends
        # on glib and glib depends on pkg-config
        for url in WINDOWS_BIN_DEPS:
            temp = tempfile.mkdtemp()
            path = os.path.join(temp, 'download.zip')
            shell.download(url, path)
            shell.unpack(path, self.config.toolchain_prefix)
        temp = tempfile.mkdtemp()
        path = os.path.join(temp, 'download.zip')
        shell.download(SVN, path)
        shell.unpack(path, temp)
        dirpath = os.path.join(temp, os.path.splitext(os.path.split(SVN)[1])[0])
        shell.call('cp -r %s/* %s' % (dirpath, self.config.toolchain_prefix))

    def install_gl_headers(self):
        m.action(_("Installing OpenGL headers"))
        gl_path = "%s/include/GL" % (self.prefix)
        if not os.path.exists(gl_path):
            os.mkdir(gl_path)
        wget = 'wget %s -O %s'
        for h in GL_HEADERS:
            cmd = wget % (h, "%s/%s" % (gl_path, os.path.basename(h)))
            shell.call(cmd)

    def fix_lib_paths(self):
        orig_sysroot = MINGW_SYSROOT[self.version]
        if self.target_arch == Architecture.X86:
            new_sysroot = os.path.join(self.prefix, 'i686-w64-mingw32', 'lib')
        else:
            new_sysroot = os.path.join(self.prefix, 'x86_64-w64-mingw32', 'lib')
        lib_path = new_sysroot

        # Replace the old sysroot in all .la files
        for path in [f for f in os.listdir(lib_path) if f.endswith('la')]:
            self.replace(orig_sysroot, new_sysroot,
                         os.path.abspath(os.path.join(lib_path, path)))

    def replace(self, orig, replacement, filepath):
        with open(filepath, 'r') as f:
            content = f.read()
        content.replace(orig, replacement)
        with open(filepath, 'w+') as f:
            f.write(content)


def register_all():
    register_bootstraper(Distro.WINDOWS, WindowsBootstraper)
