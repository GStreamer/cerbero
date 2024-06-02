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
import shutil
import unittest
import tempfile

from cerbero.config import Platform
from cerbero.packages import PackageType
from cerbero.packages.osx.packager import OSXPackage
from cerbero.utils import shell
from test.test_packages_common import create_store
from test.test_common import DummyConfig


class PackageMakerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.config = DummyConfig()
        self.config.prefix = self.tmp
        self.config.target_platform = Platform.LINUX
        self.store = create_store(self.config)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testCreateBundle(self):
        self._add_files()
        p = self.store.get_package('gstreamer-test1')
        self.files = p.files_list()
        packager = OSXPackage(self.config, p, self.store)
        files = OSXPackage.files_list(packager, PackageType.RUNTIME, False)
        tmpdest = packager._create_bundle(files, PackageType.RUNTIME)[1]
        bundlefiles = shell.check_output('find . -type f ', tmpdest).split('\n')
        bundlefiles = sorted([f[2:] for f in bundlefiles])[1:]
        self.assertEqual(bundlefiles, self.files)
        shutil.rmtree(tmpdest)

    def _add_files(self):
        bindir = os.path.join(self.tmp, 'bin')
        libdir = os.path.join(self.tmp, 'lib')
        os.makedirs(bindir)
        os.makedirs(libdir)
        os.makedirs(os.path.join(self.tmp, 'libexec', 'gstreamer-0.10'))
        shell.call(
            'touch '
            'README '
            'linux '
            'libexec/gstreamer-0.10/pluginsloader '
            'bin/gst-launch '
            'bin/linux '
            'lib/libgstreamer-0.10.so.1 '
            'lib/libgstreamer-x11.so.1 '
            'lib/notincluded1 '
            'notincluded2 ',
            self.tmp,
        )
