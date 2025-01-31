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

import shutil
import unittest
import tempfile

from cerbero.config import Platform, Distro
from cerbero.packages import PackageType
from test.test_packages_common import Package1, Package4, MetaPackage, App
from test.test_build_common import create_cookbook, add_files
from test.test_packages_common import create_store
from test.test_common import DummyConfig


class Config(DummyConfig):
    def __init__(self, tmp, platform):
        super().__init__()
        self.prefix = tmp
        self.target_platform = platform


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        win32config = Config(self.tmp, Platform.WINDOWS)
        # FIXME config.py should initialize this
        win32config.mingw_env_for_toolchain = dict()
        win32config.mingw_env_for_build_system = dict()
        win32config.msvc_env_for_toolchain = dict()
        win32config.msvc_env_for_build_system = dict()

        linuxconfig = Config(self.tmp, Platform.LINUX)
        self.win32store = create_store(win32config)
        self.win32package = Package1(win32config, self.win32store, create_cookbook(win32config))
        # FIXME we pass the store, but we need to explicitly add it
        self.win32store.add_package(self.win32package)

        self.linuxstore = create_store(linuxconfig)
        self.linuxpackage = Package1(linuxconfig, self.linuxstore, create_cookbook(linuxconfig))
        # FIXME we pass the store, but we need to explicitly add it
        self.linuxstore.add_package(self.linuxpackage)

        self.win32package.load()
        self.linuxpackage.load()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testPackageMode(self):
        self.assertEqual(self.linuxpackage.name, 'gstreamer-test1')
        self.assertEqual(self.linuxpackage.shortdesc, 'GStreamer Test')
        self.linuxpackage.set_mode(PackageType.DEVEL)
        self.assertEqual(self.linuxpackage.package_mode, PackageType.DEVEL)
        self.assertEqual(self.linuxpackage.name, 'gstreamer-test1-devel')
        self.assertEqual(self.linuxpackage.shortdesc, 'GStreamer Test (Development Files)')

    def testParseFiles(self):
        self.assertEqual(self.win32package._recipes_files['recipe1'], ['misc', 'libs', 'bins'])
        self.assertEqual(self.win32package._recipes_files['recipe5'], ['libs'])

    def testListRecipesDeps(self):
        self.assertEqual(self.win32package.recipes_dependencies(), ['recipe1', 'recipe5', 'recipe2'])
        self.assertEqual(self.linuxpackage.recipes_dependencies(), ['recipe1', 'recipe2'])

    def testFilesList(self):
        add_files(self.tmp)
        winfiles = [
            'README',
            'bin/gst-launch.exe',
            'bin/libgstreamer-win32.dll',
            'bin/libgstreamer-0.10.dll',
            'bin/windows.exe',
            'libexec/gstreamer-0.10/pluginsloader.exe',
            'windows',
            'bin/libtest.dll',
        ]
        linuxfiles = [
            'README',
            'bin/gst-launch',
            'bin/linux',
            'lib/x86_64-linux-gnu/libgstreamer-x11.so.1',
            'lib/x86_64-linux-gnu/libgstreamer-0.10.so.1',
            'libexec/gstreamer-0.10/pluginsloader',
            'linux',
        ]
        self.win32package.load()
        self.linuxpackage.load()
        self.assertEqual(sorted(winfiles), sorted(self.win32package.files_list()))
        self.assertEqual(sorted(linuxfiles), sorted(self.linuxpackage.files_list()))

    def testDevelFilesList(self):
        add_files(self.tmp)
        devfiles = ['lib/x86_64-linux-gnu/libgstreamer-0.10.a']
        linuxdevfiles = devfiles + [
            'lib/x86_64-linux-gnu/libgstreamer-0.10.so',
            'lib/x86_64-linux-gnu/libgstreamer-x11.a',
            'lib/x86_64-linux-gnu/libgstreamer-x11.so',
        ]
        windevfiles = devfiles + [
            'lib/x86_64-linux-gnu/libgstreamer-win32.a',
            'lib/x86_64-linux-gnu/libgstreamer-win32.dll.a',
            'lib/x86_64-linux-gnu/gstreamer-win32.lib',
            'lib/x86_64-linux-gnu/libtest.a',
            'lib/x86_64-linux-gnu/libtest.dll.a',
            'lib/x86_64-linux-gnu/test.lib',
            'lib/x86_64-linux-gnu/libgstreamer-0.10.dll.a',
            'lib/x86_64-linux-gnu/gstreamer-0.10.lib',
        ]

        self.win32package.load()
        self.linuxpackage.load()
        self.assertEqual(sorted(windevfiles), self.win32package.devel_files_list())
        self.assertEqual(sorted(linuxdevfiles), self.linuxpackage.devel_files_list())

    def testSystemDependencies(self):
        config = Config(self.tmp, Platform.LINUX)
        config.target_distro = Distro.DEBIAN
        package = Package4(config, None, None)
        self.assertEqual(package.get_sys_deps(), ['python'])
        config.target_distro = Distro.REDHAT
        config.target_distro_version = 'fedora_16'
        package = Package4(config, None, None)
        self.assertEqual(package.get_sys_deps(), ['python27'])


