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
import shutil

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Architecture, Distro, Platform
from cerbero.utils import shell, _, fix_winpath, to_unixpath
from cerbero.utils import messages as m

# Toolchain
MINGW_DOWNLOAD_SOURCE = 'http://www.freedesktop.org/software/gstreamer-sdk/'\
                        'data/packages/2012.5/windows/toolchain'
MINGW_TARBALL_TPL = "mingw-%s-%s-%s.tar.xz"

# Extra dependencies
MINGWGET_DEPS = ['msys-wget']
GNOME_FTP = 'http://ftp.gnome.org/pub/gnome/binaries/win32/'
WINDOWS_BIN_DEPS = ['intltool/0.40/intltool_0.40.4-1_win32.zip']
PTHREADS_URL = \
'''http://downloads.sourceforge.net/project/mingw-w64/External%20binary%20\
packages%20%28Win64%20hosted%29/pthreads/pthreads-20100604.zip'''


class WindowsBootstraper(BootstraperBase):
    '''
    Bootstraper for windows builds.
    Installs the mingw-w64 compiler toolchain and headers for Directx and
    Python
    '''

    def start(self):
        self.prefix = self.config.toolchain_prefix
        self.platform = self.config.target_platform
        self.arch = self.config.target_arch
        if self.arch == Architecture.X86:
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
        self.install_python_sdk()
        self.install_pthreads()

    def check_dirs(self):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)
        etc_path = os.path.join(self.config.prefix, 'etc')
        if not os.path.exists(etc_path):
            os.makedirs(etc_path)

    def install_mingw(self):
        tarball = MINGW_TARBALL_TPL % (self.version, self.platform,
                self.arch)

        tarfile = os.path.join(self.prefix, tarball)
        tarfile = to_unixpath(os.path.abspath(tarfile))
        shell.download("%s/%s" % (MINGW_DOWNLOAD_SOURCE, tarball), tarfile)
        try:
            shell.unpack(tarfile, self.prefix)
        except Exception:
            pass
        self.fix_lib_paths()
        if self.arch == Architecture.X86:
            try:
                shutil.rmtree('/mingw/lib')
            except Exception:
                pass

    def install_pthreads(self):
        pthreadszip = os.path.join(self.prefix, 'pthreads.zip')
        shell.download(PTHREADS_URL, pthreadszip)
        temp = fix_winpath(os.path.abspath(tempfile.mkdtemp()))
        # real pthreads stuff is in a zip file inside the previous zip file
        # under mingwxx/pthreads-xx.zip
        shell.unpack(pthreadszip, temp)
        shell.unpack(os.path.join(temp, 'pthreads-20100604',
            'ming%s' % self.version, 'pthreads-%s.zip' % self.version),
            self.prefix)

    def install_python_sdk(self):
        m.action(_("Installing Python headers"))
        temp = tempfile.mkdtemp()
        shell.call("git clone %s" % os.path.join(self.config.git_root,
                                                 'windows-external-sdk.git'),
                   temp)

        python_headers = os.path.join(self.prefix, 'include', 'Python2.7')
        python_headers = to_unixpath(os.path.abspath(python_headers))

        shell.call('mkdir -p %s' % python_headers)
        python_libs = os.path.join(self.prefix, 'lib')
        python_libs = to_unixpath(python_libs)

        temp = to_unixpath(os.path.abspath(temp))
        shell.call('cp -f %s/windows-external-sdk/python27/%s/include/* %s' %
                  (temp, self.version, python_headers))
        shell.call('cp -f %s/windows-external-sdk/python27/%s/lib/* %s' %
                  (temp, self.version, python_libs))
        pydll = '%s/lib/python.dll' % self.prefix
        try:
            os.remove(pydll)
        except:
            pass
        shell.call('ln -s python27.dll %s' % (pydll))

    def install_mingwget_deps(self):
        for dep in MINGWGET_DEPS:
            shell.call('mingw-get install %s' % dep)

    def install_bin_deps(self):
        # On windows, we need to install first wget and pkg-config.
        # pkg-config can't be installed otherwise because it depends
        # on glib and glib depends on pkg-config
        for url in WINDOWS_BIN_DEPS:
            temp = fix_winpath(tempfile.mkdtemp())
            path = os.path.join(temp, 'download.zip')
            shell.download(GNOME_FTP + url, path)
            shell.unpack(path, self.config.toolchain_prefix)
        # replace /opt/perl/bin/perl in intltool
        files = shell.ls_files(['bin/intltool*'], self.config.toolchain_prefix)
        for f in files:
            shell.replace(os.path.join(self.config.toolchain_prefix, f),
                          {'/opt/perl/bin/perl': '/bin/perl'})
        return

    def fix_lib_paths(self):
        orig_sysroot = self.find_mingw_sys_root()
        if self.config.platform != Platform.WINDOWS:
            new_sysroot = os.path.join(self.prefix, 'mingw', 'lib')
        else:
            new_sysroot = os.path.join(self.prefix, 'lib')
        lib_path = new_sysroot

        # Replace the old sysroot in all .la files
        for path in [f for f in os.listdir(lib_path) if f.endswith('la')]:
            path = os.path.abspath(os.path.join(lib_path, path))
            shell.replace(path, {orig_sysroot: new_sysroot})

    def find_mingw_sys_root(self):
        if self.config.platform != Platform.WINDOWS:
            f = os.path.join(self.prefix, 'mingw', 'lib', 'libstdc++.la')
        else:
            f = os.path.join(self.prefix, 'lib', 'libstdc++.la')
        with open(f, 'r') as f:
            # get the "libdir=/path" line
            libdir = [x for x in f.readlines() if x.startswith('libdir=')][0]
            # get the path
            libdir = libdir.split('=')[1]
            # strip the surrounding quotes
            print libdir
            return libdir.strip()[1:-1]


def register_all():
    register_bootstraper(Distro.WINDOWS, WindowsBootstraper)
