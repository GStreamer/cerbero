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

from cerbero.config import Platform
from cerbero.errors import PackageNotFoundError
from cerbero.packages.package import Package, SDKPackage, InstallerPackage
from cerbero.packages.packagesstore import PackagesStore
from test import test_packages_common as common


PACKAGE = """
class Package(package.Package):

    name = 'test-package'

    def test_imports(self):
        Platform.WINDOWS
        Distro.WINDOWS
        DistroVersion.WINDOWS_7
        Architecture.X86
"""

SDKPACKAGE = """
class SDKPackage(package.SDKPackage):

    name = 'test-package'
"""

INSTALLERPACKAGE = """
class InstallerPackage(package.InstallerPackage):

    name = 'test-package'
"""


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.config = common.DummyConfig()
        self.config.packages_dir = '/test'
        self.config.target_platform = Platform.LINUX
        self.store = PackagesStore(self.config, False)

    def testAddPackage(self):
        package = common.Package1(self.config, None, None)
        self.assertEqual(len(self.store._packages), 0)
        self.store.add_package(package)
        self.assertEqual(len(self.store._packages), 1)
        self.assertEqual(package, self.store._packages[package.name])

    def testGetPackage(self):
        package = common.Package1(self.config, None, None)
        self.store.add_package(package)
        self.assertEqual(package, self.store.get_package(package.name))

    def testPackageNotFound(self):
        self.assertRaises(PackageNotFoundError, self.store.get_package, 'unknown')

    def testPackagesList(self):
        package = common.Package1(self.config, None, None)
        metapackage = common.MetaPackage(self.config, None)
        self.store.add_package(package)
        self.store.add_package(metapackage)
        packages = sorted([package, metapackage], key=lambda x: x.name)
        self.assertEqual(packages, self.store.get_packages_list())

    def testPackageDeps(self):
        package = common.Package1(self.config, None, None)
        package2 = common.Package2(self.config, None, None)
        self.store.add_package(package)
        self.store.add_package(package2)
        self.assertEqual(package.deps, [x.name for x in self.store.get_package_deps(package.name)])

    def testMetaPackageDeps(self):
        metapackage = common.MetaPackage(self.config, None)
        self.store.add_package(metapackage)
        # the metapackage depends on package that are not yet in the store
        self.assertRaises(PackageNotFoundError, self.store.get_package_deps, metapackage.name)
        for klass in [common.Package1, common.Package2, common.Package3, common.Package4]:
            p = klass(self.config, None, None)
            self.store.add_package(p)
        for klass in [common.MetaPackage]:
            p = klass(self.config, None)
            self.store.add_package(p)
        deps = ['gstreamer-test-bindings', 'gstreamer-test1', 'gstreamer-test2', 'gstreamer-test3']
        res = [x.name for x in self.store.get_package_deps(metapackage.name)]
        self.assertEqual(sorted(deps), sorted(res))

    def testLoadPackageFromFile(self):
        package_file = tempfile.NamedTemporaryFile()
        package_file.write(PACKAGE)
        package_file.flush()
        p = self.store._load_package_from_file(package_file.name)
        self.assertIsInstance(p, Package)
        self.assertEqual('test-package', p.name)

    def testLoadMetaPackageFromFile(self):
        for x, t in [(SDKPACKAGE, SDKPackage), (INSTALLERPACKAGE, InstallerPackage)]:
            package_file = tempfile.NamedTemporaryFile()
            package_file.write(x)
            package_file.flush()
            p = self.store._load_package_from_file(package_file.name)
            print(p, type(p))
            self.assertIsInstance(p, t)
            self.assertEqual('test-package', p.name)

    def testImports(self):
        package_file = tempfile.NamedTemporaryFile()
        package_file.write(PACKAGE)
        package_file.flush()
        p = self.store._load_package_from_file(package_file.name)
        self.assertIsInstance(p, Package)
        try:
            p.test_imports()
        except ImportError as e:
            self.fail('Import error raised, %s', e)