class TestMetaPackages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        config = Config(self.tmp, Platform.LINUX)
        self.store = create_store(config)
        self.package = MetaPackage(config, self.store)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _compareList(self, func_name):
        list_func = getattr(self.package, func_name)
        packages = [self.store.get_package(x) for x in self.package.list_packages()]
        files = []
        for package in packages:
            list_func = getattr(package, func_name)
            files.extend(list_func())

        list_func = getattr(self.package, func_name)
        self.assertEqual(sorted(files), list_func())

    def testListPackages(self):
        expected = ['gstreamer-test1', 'gstreamer-test3', 'gstreamer-test-bindings', 'gstreamer-test2']
        self.assertEqual(self.package.list_packages(), expected)

    def testPlatfromPackages(self):
        packages_attr = object.__getattribute__(self.package, 'packages')
        self.assertEqual(len(packages_attr), 3)
        platform_packages_attr = object.__getattribute__(self.package, 'platform_packages')
        self.assertEqual(len(platform_packages_attr), 1)
        self.assertEqual(len(self.package.packages), len(packages_attr) + len(platform_packages_attr))

    def testFilesList(self):
        self._compareList('files_list')

    def testDevelFilesList(self):
        self._compareList('devel_files_list')

    def testAllFilesList(self):
        self._compareList('all_files_list')


class AppPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        config = Config(self.tmp, Platform.LINUX)
        self.store = create_store(config)
        self.cookbook = create_cookbook(config)
        self.app = App(config, self.store, self.cookbook)
        self.app.load()
        add_files(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def listFilesWithEmbededDeps(self):
        files = []
        packages_deps = [self.store.get_package(x) for x in self.app.deps]
        for dep in self.app.deps:
            packages_deps.extend(self.store.get_package_deps(dep))
        packages_deps = list(set(packages_deps))
        for package in packages_deps:
            files.extend(package.files_list())
        files.extend(self.app._app_recipe.files_list())
        files = sorted(set(files))
        return files

    def testListFilesWithEmbededDepsOnLinux(self):
        self.app.embed_deps = True
        expected = self.listFilesWithEmbededDeps()
        result = self.app.files_list()
        self.assertEqual(expected, result)

    def testListFilesWithEmbededDepsOnWindows(self):
        self.app.embed_deps = True
        self.app.config.target_platform = Platform.WINDOWS
        expected = self.listFilesWithEmbededDeps()
        result = self.app.files_list()
        self.assertEqual(expected, result)

    def testListFilesWithoutEmbededDeps(self):
        self.app.embed_deps = False
        expected = self.app._app_recipe.files_list()
        result = self.app.files_list()
        self.assertEqual(expected, result)

    def testDevelFilesList(self):
        self.assertEqual(self.app.devel_files_list(), [])

    def testAllFilesList(self):
        self.assertNotEqual(self.app.files_list(), [])
        self.assertNotEqual(self.app.all_files_list(), [])
        self.assertEqual(self.app.files_list(), self.app.all_files_list())
