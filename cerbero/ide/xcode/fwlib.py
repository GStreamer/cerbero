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
                libpath = os.path.join(libdir, 'lib%s.dylib' % lib)
                if not os.path.exists(libpath):
                    continue
                libspaths.append(os.path.realpath(libpath))
                break
        return libspaths

    def _create_framework_library(self, libname, install_name, libraries, arch):
        libraries = ' '.join(['-Wl,-reexport_library %s' % x for x in libraries])
        shell.call('gcc -dynamiclib -o %s -arch %s -install_name %s %s' %
                   (libname, arch, install_name, libraries))


