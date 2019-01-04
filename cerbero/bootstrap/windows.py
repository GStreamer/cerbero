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
TOOLCHAIN_BASE_URL = 'https://gstreamer.freedesktop.org/data/cerbero/toolchain/windows/'
TOOLCHAIN_PLATFORM = {
    Platform.LINUX: ('mingw-6.0.0-gcc-8.2.0-linux-multilib.tar.xz',
        '396ceb50161720b19971e2c71c87ce08150213b091ed8ffc00782df8759921bf'),
    Platform.WINDOWS: ('mingw-6.0.0-gcc-8.2.0-windows-multilib.tar.xz',
        '77fc1319b13894d7340d4994150e3af615e23a63113a9947412d11be95f4d8a9'),
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
        self.platform = self.config.platform
        # Register all network resources this bootstrapper needs. They will all
        # be downloaded into self.config.local_sources
        #
        # MinGW toolchain
        filename, checksum = TOOLCHAIN_PLATFORM[self.config.platform]
        url = TOOLCHAIN_BASE_URL + filename
        self.fetch_urls.append((url, checksum))
        self.extract_steps.append((url, True, self.prefix))
        # wglext.h
        url = KHRONOS_WGL_TPL.format(OPENGL_COMMIT)
        self.fetch_urls.append((url, WGL_CHECKSUM))
        sysroot = os.path.join(self.prefix,
                'x86_64-w64-mingw32/sysroot/usr/x86_64-w64-mingw32')
        gl_inst_path = os.path.join(sysroot, 'include/GL/')
        self.extract_steps.append((url, False, gl_inst_path))
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
        if self.arch == Architecture.X86:
            try:
                shutil.rmtree('/mingw/lib')
            except Exception:
                pass
        if self.platform == Platform.WINDOWS:
            # Tar does not create correctly the mingw symlink
            sysroot = os.path.join(self.prefix, 'x86_64-w64-mingw32/sysroot')
            mingwdir = os.path.join(sysroot, 'mingw')
            # The first time the toolchain is extracted it creates a file with
            # symlink
            if not os.path.isdir(mingwdir):
                os.remove(mingwdir)
            # Otherwise we simply remove the directory and link back the sysroot
            else:
                shutil.rmtree(mingwdir)
            shell.call('ln -s usr/x86_64-w64-mingw32 mingw', sysroot)
            # In cross-compilation gcc does not create a prefixed cpp
            cpp_exe = os.path.join(self.prefix, 'bin', 'cpp.exe')
            host_cpp_exe = os.path.join(self.prefix, 'bin', 'x86_64-w64-mingw32-cpp.exe')
            shutil.copyfile(cpp_exe, host_cpp_exe)

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


def register_all():
    register_bootstrapper(Distro.WINDOWS, WindowsBootstrapper)
