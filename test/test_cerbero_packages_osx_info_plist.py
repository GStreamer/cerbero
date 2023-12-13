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
import tempfile

from cerbero.packages.osx.info_plist import InfoPlist, FrameworkPlist, ApplicationPlist, INFO_PLIST_TPL


class InfoPlistTest(unittest.TestCase):
    PROPS_TPL = (
        '%(icon)s<key>CFBundleIdentifier</key>\n'
        '<string>test.org</string>\n'
        '<key>CFBundleName</key>\n'
        '<string>test</string>\n'
        '<key>CFBundlePackageGetInfoString</key>\n'
        '<string>Test package</string>\n'
        '<key>CFBundlePackageType</key>\n'
        '<string>%(ptype)s</string>\n'
        '<key>CFBundleVersion</key>\n'
        '<string>1.0</string>'
    )

    def setUp(self):
        self.info_plist = InfoPlist('test', 'test.org', '1.0', 'Test package')

    def testFormatProperty(self):
        self.assertEqual('<key>Key</key>\n<string>Value</string>', self.info_plist._format_property('Key', 'Value'))

    def testGetPropertiesString(self):
        result = self.info_plist._get_properties_string()
        expected = self.PROPS_TPL % {'icon': '', 'ptype': ''}
        self.assertEqual(result, expected)

    def testFrameworkPackageType(self):
        self.info_plist = FrameworkPlist('test', 'test.org', '1.0', 'Test package')
        result = self.info_plist._get_properties_string()
        expected = self.PROPS_TPL % {'ptype': 'FMWK', 'icon': ''}
        self.assertEqual(result, expected)

    def testApplicationPackageType(self):
        self.info_plist = ApplicationPlist('test', 'test.org', '1.0', 'Test package')
        result = self.info_plist._get_properties_string()
        expected = self.PROPS_TPL % {'ptype': 'APPL', 'icon': ''}
        self.assertEqual(result, expected)

    def testGetPropertiesStringWithIcon(self):
        self.info_plist.icon = 'test.ico'
        result = self.info_plist._get_properties_string()
        expected = self.PROPS_TPL % {
            'ptype': '',
            'icon': self.info_plist._format_property('CFBundleIconFile', 'test.ico') + '\n',
        }
        self.info_plist.icon = None
        self.assertEqual(result, expected)

    def testSave(self):
        tmp = tempfile.NamedTemporaryFile()
        self.info_plist.save(tmp.name)
        with open(tmp.name, 'r') as f:
            result = f.read()
        expected = INFO_PLIST_TPL % (
            self.info_plist.BEGIN,
            self.info_plist._get_properties_string(),
            self.info_plist.END,
        )
        self.assertEqual(result, expected)
