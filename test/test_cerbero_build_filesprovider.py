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

from cerbero.build import recipe
from cerbero.config import Platform, License
from test.test_build_common import add_files
from test.test_common import DummyConfig


class Config(DummyConfig):
    def __init__(self, tmp, platform):
        super().__init__()
        self.prefix = tmp
        self.target_platform = platform
        self.env['DLLTOOL'] = 'dlltool'


class Recipe(recipe.Recipe):
    name = 'filesprovider-test'
    version = '0.0.1'
    files_misc = ['README', 'libexec/gstreamer-0.10/pluginsloader%(bext)s']
    files_libs = ['libgstreamer-0.10']
    files_bins = ['gst-launch']
    files_devel = ['include/gstreamer.h']
    licenses_devel = [License.LGPLv2_1Plus]
    platform_files_bins = {Platform.WINDOWS: ['windows'], Platform.LINUX: ['linux']}
    platform_files_libs = {Platform.WINDOWS: ['libgstreamer-win32'], Platform.LINUX: ['libgstreamer-x11']}


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        win32config = Config(self.tmp, Platform.WINDOWS)
        linuxconfig = Config(self.tmp, Platform.LINUX)
        # FIXME config.py should initialize this
        win32config.mingw_env_for_toolchain = dict()
        win32config.mingw_env_for_build_system = dict()
        win32config.msvc_env_for_toolchain = dict()
        win32config.msvc_env_for_build_system = dict()

        self.win32recipe = Recipe(win32config, {})
        self.linuxrecipe = Recipe(linuxconfig, {})

        self.winbin = ['bin/gst-launch.exe', 'bin/windows.exe']
        self.linuxbin = ['bin/gst-launch', 'bin/linux']
        self.winlib = ['bin/libgstreamer-0.10.dll', 'bin/libgstreamer-win32.dll']
        self.linuxlib = ['lib/libgstreamer-0.10.so.1', 'lib/libgstreamer-x11.so.1']
        self.winmisc = ['README', 'libexec/gstreamer-0.10/pluginsloader.exe']
        self.linuxmisc = ['README', 'libexec/gstreamer-0.10/pluginsloader']
        devfiles = ['include/gstreamer.h', 'lib/libgstreamer-0.10.a', 'lib/libgstreamer-0.10.la']

        self.windevfiles = devfiles + [
            'lib/libgstreamer-win32.a',
            'lib/libgstreamer-win32.la',
            'lib/libgstreamer-win32.dll.a',
            'lib/libgstreamer-win32.def',
            'lib/gstreamer-win32.lib',
            'lib/libgstreamer-0.10.dll.a',
            'lib/libgstreamer-0.10.def',
            'lib/gstreamer-0.10.lib',
        ]
        self.lindevfiles = devfiles + [
            'lib/libgstreamer-0.10.so',
            'lib/libgstreamer-x11.a',
            'lib/libgstreamer-x11.la',
            'lib/libgstreamer-x11.so',
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testFilesCategories(self):
        self.assertEqual(sorted(['bins', 'libs', 'misc', 'devel']), self.win32recipe._files_categories())

    def testListBinaries(self):
        self.assertEqual(self.win32recipe.files_list_by_category('bins'), sorted(self.winbin))
        self.assertEqual(self.linuxrecipe.files_list_by_category('bins'), sorted(self.linuxbin))

    def testListLibraries(self):
        add_files(self.tmp)
        self.assertEqual(self.win32recipe.files_list_by_category('libs'), sorted(self.winlib))
        self.assertEqual(self.linuxrecipe.files_list_by_category('libs'), sorted(self.linuxlib))

    def testDevelFiles(self):
        add_files(self.tmp)
        self.assertEqual(self.win32recipe.devel_files_list(), sorted(self.windevfiles))
        self.assertEqual(self.linuxrecipe.devel_files_list(), sorted(self.lindevfiles))

    def testDistFiles(self):
        win32files = self.winlib + self.winbin + self.winmisc
        linuxfiles = self.linuxlib + self.linuxbin + self.linuxmisc
        add_files(self.tmp)
        self.assertEqual(self.win32recipe.dist_files_list(), sorted(win32files))
        self.assertEqual(self.linuxrecipe.dist_files_list(), sorted(linuxfiles))

    def testGetAllFiles(self):
        win32files = self.winlib + self.winbin + self.winmisc + self.windevfiles
        linuxfiles = self.linuxlib + self.linuxbin + self.linuxmisc + self.lindevfiles
        add_files(self.tmp)
        self.assertEqual(self.win32recipe.files_list(), sorted(win32files))
        self.assertEqual(self.linuxrecipe.files_list(), sorted(linuxfiles))
