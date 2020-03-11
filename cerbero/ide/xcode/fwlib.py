#!/usr/bin/env python3
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
import sys
import tempfile
import shutil
import subprocess
import asyncio
import collections
from collections import defaultdict

from cerbero.config import Distro, Architecture
from cerbero.errors import FatalError
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.utils import shell, run_tasks, run_until_complete
from cerbero.utils import messages as m


class FrameworkLibrary(object):
    '''
    Combine several shared library into a single shared library to be used
    as a Framework.
    The complete list of shared libraries needed are guessed with pkg-config
    but full paths can be used too with use_pkgconfig=False
    '''

    def __init__(self, min_version, target, libname, install_name, libraries, arch, env=None):
        self.libname = libname
        self.min_version = min_version
        self.target = target
        self.install_name = install_name
        self.libraries = libraries
        self.arch = arch
        self.use_pkgconfig = True
        self.universal_archs = None
        self.env = env.copy() if env else os.environ.copy()

    def create(self):
        if self.arch == Architecture.X86:
            self.arch = 'i386'
        if self.use_pkgconfig:
            libraries = self._libraries_paths(self.libraries)
        else:
            libraries = self.libraries

        self._create_framework_library(libraries)

    def _libraries_paths(self, libraries):
        pkgconfig = PkgConfig(libraries, env=self.env)
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
        cmdline  = ['clang', '-dynamiclib', '-o', self.libname, '-arch', self.arch]
        if self.target == Distro.OS_X:
            cmdline += ['-mmacosx-version-min=%s' % self.min_version]

        cmdline += ['-install_name', self.install_name]
        for lib in libraries:
            cmdline += ['-Wl,-reexport_library', lib]

        shell.new_call(cmdline, env=self.env)

    def _get_lib_file_name(self, lib):
        return 'lib%s.dylib' % lib

class BuildStatusPrinter:
    def __init__(self, archs, interactive):
        self.archs = archs
        self.interactive = interactive
        self.arch_total = collections.defaultdict(lambda : 0)
        self.arch_count = collections.defaultdict(lambda : 0)

    def inc_arch(self, arch):
        self.arch_count[arch] += 1
        self.output_status_line()

    def output_status_line(self):
        if self.interactive:
            m.output_status(self._generate_status_line())

    def _generate_status_line(self):
        s = "["
        s += ", ".join([str(arch) + ": (" + str(self.arch_count[arch]) + "/" + str(self.arch_total[arch]) + ")" for arch in self.archs])
        s += "]"
        return s

