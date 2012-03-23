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
from cerbero.tests.test_packages_common import Package1
from cerbero.utils import shell


class DummyConfig(object):

    def __init__(self, prefix, target_platform):
        self.prefix = prefix
        self.target_platform = target_platform


class PackageTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        win32config = DummyConfig(self.tmp, Platform.WINDOWS)
        linuxconfig = DummyConfig(self.tmp, Platform.LINUX)
        self.win32package = Package1(win32config)
        self.linuxpackage = Package1(linuxconfig)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _add_files(self):
        bindir = os.path.join(self.tmp, 'bin')
        libdir = os.path.join(self.tmp, 'lib')
        os.makedirs(bindir)
        os.makedirs(libdir)
        shell.call('touch '
            '%(bindir)s/libgstreamer.dll '
            '%(bindir)s/libgstreamer-win32.dll '
            '%(libdir)s/libgstreamer.so.1 '
            '%(libdir)s/libgstreamer-x11.so.1 ' %
            {'bindir': bindir, 'libdir':libdir})

    def test_list_files(self):
        win32files = ['README', 'libexec/gstreamer-0.10/pluginsloader.exe',
                      'windows']
        linuxfiles = ['README', 'libexec/gstreamer-0.10/pluginsloader',
                      'linux']

        self.assertEquals(self.win32package._get_files(), win32files)
        self.assertEquals(self.linuxpackage._get_files(), linuxfiles)

    def test_list_binaries(self):
        win32files = ['bin/gst-launch.exe', 'bin/windows.exe']
        linuxfiles = ['bin/gst-launch', 'bin/linux']

        self.assertEquals(self.win32package._get_binaries(), win32files)
        self.assertEquals(self.linuxpackage._get_binaries(), linuxfiles)

    def test_list_libraries(self):
        win32files = ['bin/libgstreamer.dll', 'bin/libgstreamer-win32.dll']
        linuxfiles = ['lib/libgstreamer.so.1', 'lib/libgstreamer-x11.so.1']
        self._add_files()
        self.assertEquals(self.win32package._get_libraries(), win32files)
        self.assertEquals(self.linuxpackage._get_libraries(), linuxfiles)

    def test_get_all_files(self):
        win32files = ['README', 'libexec/gstreamer-0.10/pluginsloader.exe',
                      'windows']
        linuxfiles = ['README', 'libexec/gstreamer-0.10/pluginsloader',
                      'linux']
        win32files += ['bin/gst-launch.exe', 'bin/windows.exe']
        linuxfiles += ['bin/gst-launch', 'bin/linux']
        win32files += ['bin/libgstreamer.dll', 'bin/libgstreamer-win32.dll']
        linuxfiles += ['lib/libgstreamer.so.1', 'lib/libgstreamer-x11.so.1']
        self._add_files()
        self.assertEquals(self.win32package.get_files_list(),
                          sorted(win32files))
        self.assertEquals(self.linuxpackage.get_files_list(),
                          sorted(linuxfiles))
