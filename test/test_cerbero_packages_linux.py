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

from cerbero.config import DEFAULT_PACKAGER
from cerbero.packages import PackageType
from cerbero.packages import linux, PackagerBase
from test.test_common import DummyConfig as Config
from test.test_packages_common import Package1, create_store


packed = []


class LoggerPackager(linux.LinuxPackager):
    def pack(self, output_dir, devel, force, keep_temp, pack_deps, tmpdir):
        packed.append(self.package.name)


class DummyPackager(linux.LinuxPackager):
    def build(self, output_dir, tarname, tmpdir, packagedir, srcdir):
        linux.LinuxPackager.build(self, output_dir, tarname, tmpdir, packagedir, srcdir)
        return ['test']

    def create_tree(self, tmpdir):
        linux.LinuxPackager.create_tree(self, tmpdir)
        return ('', '', '')


class DummyTarballPackager(PackagerBase):
    def pack(self, output_dir, devel=True, force=False, split=True, package_prefix='', strip_binaries=False):
        return ['test']


linux.DistTarball = DummyTarballPackager


class LinuxPackagesTest(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.store = create_store(self.config)
        self.packager = linux.LinuxPackager(self.config, self.store.get_package('gstreamer-runtime'), self.store)

    def testInit(self):
        config = Config()

        # Test default values
        package = Package1(config, None, None)
        packager = linux.LinuxPackager(config, package, None)
        self.assertEqual(packager.package_prefix, '')
        self.assertEqual(packager.full_package_name, 'gstreamer-test1-1.0')
        self.assertEqual(packager.packager, DEFAULT_PACKAGER)

        # Test packages_prefix and packager
        config.packages_prefix = 'test'
        config.packager = 'Pin <pan@p.un>'
        packager = linux.LinuxPackager(config, package, None)
        self.assertEqual(packager.package_prefix, 'test-')
        self.assertEqual(packager.full_package_name, 'test-gstreamer-test1-1.0')
        self.assertEqual(packager.packager, 'Pin <pan@p.un>')

        # Test ignore package
        package.ignore_package_prefix = True
        packager = linux.LinuxPackager(config, package, None)
        self.assertEqual(packager.package_prefix, '')
        self.assertEqual(packager.full_package_name, 'gstreamer-test1-1.0')

    def testRequires(self):
        self.packager._empty_packages = []
        expected = sorted(['gstreamer-test-bindings', 'gstreamer-test2', 'gstreamer-test3', 'gstreamer-test1'])

        requires = self.packager.get_requires(PackageType.RUNTIME, '-dev')
        self.assertEqual(expected, requires)

        # test devel packages
        requires = self.packager.get_requires(PackageType.DEVEL, '-dev')
        self.assertEqual([], requires)
        self.store.get_package('gstreamer-test1').has_devel_package = True
        requires = self.packager.get_requires(PackageType.DEVEL, '-dev')
        self.assertEqual(['gstreamer-test1-dev'], requires)
        for p in expected:
            self.store.get_package(p).has_devel_package = True
        requires = self.packager.get_requires(PackageType.DEVEL, '-dev')
        self.assertEqual([x + '-dev' for x in expected], requires)

        # test empty packages
        self.packager._empty_packages = [self.store.get_package('gstreamer-test2')]
        requires = self.packager.get_requires(PackageType.RUNTIME, '-dev')
        expected.remove('gstreamer-test2')
        self.assertEqual(expected, requires)

    def testMetaPackageRequires(self):
        self.packager._empty_packages = []
        expected = (['gstreamer-test1'], ['gstreamer-test3'], ['gstreamer-test-bindings'])
        self.store.get_package('gstreamer-test1').has_runtime_package = True
        self.store.get_package('gstreamer-test3').has_runtime_package = True
        self.store.get_package('gstreamer-test-bindings').has_runtime_package = True
        requires = self.packager.get_meta_requires(PackageType.RUNTIME, '')
        self.assertEqual(expected, requires)

        # test devel packages
        requires = self.packager.get_meta_requires(PackageType.DEVEL, '-dev')
        self.assertEqual((['gstreamer-runtime'], [], []), requires)

        # test empty packages
        self.store.get_package('gstreamer-test1').has_devel_package = True
        requires = self.packager.get_meta_requires(PackageType.DEVEL, '-dev')
        self.assertEqual((['gstreamer-test1-dev', 'gstreamer-runtime'], [], []), requires)

        for p in [self.store.get_package(x[0]) for x in expected]:
            p.has_devel_package = True
        requires = self.packager.get_meta_requires(PackageType.DEVEL, '-dev')
        expected = (
            ['gstreamer-test1-dev', 'gstreamer-runtime'],
            ['gstreamer-test3-dev'],
            ['gstreamer-test-bindings-dev'],
        )
        self.assertEqual(expected, requires)

    def testPackDeps(self):
        expected = sorted(['gstreamer-test-bindings', 'gstreamer-test2', 'gstreamer-test3', 'gstreamer-test1'])
        self.packager = LoggerPackager(self.config, self.store.get_package('gstreamer-runtime'), self.store)
        self.packager.devel = False
        self.packager.force = False
        global packed
        packed = []
        self.packager.pack_deps('', '', True)
        self.assertEqual(sorted(packed), expected)
        packed = []

        self.packager.devel = False
        self.packager.pack_deps('', '', True)
        self.assertEqual(sorted(packed), expected)
        packed = []

    def testPack(self):
        self.packager = DummyPackager(self.config, self.store.get_package('gstreamer-runtime'), self.store)
        paths = self.packager.pack('', False, True, True, False, None)
        self.assertTrue(os.path.exists('gstreamer-runtime-stamp'))
        os.remove('gstreamer-runtime-stamp')
        self.assertEqual(paths, ['test'])

        self.packager = DummyPackager(self.config, self.store.get_package('gstreamer-test1'), self.store)
        paths = self.packager.pack('', False, True, True, False, None)
        self.assertTrue(os.path.exists('gstreamer-test1-stamp'))
        os.remove('gstreamer-test1-stamp')
        self.assertEqual(paths, ['test'])
