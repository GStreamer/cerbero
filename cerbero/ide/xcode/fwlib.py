#!/usr/bin/env python
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

from cerbero.config import Architecture
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.utils import shell


class FrameworkLibrary(object):
    '''
    Combine several shared library into a single shared library to be used
    as a Framework.
    The complete list of shared libraries needed are guessed with pkg-config
    but full paths can be used too with use_pkgconfig=False
    '''

    def create(self, libname, install_name, libraries, arch,
            use_pkgconfig=True):
        if arch == Architecture.X86:
            arch = 'i386'
        if use_pkgconfig:
            libraries = self._libraries_paths(libraries)
        self._create_framework_library(libname, install_name, libraries, arch)

    def _libraries_paths(self, libraries):
        pkgconfig = PkgConfig(libraries)
        libdirs = pkgconfig.libraries_dirs()
        libs = pkgconfig.libraries()
        libspaths = []
        for lib in libs:
            for libdir in libdirs:
                libpath = os.path.join(libdir, self._get_lib_file_name (lib))
                if not os.path.exists(libpath):
                    continue
                libspaths.append(os.path.realpath(libpath))
                break
        return libspaths

    def _create_framework_library(self, libname, install_name, libraries, arch):
        raise NotImplemented

    def _get_lib_file_name(self, lib):
        return lib


class DynamicFrameworkLibrary(FrameworkLibrary):
    def _create_framework_library(self, libname, install_name, libraries, arch):
        extra_options = self._get_create_framework_options (libname)
        libraries = ' '.join(['-Wl,-reexport_library %s' % x for x in libraries])
        shell.call('gcc -dynamiclib -o %s -arch %s -install_name %s %s' %
                   (libname, arch, install_name, libraries))

    def _get_lib_file_name(self, lib):
        return 'lib%s.dylib' % lib

class StaticFrameworkLibrary(FrameworkLibrary):
    def _get_lib_file_name(self, lib):
        return 'lib%s.a' % lib

    def _create_framework_library(self, libname, install_name, libraries, arch):
        tmpdir = tempfile.mkdtemp()

        for lib in libraries:
            libprefix = os.path.split(lib)[-1].replace('.', '_')
            lib_tmpdir = tempfile.mkdtemp()
            shutil.copy(lib, lib_tmpdir)

            tmplib = os.path.join(lib_tmpdir, os.path.basename(lib))
            shell.call('ar -x %s' % tmplib, lib_tmpdir)

            obj_files = shell.ls_files(['*.o'], lib_tmpdir)
            for obj_f in obj_files:
                shell.call('cp %s %s' % (os.path.join(lib_tmpdir, obj_f), '%s-%s' % (libprefix, obj_f)), tmpdir)
                shell.call('ar -cqS %s %s-%s' % (libname, libprefix, obj_f), tmpdir)
        shell.call('ar -s %s' % (libname), tmpdir)

