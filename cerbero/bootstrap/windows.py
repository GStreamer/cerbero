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
from pathlib import Path

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_bootstrapper
from cerbero.config import Architecture, Distro, Platform
from cerbero.errors import ConfigurationError
from cerbero.utils import shell, _, fix_winpath, to_unixpath, git
from cerbero.utils import messages as m

# Toolchain
GCC_VERSION = '4.7.3'
MINGW_DOWNLOAD_TPL = 'https://gstreamer.freedesktop.org/data/cerbero/toolchain/windows/mingw-%s-gcc-%s-%s-%s.tar.xz'
MINGW_CHECKSUMS = {
    'mingw-w32-gcc-4.7.3-linux-x86.tar.xz': '16a3ad2584f0dc25ec122029143b186c99f362d1be1a77a338431262491004ae',
    'mingw-w64-gcc-4.7.3-linux-x86_64.tar.xz': 'e673536cc89a778043789484f691d7e35458a5d72638dc4b0123f92ecf868592',
    'mingw-w32-gcc-4.7.3-windows-x86.tar.xz': 'da783488ab3a2b28471c13ece97c643f8e8ec774308fb2a01152b23618f13a33',
    'mingw-w64-gcc-4.7.3-windows-x86_64.tar.xz': '820fa7490b3d738b9cf8c360cdd9a7aeb0592510a8ea50486e721b5b92722b08',
}

# MinGW Perl
PERL_VERSION = '5.24.0'
MINGW_PERL_TPL = 'https://sourceforge.net/projects/perl-mingw/files/{0}/perl-{0}-mingw32.zip'
MINGW_PERL_CHECKSUM = '9d4db40959727d43b4ff4b9884f5aebda20292347978036683684c2608c1397b'

# Khronos wglext.h for Windows GL
OPENGL_COMMIT = 'a4b0c7d5d10a8fca5866c6d08a608010843a4b36'
KHRONOS_WGL_TPL = 'https://raw.githubusercontent.com/KhronosGroup/OpenGL-Registry/{}/api/GL/wglext.h'
WGL_CHECKSUM = '8961c809d180e3590fca32053341fe3a83394edcb936f7699f0045feadb16115'

# Extra binary dependencies
GNOME_FTP = 'https://download.gnome.org/binaries/win32/'
WINDOWS_BIN_DEPS = [
    ('intltool/0.40/intltool_0.40.4-1_win32.zip',
     '7180a780cee26c5544c06a73513c735b7c8c107db970b40eb7486ea6c936cb33')]

# MSYS packages needed
MINGWGET_DEPS = ['msys-flex', 'msys-bison', 'msys-perl']

