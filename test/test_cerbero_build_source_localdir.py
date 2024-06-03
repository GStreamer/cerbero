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
import tempfile
import shutil

from test.test_common import DummyConfig
from cerbero.build.cookbook import CookBook
from cerbero.build.oven import Oven
from cerbero.config import Config
from cerbero.utils import run_until_complete


class LocalDirTest(unittest.TestCase):
    def setUp(self):
        # Use the cached condif if running in the CI
        in_ci = os.getenv('CI', 'false')
        if in_ci == 'true':
            self.config = Config()
            self.config.load(['config/linux.config', 'localconf.cbc'])
        else:
            self.config = DummyConfig()

        self.tmp = tempfile.mkdtemp()
        self.config.prefix = self.tmp
        self.config.external_recipes = {'test': (os.path.join(os.path.dirname(__file__), 'recipes'), 1)}
        self.cookbook = CookBook(self.config)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def localDirProject(self, name, file):
        # Build the project
        recipe_name = self.cookbook.get_closest_recipe(name)
        recipe = self.cookbook.get_recipe(recipe_name)
        oven = Oven([recipe_name], self.cookbook, force=True)
        run_until_complete(oven.start_cooking())
        files = recipe.files_list()
        # Check for the existance of file1.txt
        self.assertEqual(files, [file])

    def testLocalDirAutotools(self):
        self.localDirProject('autotools-cerbero', 'share/autotools-cerbero/file1.txt')

    def testLocalDirMeson(self):
        self.localDirProject('meson-cerbero', 'share/meson-cerbero/file1.txt')

    def testLocalDirCMake(self):
        self.localDirProject('cmake-cerbero', 'share/cmake-cerbero/file1.txt')
