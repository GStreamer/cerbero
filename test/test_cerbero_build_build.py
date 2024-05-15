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

import unittest
import os

from test.test_common import DummyConfig
from cerbero.build import build


class MakefilesBase(build.MakefilesBase):
    srcdir = ''
    build_dir = ''

    def __init__(self, config):
        self.config = config
        self.config_src_dir = os.path.join(config.sources, 'test')
        self.env = {}
        build.MakefilesBase.__init__(self)

    @build.modify_environment
    def get_env_var(self, var):
        if var not in self.env:
            return None
        return self.env[var]

    @build.modify_environment
    def get_env_var_nested(self, var):
        return self.get_env_var(var)


class ModifyEnvTest(unittest.TestCase):
    def setUp(self):
        self.var = 'TEST_VAR'
        self.val1 = 'test'
        self.val2 = 'test2'
        self.mk = MakefilesBase(DummyConfig())

    def testAppendEnv(self):
        self.mk.env[self.var] = self.val1
        self.mk.append_env(self.var, self.val2)
        val = self.mk.get_env_var(self.var)
        self.assertEqual(val, '%s %s' % (self.val1, self.val2))

    def testAppendNonExistentEnv(self):
        if self.var in self.mk.env:
            del self.mk.env[self.var]
        self.mk.append_env(self.var, self.val2)
        val = self.mk.get_env_var(self.var)
        self.assertEqual(val, '%s' % self.val2)

    def testSystemLibs(self):
        self.mk.env['PKG_CONFIG_PATH'] = '/path/1'
        self.mk.env['PKG_CONFIG_LIBDIR'] = '/path/2'
        self.mk.config.allow_system_libs = True
        self.mk.use_system_libs = True
        self.mk.maybe_add_system_libs('configure')
        val = self.mk.get_env_var('PKG_CONFIG_PATH')
        self.assertEqual(
            val, '/path/2:/path/1:/usr/lib/pkgconfig:' '/usr/share/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig'
        )
        val = self.mk.get_env_var('PKG_CONFIG_LIBDIR')
        self.assertEqual(val, '/path/2')

    def testNestedModif(self):
        self.mk.env[self.var] = self.val1
        self.mk.append_env(self.var, self.val2)
        val = self.mk.get_env_var(self.var)
        self.assertEqual(val, '%s %s' % (self.val1, self.val2))
        val = self.mk.get_env_var_nested(self.var)
        self.assertEqual(val, '%s %s' % (self.val1, self.val2))
