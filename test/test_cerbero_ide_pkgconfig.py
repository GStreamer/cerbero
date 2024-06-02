#!/usr/bin/env python3
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

from cerbero.ide.pkgconfig import PkgConfig


class TestPkgConfig(unittest.TestCase):
    def setUp(self):
        pc_path = os.path.join(os.path.dirname(__file__), 'pkgconfig')
        os.environ['PKG_CONFIG_LIBDIR'] = pc_path
        os.environ['PKG_CONFIG_PATH'] = pc_path
        self.pkgconfig = PkgConfig('gstreamer-0.10')
        self.pkgconfig2 = PkgConfig('gstreamer-0.10', False)

    def testListAll(self):
        expected = [
            'gobject-2.0',
            'gmodule-2.0',
            'libxml-2.0',
            'gthread-2.0',
            'glib-2.0',
            'gmodule-no-export-2.0',
            'gstreamer-0.10',
        ]
        self.assertEqual(sorted(PkgConfig.list_all()), sorted(expected))

    def testIncludeDirs(self):
        expected = [
            '/usr/include/gstreamer-0.10',
            '/usr/include/glib-2.0',
            '/usr/lib/glib-2.0/include',
            '/usr/include/libxml2',
        ]
        self.assertEqual(self.pkgconfig.include_dirs(), expected)
        expected = ['/usr/include/gstreamer-0.10']
        self.assertEqual(self.pkgconfig2.include_dirs(), expected)

    def testCFlags(self):
        expected = ['-pthread']
        self.assertEqual(self.pkgconfig.cflags(), expected)
        expected = []
        self.assertEqual(self.pkgconfig2.cflags(), expected)

    def testLibrariesDir(self):
        expected = []
        self.assertEqual(self.pkgconfig.libraries_dirs(), expected)
        expected = []
        self.assertEqual(self.pkgconfig2.libraries_dirs(), expected)

    def testLibraries(self):
        expected = ['gstreamer-0.10', 'gobject-2.0', 'gmodule-2.0', 'rt', 'gthread-2.0', 'rt', 'glib-2.0', 'xml2']
        self.assertEqual(self.pkgconfig.libraries(), expected)
        expected = ['gstreamer-0.10']
        self.assertEqual(self.pkgconfig2.libraries(), expected)

    def testRequires(self):
        expected = ['glib-2.0', 'gobject-2.0', 'gmodule-no-export-2.0', 'gthread-2.0', 'libxml-2.0']
        self.assertEqual(self.pkgconfig.requires(), expected)
        self.assertEqual(self.pkgconfig2.requires(), expected)

    def testPrefix(self):
        self.assertEqual(self.pkgconfig.prefix(), '/usr')
        self.assertEqual(self.pkgconfig2.prefix(), '/usr')
