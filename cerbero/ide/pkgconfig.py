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

import subprocess
import os

from cerbero.errors import FatalError

class PkgConfig(object):
    '''
    pkg-config wrapper
    '''

    cmd = 'pkg-config'

    def __init__(self, libs, inherit=True):
        if isinstance(libs, str):
            libs = [libs]
        self.libs = libs
        self.inherit = inherit
        if not inherit:
            requires = self.requires()
            if requires == []:
                self.inherit = True
            else:
                self.deps_pkgconfig = PkgConfig(requires)

    def include_dirs(self):
        res = self._exec('--cflags-only-I', '-I')
        return self._remove_deps(PkgConfig.include_dirs, res)

    def cflags(self):
        res = self._exec('--cflags-only-other', ' ')
        return self._remove_deps(PkgConfig.cflags, res)

    def libraries_dirs(self):
        res = self._exec('--libs-only-L', '-L')
        return self._remove_deps(PkgConfig.libraries_dirs, res)

    def libraries(self):
        res = self._exec('--libs-only-l', '-l')
        return self._remove_deps(PkgConfig.libraries, res)

    def requires(self):
        res = []
        for x in self._exec('--print-requires', '\n'):
            # take care of requires expressed with version requirements
            # eg: glib-2.0 >= 2.10
            libname = x.replace('<', '').replace('>', '').split('=')[0]
            res.append(libname.strip())
        return res

    def prefix(self):
        return self._exec('--variable=prefix')

    @staticmethod
    def list_all():
        res = PkgConfig._call('%s --list-all' % PkgConfig.cmd, '\n')
        return [x.split(' ', 1)[0] for x in res]

    @staticmethod
    def list_all_include_dirs():
        include_dirs = []
        for pc in PkgConfig.list_all():
            pkgconfig = PkgConfig(pc)
            d = pkgconfig.include_dirs()
            for p in d:
                if not os.path.isabs(p):
                    raise FatalError("pkg-config file %s contains relative include dir %s" % (pc, p))

            include_dirs.extend(pkgconfig.include_dirs())
        return list(set(include_dirs))

    def _remove_deps(self, func, all_values):
        if not self.inherit:
            deps = func(self.deps_pkgconfig)
            return list(set(all_values) - set(deps))
        return all_values

    def _exec(self, mode, delimiter=None):
        cmd = '%s %s %s' % (self.cmd, mode, ' '.join(self.libs))
        return self._call(cmd, delimiter)

    @staticmethod
    def _call(cmd, delimiter=None):
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        output, unused_err = process.communicate()
        output = output.strip()
        if delimiter:
            res = output.split('%s' % delimiter)
            if res[0] == ' ':
                res.remove(' ')
            if res[0] == '':
                res.remove('')
            return [x.strip() for x in res]
        return output
