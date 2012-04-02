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

from cerbero.config import Platform
from cerbero.tests.test_packages_common import Package1
from cerbero.tests.test_build_common import create_cookbook, add_files
from cerbero.tests.test_common import DummyConfig


class Config(DummyConfig):

    def __init__(self, tmp, platform):
        self.prefix = tmp
        self.target_platform = platform


class PackageTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        win32config = Config(self.tmp, Platform.WINDOWS)
        linuxconfig = Config(self.tmp, Platform.LINUX)
        self.win32package = Package1(win32config, create_cookbook(win32config))
        self.linuxpackage = Package1(linuxconfig, create_cookbook(linuxconfig))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testParseFiles(self):
        self.assertEquals(self.win32package._recipes_files['recipe1'],
                ['misc', 'libs', 'bins'])
        self.assertEquals(self.win32package._recipes_files['recipe5'], ['libs'])

    def testListRecipesDeps(self):
        self.assertEquals(self.win32package.recipes_dependencies(),
                          ['recipe1', 'recipe5'])
        self.assertEquals(self.linuxpackage.recipes_dependencies(),
                          ['recipe1'])

    def testFilesList(self):
        add_files(self.tmp)
        winfiles = ['README', 'bin/gst-launch.exe', 'bin/libgstreamer-win32.dll',
                'bin/libgstreamer-0.10.dll', 'bin/windows.exe',
                'libexec/gstreamer-0.10/pluginsloader.exe',
                'windows', 'bin/libtest.dll']
        linuxfiles = ['README', 'bin/gst-launch', 'bin/linux',
                'lib/libgstreamer-x11.so.1', 'lib/libgstreamer-0.10.so.1',
                'libexec/gstreamer-0.10/pluginsloader', 'linux']

        self.assertEquals(sorted(winfiles),
            sorted(self.win32package.files_list()))
        self.assertEquals(sorted(linuxfiles),
            sorted(self.linuxpackage.files_list()))

    def testDevelFilesList(self):
        add_files(self.tmp)
        devfiles = ['lib/libgstreamer-0.10.dll.a', 'lib/libgstreamer-0.10.a',
                    'lib/libgstreamer-0.10.la']
        linuxdevfiles = devfiles + ['lib/libgstreamer-0.10.so',
            'lib/libgstreamer-x11.a', 'lib/libgstreamer-x11.la',
            'lib/libgstreamer-x11.so']
        windevfiles = devfiles + ['lib/libgstreamer-win32.a',
            'lib/libgstreamer-win32.dll.a', 'lib/libgstreamer-win32.la',
            'lib/libtest.a', 'lib/libtest.dll.a', 'lib/libtest.la']

        self.assertEquals(sorted(windevfiles), self.win32package.devel_files_list())
        self.assertEquals(sorted(linuxdevfiles), self.linuxpackage.devel_files_list())
