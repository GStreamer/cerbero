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


class ModifyEnvBase(build.ModifyEnvBase):
    def __init__(self, config):
        self.env = {}
        self.config = config
        self.src_dir = os.path.join(config.sources, 'test')
        build.ModifyEnvBase.__init__(self)

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
        self.mk = ModifyEnvBase(DummyConfig())

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

    def testNestedModif(self):
        self.mk.env[self.var] = self.val1
        self.mk.append_env(self.var, self.val2)
        val = self.mk.get_env_var(self.var)
        self.assertEqual(val, '%s %s' % (self.val1, self.val2))
        val = self.mk.get_env_var_nested(self.var)
        self.assertEqual(val, '%s %s' % (self.val1, self.val2))
