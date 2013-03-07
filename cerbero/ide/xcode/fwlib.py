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

    def __init__(self, libname, install_name, libraries, arch):
        self.libname = libname
        self.install_name = install_name
        self.libraries = libraries
        self.arch = arch
        self.use_pkgconfig = True
        self.universal_archs = None

    def create(self):
        if self.arch == Architecture.X86:
            self.arch = 'i386'
        if self.use_pkgconfig:
            libraries = self._libraries_paths(self.libraries)
        else:
            libraries = self.libraries

        self._create_framework_library(libraries)

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

    def _create_framework_library(self, libraries):
        raise NotImplemented

    def _get_lib_file_name(self, lib):
        return lib


class DynamicFrameworkLibrary(FrameworkLibrary):
    def _create_framework_library(self, libraries):
        libraries = ' '.join(['-Wl,-reexport_library %s' % x for x in libraries])
        shell.call('gcc -dynamiclib -o %s -arch %s -install_name %s %s' %
                   (self.libname, self.arch, self.install_name, libraries))

    def _get_lib_file_name(self, lib):
        return 'lib%s.dylib' % lib

class StaticFrameworkLibrary(FrameworkLibrary):
    def _get_lib_file_name(self, lib):
        return 'lib%s.a' % lib

    def _split_static_lib(self, lib, thin_arch=None):
        '''Splits the static lib @lib into its object files

           Splits the static lib @lib into its object files and returns
           a new temporary directory where the .o files should be found.

           if @thin_arch was provided, it considers the @lib to be a fat
           binary and takes its thin version for the @thin_arch specified
           before retrieving the object files.
        '''
        lib_tmpdir = tempfile.mkdtemp()
        shutil.copy(lib, lib_tmpdir)
        tmplib = os.path.join(lib_tmpdir, os.path.basename(lib))

        if thin_arch: #should be a fat file, split only to the arch we want
            newname = '%s_%s' % (thin_arch, os.path.basename(lib))
            shell.call('lipo %s -thin %s -output %s' % (tmplib,
                           thin_arch, newname), lib_tmpdir)
            tmplib = os.path.join (lib_tmpdir, newname)

        shell.call('ar -x %s' % tmplib, lib_tmpdir)
        return lib_tmpdir

    def _create_framework_library(self, libraries):
        tmpdir = tempfile.mkdtemp()

        libname = os.path.basename (self.libname) # just to make sure

        if self.arch == Architecture.UNIVERSAL:
            archs = self.universal_archs
        else:
            archs = [self.arch]

        archs = [a if a != Architecture.X86 else 'i386' for a in archs]

        for thin_arch in archs:
            shell.call ('mkdir -p %s' % thin_arch, tmpdir)
            tmpdir_thinarch = os.path.join(tmpdir, thin_arch)

            for lib in libraries:
                libprefix = os.path.split(lib)[-1].replace('.', '_')

                if len(archs) > 1: #should be a fat file, split only to the arch we want
                    libprefix += '_%s_' % thin_arch
                    lib_tmpdir = self._split_static_lib(lib, thin_arch)
                else:
                    lib_tmpdir = self._split_static_lib(lib)

                obj_files = shell.ls_files(['*.o'], lib_tmpdir)
                for obj_f in obj_files:
                    shell.call('cp %s %s' % (os.path.join(lib_tmpdir, obj_f), '%s-%s' % (libprefix, obj_f)), tmpdir_thinarch)
                    shell.call('ar -cqS %s %s-%s' % (libname, libprefix, obj_f), tmpdir_thinarch)
            shell.call('ar -s %s' % (libname), tmpdir_thinarch)

        if len(archs) > 1:
            #merge the final libs into a fat file again
            shell.call('lipo %s -create -output %s' % (' '.join([os.path.join(tmpdir, arch, libname) for arch in archs]), self.install_name), tmpdir)
        else:
            shell.call('cp %s %s' % (os.path.join(tmpdir, self.arch, libname), self.install_name), tmpdir)

