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

import asyncio
import unittest
import os

from cerbero.build import recipe, build, source
from cerbero.config import Platform, License, Architecture
from cerbero.errors import FatalError
from test.test_common import DummyConfig

# ruff: noqa: E731


class Class1(build.Build):
    test = None

    def __init__(self):
        self.test = 'CODEPASS'
        super().__init__()

    class1_method = lambda x: None

    async def compile(self):
        return 'CODEPASS'


class Class2(source.Source):
    class2_method = lambda x: None

    async def fetch(self):
        return 'CODEPASS'


class Recipe(recipe.Recipe):
    btype = Class1
    stype = Class2

    name = 'recipe'
    version = '0.0.0'
    licenses = [License.LGPLv2Plus]
    deps = ['dep1', 'dep2']
    platform_deps = {Platform.LINUX: ['dep3'], Platform.WINDOWS: ['dep4']}

    files_libs = ['librecipe-test']
    files_bins = ['recipe-test']
    licenses_bins = [License.GPLv2Plus]
    platform_files_test = {Platform.LINUX: ['test1']}
    platform_licenses_test = {Platform.LINUX: [License.BSD_3_Clause]}

    async def post_install(self):
        return 'CODEPASS'


class Class3(object, metaclass=recipe.MetaUniversalRecipe):
    async def _do_step(self, name):
        return name


class TestRecipeMetaClass(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.config.local_sources = ''
        self.config.sources = ''
        self.t = Recipe(self.config, {})

    def testReceiptSubclassBases(self):
        bases = self.t.__class__.mro()
        self.assertTrue(Class1 in bases)
        self.assertTrue(Class2 in bases)

    def testFunctions(self):
        self.assertTrue(hasattr(self.t, 'class1_method'))
        self.assertTrue(hasattr(self.t, 'class2_method'))
        self.assertEqual(asyncio.run(self.t.fetch()), 'CODEPASS')
        self.assertEqual(asyncio.run(self.t.compile()), 'CODEPASS')
        self.assertEqual(asyncio.run(self.t.post_install()), 'CODEPASS')

    def testSubclassesInit(self):
        self.assertEqual(self.t.test, 'CODEPASS')


class TestRecipe(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.config.local_sources = 'path1'
        self.config.sources = 'path2'
        self.recipe = Recipe(self.config, {})

    def testSources(self):
        repo_dir = os.path.join(self.config.local_sources, self.recipe.package_name)
        repo_dir = os.path.abspath(repo_dir)
        build_dir = os.path.join(self.config.sources, self.recipe.package_name)
        build_dir = os.path.abspath(build_dir)

        self.assertEqual(self.recipe.repo_dir, repo_dir)
        self.assertEqual(self.recipe.build_dir, build_dir)

    def testListDeps(self):
        self.recipe.config.target_platform = Platform.LINUX
        self.assertEqual(['dep1', 'dep2', 'dep3'], self.recipe.list_deps())
        self.recipe.config.target_platform = Platform.WINDOWS
        self.assertEqual(['dep1', 'dep2', 'dep4'], self.recipe.list_deps())


class TestLicenses(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.config.local_sources = ''
        self.config.sources = ''
        self.recipe = Recipe(self.config, {})

    def testLicenses(self):
        self.assertEqual(self.recipe.licenses, [License.LGPLv2Plus])

        licenses_libs = self.recipe.list_licenses_by_categories(['libs'])
        self.assertEqual(licenses_libs['libs'], [License.LGPLv2Plus])
        self.assertEqual(list(licenses_libs.values()), [[License.LGPLv2Plus]])
        licenses_bins = self.recipe.list_licenses_by_categories(['bins'])
        self.assertEqual(licenses_bins['bins'], [License.GPLv2Plus])
        self.assertEqual(list(licenses_bins.values()), [[License.GPLv2Plus]])

        self.recipe.platform = Platform.LINUX
        self.recipe.config.target_platform = Platform.LINUX
        licenses_test = self.recipe.list_licenses_by_categories(['test'])
        self.assertEqual(licenses_test['test'], [License.BSD_3_Clause])
        self.assertEqual(list(licenses_test.values()), [[License.BSD_3_Clause]])


class TestMetaUniversalRecipe(unittest.TestCase):
    def testBuildSteps(self):
        obj = Class3()
        for _, step in recipe.BuildSteps():
            self.assertTrue(hasattr(obj, step))
            stepfunc = getattr(obj, step)
            self.assertEqual(asyncio.run(stepfunc()), step)


class TestUniversalRecipe(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.config.target_platform = Platform.LINUX
        self.config_x86 = DummyConfig()
        self.config_x86.target_platform = Platform.LINUX
        self.config_x86.target_arch = Architecture.X86
        self.config_x86_64 = DummyConfig()
        self.config_x86_64.target_platform = Platform.LINUX
        self.config_x86_64.target_arch = Architecture.X86_64
        self.recipe = recipe.UniversalMergedRecipe(self.config)
        self.recipe_x86 = Recipe(self.config_x86, {})
        self.recipe_x86_64 = Recipe(self.config_x86_64, {})

    def testEmpty(self):
        self.assertTrue(self.recipe.is_empty())

    def testProxyEmpty(self):
        self.assertRaises(AttributeError, getattr, self.recipe, 'name')

    def testProxyRecipe(self):
        self.recipe.add_recipe(self.recipe_x86)
        self.assertEqual(self.recipe.name, self.recipe_x86.name)
        self.assertEqual(self.recipe.version, self.recipe_x86.version)
        self.assertEqual(self.recipe.licenses, self.recipe_x86.licenses)

    def testAddRecipe(self):
        self.recipe.add_recipe(self.recipe_x86)
        self.assertEqual(self.recipe._recipes[Architecture.X86], self.recipe_x86)
        self.assertEqual(self.recipe._proxy_recipe, self.recipe_x86)

    def testDifferentRecipe(self):
        self.recipe.add_recipe(self.recipe_x86)
        recipe_test = Recipe(self.config_x86, {})
        recipe_test.name = 'noname'
        self.assertRaises(FatalError, self.recipe.add_recipe, recipe_test)

    def testSteps(self):
        self.assertEqual(self.recipe.steps, [])
        self.recipe.add_recipe(self.recipe_x86)
        self.recipe.add_recipe(self.recipe_x86_64)
        self.assertEqual(self.recipe.steps, recipe.BuildSteps() + [recipe.BuildSteps.MERGE])
