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

from cerbero.build import filesprovider
from cerbero.config import Platform
from cerbero.tests.test_build_common import add_files


class DummyConfig(object):

    def __init__(self, prefix, target_platform):
        self.prefix = prefix
        self.target_platform = target_platform


class FilesProvider(filesprovider.FilesProvider):

    files_misc = ['README', 'libexec/gstreamer-0.10/pluginsloader%(bext)s']
    files_libs = ['libgstreamer']
    files_bins = ['gst-launch']
    files_devel = ['include/gstreamer.h']
    files_bins_platform = {
            Platform.WINDOWS: ['windows'],
            Platform.LINUX: ['linux']}
    files_libs_platform = {
            Platform.WINDOWS: ['libgstreamer-win32'],
            Platform.LINUX: ['libgstreamer-x11']}


class PackageTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        win32config = DummyConfig(self.tmp, Platform.WINDOWS)
        linuxconfig = DummyConfig(self.tmp, Platform.LINUX)
        self.win32recipe = FilesProvider(win32config)
        self.linuxrecipe = FilesProvider(linuxconfig)

        self.winbin = ['bin/gst-launch.exe', 'bin/windows.exe']
        self.linuxbin = ['bin/gst-launch', 'bin/linux']
        self.winlib = ['bin/libgstreamer.dll', 'bin/libgstreamer-win32.dll']
        self.linuxlib = ['lib/libgstreamer.so.1', 'lib/libgstreamer-x11.so.1']
        self.winmisc = ['README', 'libexec/gstreamer-0.10/pluginsloader.exe']
        self.linuxmisc = ['README', 'libexec/gstreamer-0.10/pluginsloader']
        self.devfiles = ['include/gstreamer.h', 'lib/libgstreamer.a',
                'lib/libgstreamer-win32.a', 'lib/libgstreamer-win32.so',
                'lib/libgstreamer-win32.la', 'lib/libgstreamer.la',
                'lib/libgstreamer-x11.a', 'lib/libgstreamer-x11.la',
                'lib/libgstreamer-x11.so', 'lib/libgstreamer.so']

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testFilesCategories(self):
        self.assertEquals(sorted(['bins', 'libs', 'misc', 'devel']),
                self.win32recipe._files_categories())

    def testListBinaries(self):
        self.assertEquals(self.win32recipe.files_list_by_category('bins'),
                sorted(self.winbin))
        self.assertEquals(self.linuxrecipe.files_list_by_category('bins'),
                sorted(self.linuxbin))

    def testListLibraries(self):
        add_files(self.tmp)
        self.assertEquals(self.win32recipe.files_list_by_category('libs'),
                sorted(self.winlib))
        self.assertEquals(self.linuxrecipe.files_list_by_category('libs'),
                sorted(self.linuxlib))

    def testDevelFiles(self):
        add_files(self.tmp)
        self.assertEquals(self.win32recipe.devel_files_list(),
                sorted(self.devfiles))

    def testDistFiles(self):
        win32files = self.winlib + self.winbin + self.winmisc
        linuxfiles = self.linuxlib + self.linuxbin + self.linuxmisc
        add_files(self.tmp)
        self.assertEquals(self.win32recipe.dist_files_list(), sorted(win32files))
        self.assertEquals(self.linuxrecipe.dist_files_list(), sorted(linuxfiles))

    def testGetAllFiles(self):
        win32files = self.winlib + self.winbin + self.winmisc + self.devfiles
        linuxfiles = self.linuxlib + self.linuxbin + self.linuxmisc + self.devfiles
        add_files(self.tmp)
        self.assertEquals(self.win32recipe.files_list(), sorted(win32files))
        self.assertEquals(self.linuxrecipe.files_list(), sorted(linuxfiles))
