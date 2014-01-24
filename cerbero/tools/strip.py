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
from cerbero.config import Platform
from cerbero.utils import shell

class Strip(object):
    '''Wrapper for the strip tool'''

    STRIP_CMD = '$STRIP'

    def __init__(self, config, excludes=None, keep_symbols=None):
        self.config = config
        self.excludes = excludes or []
        self.keep_symbols = keep_symbols or []

    def strip_file(self, path):
        for f in self.excludes:
            if f in path:
                return
        try:
            if self.config.target_platform == Platform.DARWIN:
                shell.call("%s -x %s" % (self.STRIP_CMD, path))
            else:
                shell.call("%s %s --strip-unneeded %s" % (self.STRIP_CMD,
                    ' '.join(['-K %s' % x for x in self.keep_symbols]), path))
        except:
            pass

    def strip_dir(self, dir_path):
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                self.strip_file(os.path.join(dirpath, f))
