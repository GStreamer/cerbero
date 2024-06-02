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
import tempfile

from cerbero.ide.xcode.xcconfig import XCConfig


XCCONFIG = """
ALWAYS_SEARCH_USER_PATHS = YES
USER_HEADER_SEARCH_PATHS = /usr/include/gstreamer-0.10\
 /usr/include/glib-2.0 /usr/lib/glib-2.0/include\
 /usr/include/libxml2
LIBRARY_SEARCH_PATHS = 
OTHER_LDFLAGS =  -lgstreamer-0.10 \
-lgobject-2.0 -lgmodule-2.0 -lrt -lgthread-2.0 -lrt -lglib-2.0 -lxml2
"""


class TestPkgConfig(unittest.TestCase):
    def setUp(self):
        pc_path = os.path.join(os.path.dirname(__file__), 'pkgconfig')
        os.environ['PKG_CONFIG_LIBDIR'] = pc_path
        os.environ['PKG_CONFIG_PATH'] = pc_path

    def testFill(self):
        xcconfig = XCConfig('gstreamer-0.10')
        expected = {
            'libs': ' -lgstreamer-0.10 -lgobject-2.0 -lgmodule-2.0 -lrt -lgthread-2.0 -lrt -lglib-2.0 -lxml2',
            'hsp': '/usr/include/gstreamer-0.10 /usr/include/glib-2.0 '
            '/usr/lib/glib-2.0/include '
            '/usr/include/libxml2',
            'lsp': '',
        }
        self.assertEqual(expected, xcconfig._fill())

    def testXCConfig(self):
        tmp = tempfile.NamedTemporaryFile()
        xcconfig = XCConfig('gstreamer-0.10')
        xcconfig.create(tmp.name)
        with open(tmp.name, 'r') as f:
            self.assertEqual(f.read(), XCCONFIG)