class StaticFrameworkLibrary(FrameworkLibrary):
    def _get_lib_file_name(self, lib):
        return 'lib%s.a' % lib

    async def _split_static_lib(self, lib, thin_arch=None):
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
            cmd = ['lipo', tmplib, '-thin', thin_arch, '-output', newname]
            proc = await asyncio.create_subprocess_exec(*cmd, cwd=lib_tmpdir,
                stderr=subprocess.PIPE, env=self.env)

            (unused_out, output) = await proc.communicate()

            if sys.stderr.encoding:
                output = output.decode(sys.stderr.encoding, errors='replace')

            if proc.returncode != 0:
                if 'does not contain the specified architecture' in output:
                    return None
                raise FatalError('Running {!r}, returncode {}:\n{}'.format(cmd, proc.returncode, output))
            tmplib = os.path.join (lib_tmpdir, newname)

        await shell.async_call(['ar', '-x', tmplib], lib_tmpdir, env=self.env)

        # object files with the same name in an archive are overwritten
        # when they are extracted. osx's ar does not support the N count
        # modifier so after extracting all the files we remove them from
        # the archive to extract those with duplicated names.
        # eg:
        # ar t libavcodec.a -> mlpdsp.o mlpdsp.o (2 objects with the same name)
        # ar d libavcodec.a mlpdsp.o (we remove the first one)
        # ar t libavcodec.a -> mlpdsp.o (we only the second one now)
        files = (await shell.async_call_output(['ar', '-t', tmplib], lib_tmpdir, env=self.env)).split('\n')
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
                await shell.async_call(['ar', '-x', tmplib, f], lib_tmpdir, env=self.env)
                shutil.move (path, new_path)
                await shell.async_call(['ar', '-d',tmplib, f], lib_tmpdir, env=self.env)

        return lib_tmpdir

    async def _check_duplicated_symbols(self, file, tmpdir):
        syms = defaultdict(list)
        symbols = (await shell.async_call_output(['nm', '-UA', file], tmpdir, env=self.env)).split('\n')
        # nm output is: test.o: 00000000 T _gzwrite
        # (filename, address, symbol type, symbols_name)
        for s in symbols:
            s = s.split(' ')
            if len(s) == 4 and s[2] == 'T':
                syms[s[3]].append(s)
        dups = {}
        for k,v in syms.items():
            if len(v) > 1:
                dups[k] = v
        if dups:
            m.warning ("The static library contains duplicated symbols")
        for k, v in dups.items():
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

        split_queue = asyncio.Queue()
        join_queues = collections.defaultdict(asyncio.Queue)
        for thin_arch in archs:
            os.makedirs (os.path.join (tmpdir, thin_arch))

        status = BuildStatusPrinter(archs, m.console_is_interactive())
        for lib in libraries:
            for thin_arch in archs:
                split_queue.put_nowait((lib, thin_arch))
                status.arch_total[thin_arch] += 1

        async def split_library_worker():
            while True:
                lib, thin_arch = await split_queue.get()

                tmpdir_thinarch = os.path.join(tmpdir, thin_arch)
                libprefix = os.path.split(lib)[-1].replace('.', '_')

                if len(archs) > 1: #should be a fat file, split only to the arch we want
                    libprefix += '_%s_' % thin_arch
                    lib_tmpdir = await self._split_static_lib(lib, thin_arch)
                else:
                    lib_tmpdir = await self._split_static_lib(lib)

                if lib_tmpdir is None:
                    # arch is not supported in the static lib, skip it
                    status.inc_arch (thin_arch)
                    split_queue.task_done()
                    continue

                obj_files = shell.ls_files(['*.o'], lib_tmpdir)
                obj_dict = {}
                for obj_f in obj_files:
                    obj_path = os.path.join(lib_tmpdir, obj_f)
                    md5 = (await shell.async_call_output(['md5', '-q', obj_path], env=self.env)).split('\n')[0]
                    md5 = '%s-%s' % (md5, os.path.getsize(obj_path))
                    obj_dict[obj_f] = md5

                join_queues[thin_arch].put_nowait((lib, lib_tmpdir, obj_dict))
                split_queue.task_done()

        async def join_library_worker(q, thin_arch):
            object_files_md5 = []
            while True:
                lib, lib_tmpdir, obj_dict = await q.get()

                status.inc_arch (thin_arch)

                tmpdir_thinarch = os.path.join(tmpdir, thin_arch)
                libprefix = os.path.split(lib)[-1].replace('.', '_')

                target_objs = []
                for obj_f, md5 in obj_dict.items():
                    obj_path = os.path.join(lib_tmpdir, obj_f)
                    if md5 not in object_files_md5:
                        target_name = '%s-%s' % (libprefix, obj_f)
                        try:
                            # Hard link source file to the target name
                            os.link(obj_path, tmpdir_thinarch + '/' + target_name)
                        except:
                            # Fall back to cp if hard link doesn't work for any reason
                            await shell.async_call(['cp', obj_path, target_name], tmpdir_thinarch, env=self.env)

                        # If we have a duplicate object, commit any collected ones
                        if target_name in target_objs:
                            m.warning ("Committing %d objects due to dup %s" % (len (target_objs), target_name))
                            await shell.async_call(['ar', '-cqS', libname] + target_objs, tmpdir_thinarch, env=self.env)
                            target_objs = []

                        target_objs.append (target_name)
                        object_files_md5.append(md5)

                # Put all the collected target_objs in the archive. cmdline limit is 262k args on OSX.
                if len(target_objs):
                    await shell.async_call(['ar', '-cqS', libname] + target_objs, tmpdir_thinarch, env=self.env)
                shutil.rmtree(lib_tmpdir)
                q.task_done()

        async def post_join_worker(thin_arch):
            tmpdir_thinarch = os.path.join(tmpdir, thin_arch)
            await shell.async_call(['ar', '-s', libname], tmpdir_thinarch, env=self.env)
            lib = os.path.join(tmpdir, thin_arch, libname)
            await self._check_duplicated_symbols(lib, tmpdir)

        async def split_join_task():
            tasks = [asyncio.ensure_future(join_library_worker(join_queues[arch], arch)) for arch in archs]
            [tasks.append(asyncio.ensure_future(split_library_worker())) for i in range(len(archs))]
            async def split_join_queues_done():
                await split_queue.join()
                for arch in archs:
                    await join_queues[arch].join()
            await run_tasks(tasks, split_join_queues_done())

            tasks = [asyncio.ensure_future(post_join_worker(thin_arch)) for thin_arch in archs]
            await run_tasks(tasks)
        run_until_complete(split_join_task())

        if len(archs) > 1:
            #merge the final libs into a fat file again
            files = [os.path.join(tmpdir, arch, libname) for arch in archs]
            shell.new_call(['lipo'] + files + ['-create' ,'-output', self.install_name], tmpdir, env=self.env)
        else:
            shell.new_call(['cp', os.path.join(tmpdir, self.arch, libname), self.install_name], tmpdir, env=self.env)
        shutil.rmtree(tmpdir)
