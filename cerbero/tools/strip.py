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
from cerbero.config import Platform
from cerbero.utils import shell, run_until_complete, messages as m


class Strip(object):
    """
    Wrapper for the strip tool.
    Warning: This wrapper should never be used for msvc-built binaries since it usually corrupts them.
    Please, check using_msvc == False.
    """

    def __init__(self, config, excludes=None, keep_symbols=None):
        self.config = config
        self.excludes = excludes or []
        self.keep_symbols = keep_symbols or []
        self.build_env = self.config.get_build_env()
        self.strip_cmd = self.build_env.get('STRIP', 'strip')

    async def async_strip_file(self, path):
        if not self.strip_cmd:
            m.warning('Strip command is not defined')
            return

        for f in self.excludes:
            if f in path:
                return

        if self.config.target_platform == Platform.DARWIN:
            cmd = self.strip_cmd + ['-x', path]
        else:
            cmd = self.strip_cmd[:]
            for symbol in self.keep_symbols:
                cmd += ['-K', symbol]
            cmd += ['--strip-unneeded', path]

        try:
            # async_call() is not adapted for EnvValues in env
            await shell.async_call(cmd, env={'PATH': self.build_env['PATH'].get()})
        except Exception as e:
            m.warning(e)

    def strip_file(self, path):
        run_until_complete(self.async_strip_file(path))

    def strip_dir(self, dir_path):
        if not self.strip_cmd:
            m.warning('Strip command is not defined')
            return

        tasks = []
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                tasks.append(self.async_strip_file(os.path.join(dirpath, f)))
        run_until_complete(tasks)
