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
import tempfile
import pickle

from cerbero.build.cookbook import CookBook
from cerbero.errors import RecipeNotFoundError
from test.test_common import DummyConfig as Config
from test.test_build_common import Recipe1


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config.cache_file = '/dev/null'
        self.cookbook = CookBook(self.config, False)

    def testSetGetConfig(self):
        self.assertEqual(self.config, self.cookbook.get_config())

    def testCacheMissing(self):
        status = {'test': 'test'}
        self.cookbook.set_status(status)
        self.cookbook._restore_cache()
        self.assertEqual(self.cookbook.status, {})

    def testSaveCache(self):
        tmp = tempfile.NamedTemporaryFile()
        status = {'test': 'test'}
        self.cookbook.set_status(status)
        self.cookbook.get_config().cache_file = tmp.name
        self.cookbook.save()
        with open(self.cookbook._cache_file(self.config), 'rb') as f:
            loaded_status = pickle.load(f)
            self.assertEqual(status, loaded_status)

    def testLoad(self):
        tmp = tempfile.NamedTemporaryFile()
        status = {'test': 'test'}
        self.cookbook.get_config().cache_file = tmp.name
        with open(tmp.name, 'wb') as f:
            pickle.dump(status, f)
        self.cookbook._restore_cache()
        self.assertEqual(status, self.cookbook.status)

    def testAddGetRecipe(self):
        recipe = Recipe1(self.config, {})
        self.assertRaises(RecipeNotFoundError, self.cookbook.get_recipe, recipe.name)
        self.cookbook.add_recipe(recipe)
        self.assertEqual(recipe, self.cookbook.recipes[recipe.name])
        self.assertEqual(recipe, self.cookbook.get_recipe(recipe.name))
        self.assertEqual(self.cookbook.get_recipes_list(), [recipe])

    def testGetRecipesStatus(self):
        recipe = Recipe1(self.config, {})
        self.cookbook._restore_cache()
        self.assertEqual(self.cookbook.status, {})
        self.cookbook.add_recipe(recipe)
        self.assertEqual(len(self.cookbook.status), 0)
        status = self.cookbook._recipe_status(recipe.name)
        self.assertEqual(len(self.cookbook.status), 1)
        self.assertEqual(status.steps, [])
        status.steps.append('1')
        status = self.cookbook._recipe_status(recipe.name)
        self.assertEqual(len(self.cookbook.status), 1)
        self.assertEqual(status.steps[0], '1')

    def testUpdateStatus(self):
        recipe = Recipe1(self.config, {})
        self.cookbook.add_recipe(recipe)
        self.cookbook._restore_cache()
        self.cookbook.update_step_status(recipe.name, 'fetch')
        status = self.cookbook._recipe_status(recipe.name)
        self.assertEqual(status.steps, ['fetch'])
        self.cookbook.update_step_status(recipe.name, 'build')
        status = self.cookbook._recipe_status(recipe.name)
        self.assertEqual(status.steps, ['fetch', 'build'])
        self.cookbook.update_step_status(recipe.name, 'install')
        status = self.cookbook._recipe_status(recipe.name)
        self.assertEqual(status.steps, ['fetch', 'build', 'install'])
        for step in ['fetch', 'build', 'install']:
            self.assertTrue(self.cookbook.step_done(recipe.name, step))

    def testBuildStatus(self):
        recipe = Recipe1(self.config, {})
        self.cookbook.add_recipe(recipe)
        self.cookbook._restore_cache()
        self.cookbook.update_build_status(recipe.name, '1.0')
        self.assertFalse(self.cookbook.recipe_needs_build(recipe.name))
        self.assertEqual(self.cookbook.status[recipe.name].built_version, '1.0')
        self.cookbook.update_build_status(recipe.name, None)
        self.assertTrue(self.cookbook.status[recipe.name].needs_build)
        self.assertEqual(self.cookbook.status[recipe.name].built_version, None)

    def testResetRecipeStatus(self):
        recipe = Recipe1(self.config, {})
        self.cookbook.add_recipe(recipe)
        self.cookbook._restore_cache()
        self.cookbook.reset_recipe_status(recipe.name)
        status = self.cookbook._recipe_status(recipe.name)
        self.assertEqual(status.steps, [])
        self.assertTrue(self.cookbook.status[recipe.name].needs_build)
