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


def to_config_path(config, paths):
    return [x % {'libdir': config.rel_libdir} for x in paths]


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        win32config = Config(self.tmp, Platform.WINDOWS)
        win32config.variants.override(['nodebug'])
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
        self.linuxlib = to_config_path(
            linuxconfig, ['%(libdir)s/*libgstreamer-0.10*.so*', '%(libdir)s/*libgstreamer-x11*.so*']
        )
        self.winmisc = ['README', 'libexec/gstreamer-0.10/pluginsloader.exe']
        self.linuxmisc = ['README', 'libexec/gstreamer-0.10/pluginsloader']
        devfiles = [
            'include/gstreamer.h',
            '%(libdir)s/libgstreamer-0.10.a',
            '%(libdir)s/libgstreamer-0.10.la',
        ]

        self.windevfiles = to_config_path(
            win32config,
            devfiles
            + [
                '%(libdir)s/libgstreamer-win32.a',
                '%(libdir)s/libgstreamer-win32.la',
                '%(libdir)s/libgstreamer-win32.dll.a',
                '%(libdir)s/libgstreamer-win32.def',
                '%(libdir)s/gstreamer-win32.lib',
                '%(libdir)s/libgstreamer-0.10.dll.a',
                '%(libdir)s/libgstreamer-0.10.def',
                '%(libdir)s/gstreamer-0.10.lib',
            ],
        )
        self.lindevfiles = to_config_path(
            linuxconfig,
            devfiles
            + [
                '%(libdir)s/libgstreamer-0.10.so',
                '%(libdir)s/libgstreamer-x11.a',
                '%(libdir)s/libgstreamer-x11.la',
                '%(libdir)s/libgstreamer-x11.so',
            ],
        )

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testFilesCategories(self):
        self.assertEqual(sorted(['bins', 'libs', 'misc', 'devel']), self.win32recipe._files_categories())

    def testListBinaries(self):
        self.assertEqual(self.win32recipe.files_list_by_category('bins', False), sorted(self.winbin))
        self.assertEqual(self.linuxrecipe.files_list_by_category('bins', False), sorted(self.linuxbin))
        self.assertEqual(self.win32recipe.files_list_by_category('bins'), [])
        self.assertEqual(self.linuxrecipe.files_list_by_category('bins'), [])

    def testListLibraries(self):
        self.assertEqual(self.win32recipe.files_list_by_category('libs', False), sorted(self.winlib))
        self.assertEqual(self.linuxrecipe.files_list_by_category('libs', False), sorted(self.linuxlib))
        self.assertEqual(self.win32recipe.files_list_by_category('libs'), [])
        self.assertEqual(self.linuxrecipe.files_list_by_category('libs'), [])

    def testDevelFiles(self):
        self.assertEqual(self.win32recipe.devel_files_list(False), sorted(self.windevfiles))
        self.assertEqual(self.linuxrecipe.devel_files_list(False), sorted(self.lindevfiles))
        self.assertEqual(self.win32recipe.devel_files_list(), [])
        self.assertEqual(self.linuxrecipe.devel_files_list(), [])

    def testDistFiles(self):
        win32files = self.winlib + self.winbin + self.winmisc
        linuxfiles = self.linuxlib + self.linuxbin + self.linuxmisc
        self.assertEqual(self.win32recipe.dist_files_list(False), sorted(win32files))
        self.assertEqual(self.linuxrecipe.dist_files_list(False), sorted(linuxfiles))
        self.assertEqual(self.win32recipe.dist_files_list(), [])
        self.assertEqual(self.linuxrecipe.dist_files_list(), [])

    def testGetAllFiles(self):
        win32files = self.winlib + self.winbin + self.winmisc + self.windevfiles
        linuxfiles = self.linuxlib + self.linuxbin + self.linuxmisc + self.lindevfiles
        self.assertEqual(self.win32recipe.files_list(False), sorted(win32files))
        self.assertEqual(self.linuxrecipe.files_list(False), sorted(linuxfiles))
        self.assertEqual(self.win32recipe.files_list(), [])
        self.assertEqual(self.linuxrecipe.files_list(), [])