class WindowsBootstrapper(BootstrapperBase):
    '''
    Bootstrapper for windows builds.
    Installs the mingw-w64 compiler toolchain and headers for Directx
    '''

    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline)
        self.prefix = self.config.toolchain_prefix
        self.perl_prefix = self.config.mingw_perl_prefix
        self.platform = self.config.target_platform
        self.arch = self.config.target_arch
        if self.arch == Architecture.X86:
            self.version = 'w32'
        else:
            self.version = 'w64'
        self.platform = self.config.platform
        # Register all network resources this bootstrapper needs. They will all
        # be downloaded into self.config.local_sources
        #
        # MinGW toolchain
        url = MINGW_DOWNLOAD_TPL % (self.version, GCC_VERSION, self.platform, self.arch)
        self.fetch_urls.append((url, MINGW_CHECKSUMS[os.path.basename(url)]))
        self.extract_steps.append((url, True, self.prefix))
        # wglext.h
        url = KHRONOS_WGL_TPL.format(OPENGL_COMMIT)
        self.fetch_urls.append((url, WGL_CHECKSUM))
        inst_path = os.path.join(self.prefix, self.config.host, 'include/GL')
        self.extract_steps.append((url, False, inst_path))
        if self.platform == Platform.WINDOWS:
            # MinGW Perl needed by openssl
            url = MINGW_PERL_TPL.format(PERL_VERSION)
            self.fetch_urls.append((url, MINGW_PERL_CHECKSUM))
            self.extract_steps.append((url, True, self.perl_prefix))
            # Newer versions of binary deps such as intltool. Must be extracted
            # after the MinGW toolchain from above is extracted so that it
            # replaces the older files.
            for dep, checksum in WINDOWS_BIN_DEPS:
                url = GNOME_FTP + dep
                self.fetch_urls.append((url, checksum))
                self.extract_steps.append((url, True, self.prefix))

    def start(self):
        if not git.check_line_endings(self.config.platform):
            raise ConfigurationError("git is configured to use automatic line "
                    "endings conversion. You can fix it running:\n"
                    "$git config core.autocrlf false")
        self.check_dirs()
        self.fix_mingw()
        self.fix_non_prefixed_strings()
        if self.platform == Platform.WINDOWS:
            self.fix_openssl_mingw_perl()
            self.fix_bin_deps()
            # FIXME: This uses the network
            self.install_mingwget_deps()
            self.fix_mingw_unused()

    def check_dirs(self):
        if not os.path.exists(self.perl_prefix):
            os.makedirs(self.perl_prefix)
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)
        etc_path = os.path.join(self.config.prefix, 'etc')
        if not os.path.exists(etc_path):
            os.makedirs(etc_path)

    def fix_mingw(self):
        self.fix_lib_paths()
        if self.arch == Architecture.X86:
            try:
                shutil.rmtree('/mingw/lib')
            except Exception:
                pass

    def fix_openssl_mingw_perl(self):
        '''
        This perl is only used by openssl; we can't use it everywhere else
        because it can't find msys tools, and so perl scripts like autom4te
        fail to run, f.ex., m4. Lucky for us, openssl doesn't use those.
        '''
        # Move perl installation from perl-5.xx.y to perl
        perldir = os.path.join(self.perl_prefix, 'perl-' + PERL_VERSION)
        for d in os.listdir(perldir):
            dest = os.path.join(self.perl_prefix, d)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.move(os.path.join(perldir, d), self.perl_prefix)
        os.rmdir(perldir)

    def install_mingwget_deps(self):
        for dep in MINGWGET_DEPS:
            shell.call('mingw-get install %s' % dep)

    def fix_bin_deps(self):
        # replace /opt/perl/bin/perl in intltool
        files = shell.ls_files(['bin/intltool*'], self.prefix)
        for f in files:
            shell.replace(os.path.join(self.prefix, f),
                          {'/opt/perl/bin/perl': '/bin/perl'})

    def fix_lib_paths(self):
        orig_sysroot = self._find_mingw_sys_root()
        if self.config.platform != Platform.WINDOWS:
            new_sysroot = os.path.join(self.prefix, 'mingw', 'lib')
        else:
            new_sysroot = os.path.join(self.prefix, 'lib')
        lib_path = new_sysroot

        # Replace the old sysroot in all .la files
        for path in [f for f in os.listdir(lib_path) if f.endswith('la')]:
            path = os.path.abspath(os.path.join(lib_path, path))
            shell.replace(path, {orig_sysroot: new_sysroot})

    def _find_mingw_sys_root(self):
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
            print("Replacing old libdir : ", libdir)
            return libdir.strip()[1:-1]

    def fix_mingw_unused(self):
        mingw_get_exe = shutil.which('mingw-get')
        if not mingw_get_exe:
            m.warning('mingw-get not found, are you not using an MSYS shell?')
            return
        msys_mingw_bindir = Path(mingw_get_exe).parent
        # Fixes checks in configure, where cpp -v is called
        # to get some include dirs (which doesn't looks like a good idea).
        # If we only have the host-prefixed cpp, this problem is gone.
        if (msys_mingw_bindir / 'cpp.exe').is_file():
            os.replace(msys_mingw_bindir / 'cpp.exe',
                       msys_mingw_bindir / 'cpp.exe.bck')
        # MSYS's link.exe (for symlinking) overrides MSVC's link.exe (for
        # C linking) in new shells, so rename it. No one uses `link` for
        # symlinks anyway.
        msys_link_exe = shutil.which('link')
        if not msys_link_exe:
            return
        msys_link_exe = Path(msys_link_exe)
        msys_link_bindir = msys_link_exe.parent
        if msys_link_exe.is_file() and 'msys/1.0/bin/link' in msys_link_exe.as_posix():
            os.replace(msys_link_exe, msys_link_bindir / 'link.exe.bck')

    def fix_non_prefixed_strings(self):
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
