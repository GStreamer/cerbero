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
import shutil
import tarfile
import tempfile

from cerbero.packages.disttarball import DistTarball
from test.test_packages_common import create_store
from test.test_common import DummyConfig
from test.test_build_common import add_files


class DistTarballTest(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.tmp = tempfile.mkdtemp()
        self.config.prefix = self.tmp
        self.store = create_store(self.config)
        self.package = self.store.get_package('gstreamer-runtime')
        self.packager = DistTarball(self.config, self.package, self.store)
        add_files(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testRuntimePackage(self):
        # Creates one package with the runtime files
        filenames = self.packager.pack(self.tmp, devel=False)
        self.assertEqual(len(filenames), 1)
        tar = tarfile.open(filenames[0], 'r:xz')
        tarfiles = sorted([x.path for x in tar.getmembers()])
        self.assertEqual(tarfiles, self.package.files_list())

    def testRuntimeAndDevelPackages(self):
        # Creates 2 packages, one with the runtime files a second one with the
        # devel files
        filenames = self.packager.pack(self.tmp, devel=True)
        self.assertEqual(len(filenames), 2)
        tar = tarfile.open(filenames[0], 'r:xz')
        tarfiles = sorted([x.path for x in tar.getmembers()])
        self.assertEqual(tarfiles, self.package.files_list())
        tar = tarfile.open(filenames[1], 'r:xz')
        tarfiles = sorted([x.path for x in tar.getmembers()])
        self.assertEqual(tarfiles, self.package.devel_files_list())

    def testRuntimeWithDevelPackage(self):
        # Creates 1 package, with the runtime files and the devel files
        filenames = self.packager.pack(self.tmp, devel=True, split=False)
        self.assertEqual(len(filenames), 1)
        tar = tarfile.open(filenames[0], 'r:xz')
        tarfiles = sorted([x.path for x in tar.getmembers()])
        self.assertEqual(tarfiles, self.package.all_files_list())
