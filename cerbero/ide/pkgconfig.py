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

import subprocess
import os
import sys

from cerbero.enums import Distro
from cerbero.errors import FatalError
from cerbero.utils import shell, to_winpath

class PkgConfig(object):
    '''
    pkg-config wrapper
    '''

    cmd = 'pkg-config'

    def __init__(self, libs, inherit=True, env=None):
        if isinstance(libs, str):
            libs = [libs]
        self.env = os.environ.copy() if env is None else env.copy()
        self.libs = libs
        self.inherit = inherit
        if not inherit:
            requires = self.requires()
            if requires == []:
                self.inherit = True
            else:
                self.deps_pkgconfig = PkgConfig(requires, env=env)

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

    def static_libraries(self):
        res = self._exec('--libs-only-l --static', '-l')
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
    def list_all(env=None):
        res = PkgConfig._call('%s --list-all' % PkgConfig.cmd, '\n', env=env)
        return [x.split(' ', 1)[0] for x in res]

    @staticmethod
    def list_all_include_dirs(env=None):
        include_dirs = []
        for pc in PkgConfig.list_all(env=env):
            pkgconfig = PkgConfig(pc, env=env)
            d = pkgconfig.include_dirs()
            for p in d:
                if not os.path.isabs(p):
                    raise FatalError("pkg-config file %s contains relative include dir %s" % (pc, p))

            include_dirs.extend(pkgconfig.include_dirs())
        return list(set(include_dirs))

    @staticmethod
    def set_default_search_dir(path, env, config):
        env['PKG_CONFIG_LIBDIR'] = path

    @staticmethod
    def add_search_dir(path, env, config):
        PkgConfig._add_path(path, env, config, 'PKG_CONFIG_PATH')

    @staticmethod
    def set_executable(env, config):
        if config.distro == Distro.MSYS2:
            # We use pkg-config installed with pacman
            env['PKG_CONFIG'] = "/ucrt64/bin/pkg-config"
            return
        env['PKG_CONFIG'] = os.path.join(config.build_tools_prefix, 'bin', 'pkg-config')

    def _remove_deps(self, func, all_values):
        if not self.inherit:
            deps = func(self.deps_pkgconfig)
            return list(set(all_values) - set(deps))
        return all_values

    def _exec(self, mode, delimiter=None):
        cmd = '%s %s %s' % (self.env.get('PKG_CONFIG', self.cmd), mode, ' '.join(self.libs))
        return self._call(cmd, delimiter, env=self.env)

    @staticmethod
    def _call(cmd, delimiter=None, env=None):
        env = os.environ.copy() if env is None else env.copy()
        output = shell.check_output(cmd, env=env)
        output = output.strip()

        if delimiter:
            res = output.split('%s' % delimiter)
            if res[0] == ' ':
                res.remove(' ')
            if res[0] == '':
                res.remove('')
            return [x.strip() for x in res]
        return output

    @staticmethod
    def _add_path(path, env, config, var):
        separator = os.pathsep
        dirs = [path]
        env_paths = env.get(var, None)
        if env_paths is not None:
            dirs += env_paths.split(separator)
        env[var] = separator.join(dirs)