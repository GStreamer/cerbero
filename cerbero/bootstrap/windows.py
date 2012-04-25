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
from cerbero.utils import shell, _, fix_winpath
from cerbero.utils import messages as m

# Toolchain
MINGW_DOWNLOAD_SOURCE = 'http://keema.collabora.co.uk'
MINGW_TARBALL_TPL = "mingw-%s-%s-%s.tar.xz"
MINGW_SYSROOT = '/home/andoni/mingw/%s/%s/lib'

# Extra dependencies
MINGWGET_DEPS = ['msys-wget']
SVN = 'http://downloads.sourceforge.net/project/win32svn/1.7.2/svn-win32-1.7.2.zip'
GNOME_FTP = 'http://ftp.gnome.org/pub/gnome/binaries/win32/'
WINDOWS_BIN_DEPS = [
    'glib/2.28/glib_2.28.8-1_win32.zip',
    'intltool/0.40/intltool_0.40.4-1_win32.zip',
    'dependencies/gettext-runtime_0.18.1.1-2_win32.zip',
    'dependencies/pkg-config-dev_0.26-1_win32.zip',
    'dependencies/pkg-config_0.26-1_win32.zip']
PTHREADS_URL = \
'''http://downloads.sourceforge.net/project/mingw-w64/External%20binary%20packages%20%28Win64%20hosted%29/pthreads/pthreads-20100604.zip'''


class WindowsBootstraper(BootstraperBase):
    '''
    Bootstraper for windows builds.
    Installs the mingw-w64 compiler toolchain and headers for Directx and Python
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
        shell.download("%s/%s" % (MINGW_DOWNLOAD_SOURCE, tarball), tarfile)
        shell.unpack(tarfile, self.prefix)
        self.fix_lib_paths()

    def install_pthreads(self):
        pthreadszip = os.path.join(self.prefix, 'pthreads.zip')
        shell.download(PTHREADS_URL, pthreadszip)
        temp = fix_winpath(tempfile.mkdtemp())
        # real pthreads stuff is in a zip file inside the previous zip file
        # under mingwxx/pthreads-xx.zip
        shell.unpack(pthreadszip, temp)
        shell.unpack(os.path.join(temp, 'pthreads-20100604', 'ming%s' % self.version,
                                  'pthreads-%s.zip' % self.version), self.prefix)

    def install_python_sdk(self):
        m.action(_("Installing Python headers"))
        temp = fix_winpath(tempfile.mkdtemp())
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
        # install svn (skipped as it's not needed anymore for now)
        temp = fix_winpath(tempfile.mkdtemp())
        path = os.path.join(temp, 'download.zip')
        shell.download(SVN, path)
        shell.unpack(path, temp)
        dirpath = os.path.join(temp, os.path.splitext(os.path.split(SVN)[1])[0])
        shell.call('cp -r %s/* %s' % (dirpath, self.config.toolchain_prefix))


def register_all():
    register_bootstraper(Distro.WINDOWS, WindowsBootstraper)
