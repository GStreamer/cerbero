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
    def assertFileContent(self, info, content):
        tmp = tempfile.NamedTemporaryFile('w+t')
        info.save(tmp.name)
        with open(tmp.name, 'r') as f:
            result = f.read()
        self.assertEqual(result, content)

    def testFormatProperty(self):
        info_plist = InfoPlist('test', 'test.org', '1.0', 'Test package', '10.12')
        content = INFO_PLIST_TPL % info_plist._get_properties()
        self.assertFileContent(info_plist, content)

    def testFormatPropertyWithIcon(self):
        info_plist = InfoPlist('test', 'test.org', '1.0', 'Test package', '10.12', icon='test.ico')
        content = INFO_PLIST_TPL % info_plist._get_properties()
        self.assertFileContent(info_plist, content)

    def testFrameworkPackageType(self):
        fmwk = FrameworkPlist('test', 'test.org', '1.0', 'Test package', '10.12')
        content = INFO_PLIST_TPL % fmwk._get_properties()
        self.assertFileContent(fmwk, content)

    def testApplicationPackageType(self):
        app = ApplicationPlist('test', 'test.org', '1.0', 'Test package', '10.12')
        content = INFO_PLIST_TPL % {'ptype': 'APPL', 'icon': '', **app._get_properties()}
        self.assertFileContent(app, content)
