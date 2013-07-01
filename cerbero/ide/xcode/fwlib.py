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
from collections import defaultdict

from cerbero.config import Architecture
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.utils import shell
from cerbero.utils import messages as m


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

        # object files with the same name in an archive are overwritten
        # when they are extracted. osx's ar does not support the N count
        # modifier so after extracting all the files we remove them from
        # the archive to extract those with duplicated names.
        # eg:
        # ar t libavcodec.a -> mlpdsp.o mlpdsp.o (2 objects with the same name)
        # ar d libavcodec.a mlpdsp.o (we remove the first one)
        # ar t libavcodec.a -> mlpdsp.o (we only the second one now)
        files = shell.check_call('ar -t %s' % tmplib, lib_tmpdir).split('\n')
        # FIXME: We should use collections.Count but it's only available in
        # python 2.7+
        dups = defaultdict(int)
        for f in files:
            dups[f] += 1
        for f in dups:
            if dups[f] <= 1:
                continue
            for x in range(dups[f]):
                path = os.path.join(lib_tmpdir, f)
                new_path = os.path.join(lib_tmpdir, 'dup%d_' % x + f)
                # The duplicated overwrote the first one, so extract it again
                shell.call('ar -x %s %s' % (tmplib, f), lib_tmpdir)
                shutil.move (path, new_path)
                shell.call('ar -d %s %s' % (tmplib, f), lib_tmpdir)

        return lib_tmpdir

    def _check_duplicated_symbols(self, files, tmpdir):
        for f in files:
            syms = defaultdict(list)
            symbols = shell.check_call('nm -UA %s' % f, tmpdir).split('\n')
            # nm output is: test.o: 00000000 T _gzwrite
            # (filename, address, symbol type, symbols_name)
            for s in symbols:
                s = s.split(' ')
                if len(s) == 4 and s[2] == 'T':
                    syms[s[3]].append(s)
            dups = {}
            for k,v in syms.iteritems():
                if len(v) > 1:
                    dups[k] = v
            if dups:
                m.warning ("The static library contains duplicated symbols")
            for k, v in dups.iteritems():
                m.message (k)  # symbol name
                for l in v:
                    m.message ("     %s" % l[0])  # file

    def _create_framework_library(self, libraries):
        tmpdir = tempfile.mkdtemp()

        libname = os.path.basename (self.libname) # just to make sure

        if self.arch == Architecture.UNIVERSAL:
            archs = self.universal_archs
        else:
            archs = [self.arch]

        archs = [a if a != Architecture.X86 else 'i386' for a in archs]

        for thin_arch in archs:
            object_files_md5 = []
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
                    obj_path = os.path.join(lib_tmpdir, obj_f)
                    md5 = shell.check_call('md5 -q %s' % obj_path).split('\n')[0]
                    md5 = '%s-%s' % (md5, os.path.getsize(obj_path))
                    if md5 not in object_files_md5:
                        shell.call('cp %s %s' % (obj_path, '%s-%s' % (libprefix, obj_f)), tmpdir_thinarch)
                        shell.call('ar -cqS %s %s-%s' % (libname, libprefix, obj_f), tmpdir_thinarch)
                        object_files_md5.append(md5)
            shell.call('ar -s %s' % (libname), tmpdir_thinarch)

        files = [os.path.join(tmpdir, arch, libname) for arch in archs]
        self._check_duplicated_symbols(files, tmpdir)
        if len(archs) > 1:
            #merge the final libs into a fat file again
            shell.call('lipo %s -create -output %s' % (' '.join(files), self.install_name), tmpdir)
        else:
            shell.call('cp %s %s' % (os.path.join(tmpdir, self.arch, libname), self.install_name), tmpdir)

