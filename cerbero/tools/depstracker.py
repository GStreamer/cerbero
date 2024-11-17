# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2013 Andoni Morales Alastruey <ylatuya@gmail.com>
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
import re

from cerbero.config import Platform
from cerbero.utils import shell


class RecursiveLister:
    def list_file_deps(self, prefix, path):
        raise NotImplementedError()

    def find_deps(self, prefix, lib, state=None, ordered=None):
        if state is None:
            state = {}
        if ordered is None:
            ordered = []
        if state.get(lib, 'clean') == 'processed':
            return
        if state.get(lib, 'clean') == 'in-progress':
            return
        state[lib] = 'in-progress'
        lib_deps = self.list_file_deps(prefix, lib)
        for libdep in lib_deps:
            self.find_deps(prefix, libdep, state, ordered)
        state[lib] = 'processed'
        ordered.append(lib)
        return ordered

    def list_deps(self, prefix, path):
        return self.find_deps(prefix, os.path.realpath(path), {}, [])


class ObjdumpLister(RecursiveLister):
    def list_file_deps(self, prefix, path):
        env = os.environ.copy()
        env['LC_ALL'] = 'C'
        files = shell.check_output(['objdump', '-xw', path], env=env).splitlines()
        prog = re.compile(r'(?i)^.*DLL[^:]*: (\S+\.dll)$')
        files = [prog.sub(r'\1', x) for x in files if prog.match(x) is not None]
        files = [os.path.join(prefix, 'bin', x) for x in files if x.lower().endswith('dll')]
        return [os.path.realpath(x) for x in files if os.path.exists(x)]


class OtoolLister(RecursiveLister):
    def list_file_deps(self, prefix, path):
        files = shell.check_output(['otool', '-L', path]).splitlines()[1:]
        # Shared libraries might be relocated, we look for files with the
        # prefix or starting with @rpath
        files = [x.strip().split(' ')[0] for x in files if prefix in x or '@rpath' in x]
        return [x.replace('@rpath/', prefix) for x in files]


class LddLister:
    def list_deps(self, prefix, path):
        files = shell.check_output(['ldd', path]).splitlines()
        return [x.split(' ')[2] for x in files if prefix in x]


class DepsTracker:
    BACKENDS = {Platform.WINDOWS: ObjdumpLister, Platform.LINUX: LddLister, Platform.DARWIN: OtoolLister}

    def __init__(self, platform, prefix):
        self.libs_deps = {}
        self.prefix = prefix
        if self.prefix[:-1] != '/':
            self.prefix += '/'
        self.lister = self.BACKENDS[platform]()

    def list_deps(self, path):
        deps = self.lister.list_deps(self.prefix, path)
        rdeps = []
        for d in deps:
            if os.path.islink(d):
                rdeps.append(os.path.realpath(d))
        return [x.replace(self.prefix, '') for x in deps + rdeps]
