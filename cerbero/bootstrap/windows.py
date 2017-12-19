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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_bootstrapper
from cerbero.config import Architecture, Distro, Platform
from cerbero.errors import ConfigurationError
from cerbero.utils import shell, _, fix_winpath, to_unixpath, git
from cerbero.utils import messages as m

# Toolchain
GCC_VERSION = '4.7.3'
MINGW_DOWNLOAD_SOURCE = 'http://gstreamer.freedesktop.org/data/cerbero/toolchain/windows'
MINGW_TARBALL_TPL = "mingw-%s-gcc-%s-%s-%s.tar.xz"

# Extra dependencies
MINGWGET_DEPS = ['msys-wget', 'msys-flex', 'msys-bison', 'msys-perl']
GNOME_FTP = 'http://ftp.gnome.org/pub/gnome/binaries/win32/'
WINDOWS_BIN_DEPS = ['intltool/0.40/intltool_0.40.4-1_win32.zip']


class WindowsBootstrapper(BootstrapperBase):
    '''
    Bootstrapper for windows builds.
    Installs the mingw-w64 compiler toolchain and headers for Directx
    '''

    def start(self):
        if not git.check_line_endings(self.config.platform):
            raise ConfigurationError("git is configured to use automatic line "
                    "endings conversion. You can fix it running:\n"
                    "$git config core.autocrlf false")
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
        self.remove_mingw_cpp()
        self.add_non_prefixed_strings()
        if self.platform == Platform.WINDOWS:
            # After mingw is beeing installed
            self.install_bin_deps()
        self.install_gl_headers()

    def check_dirs(self):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)
        etc_path = os.path.join(self.config.prefix, 'etc')
        if not os.path.exists(etc_path):
            os.makedirs(etc_path)

    def install_mingw(self):
        tarball = MINGW_TARBALL_TPL % (self.version, GCC_VERSION,
                self.platform, self.arch)

        tarfile = os.path.join(self.prefix, tarball)
        tarfile = os.path.abspath(tarfile)
        shell.download("%s/%s" % (MINGW_DOWNLOAD_SOURCE, tarball), tarfile, check_cert=False)
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

    def install_mingwget_deps(self):
        for dep in MINGWGET_DEPS:
            shell.call('mingw-get install %s' % dep)

    def install_gl_headers(self):
        m.action("Installing wglext.h")
        if self.arch == Architecture.X86:
            inst_path = os.path.join(self.prefix, 'i686-w64-mingw32/include/GL/wglext.h')
        else:
            inst_path = os.path.join(self.prefix, 'x86_64-w64-mingw32/include/GL/wglext.h')
        gl_header = 'http://www.opengl.org/registry/api/GL/wglext.h'
        shell.download(gl_header, inst_path, False, check_cert=False)

    def install_bin_deps(self):
        # FIXME: build intltool as part of the build tools bootstrap
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
            print "Replacing old libdir : ", libdir
            return libdir.strip()[1:-1]

    def remove_mingw_cpp(self):
        # Fixes glib's checks in configure, where cpp -v is called
        # to get some include dirs (which doesn't looks like a good idea).
        # If we only have the host-prefixed cpp, this problem is gone.
        if os.path.exists('/mingw/bin/cpp.exe'):
            shutil.move('/mingw/bin/cpp.exe', '/mingw/bin/cpp.exe.bck')

    def add_non_prefixed_strings(self):
        # libtool m4 macros uses non-prefixed 'strings' command. We need to
        # create a copy here
        if self.config.platform == Platform.WINDOWS:
            ext = '.exe'
        else:
            ext = ''
        if self.config.target_arch == Architecture.X86:
            host = 'i686-w64-mingw32'
        else:
            host = 'x86_64-w64-mingw32'
        bindir = os.path.join(self.config.toolchain_prefix, 'bin')
        p_strings = os.path.join(bindir, '%s-strings%s' % (host, ext))
        strings = os.path.join(bindir, 'strings%s' % ext)
        if os.path.exists(strings):
            os.remove(strings)
        shutil.copy(p_strings, strings)


def register_all():
    register_bootstrapper(Distro.WINDOWS, WindowsBootstrapper)
