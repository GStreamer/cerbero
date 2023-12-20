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
import io

from cerbero.build import recipe
from cerbero.config import Platform
from cerbero.packages import package
from cerbero.packages.wix import MergeModule
from cerbero.utils import etree
from test.test_build_common import create_cookbook
from test.test_packages_common import create_store
from test.test_common import DummyConfig


class Recipe1(recipe.Recipe):
    name = 'recipe-test'
    files_misc = [
        'bin/test.exe',
        'bin/test2.exe',
        'bin/test3.exe',
        'README',
        'lib/libfoo.dll',
        'lib/gstreamer-0.10/libgstplugins.dll',
    ]


class Package(package.Package):
    name = 'gstreamer-test'
    shortdesc = 'GStreamer Test'
    longdesc = 'test'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'
    files = ['recipe-test:misc']


MERGE_MODULE = """\
<?xml version="1.0" ?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
	<Module Id="_gstreamer_test" Language="1033" Version="1.0">
		<Package Comments="test" Description="GStreamer Test" Id="1" Manufacturer="GStreamer Project"/>
		<Directory Id="TARGETDIR" Name="SourceDir">
			<Component Guid="1" Id="_readme">
				<File Id="_readme_1" Name="README" Source="z:\\\\\\test\\\\README"/>
			</Component>
			<Directory Id="_bin" Name="bin">
				<Component Guid="1" Id="_test.exe">
					<File Id="_testexe" Name="test.exe" Source="z:\\\\\\test\\\\bin\\\\test.exe"/>
				</Component>
				<Component Guid="1" Id="_test2.exe">
					<File Id="_test2exe" Name="test2.exe" Source="z:\\\\\\test\\\\bin\\\\test2.exe"/>
				</Component>
				<Component Guid="1" Id="_test3.exe">
					<File Id="_test3exe" Name="test3.exe" Source="z:\\\\\\test\\\\bin\\\\test3.exe"/>
				</Component>
			</Directory>
			<Directory Id="_lib" Name="lib">
				<Directory Id="_gstreamer_0.10" Name="gstreamer-0.10">
					<Component Guid="1" Id="_libgstplugins.dll">
						<File Id="_libgstpluginsdll" Name="libgstplugins.dll" Source="z:\\\\\\test\\\\lib\\\\gstreamer-0.10\\\\libgstplugins.dll"/>
					</Component>
				</Directory>
				<Component Guid="1" Id="_libfoo.dll">
					<File Id="_libfoodll" Name="libfoo.dll" Source="z:\\\\\\test\\\\lib\\\\libfoo.dll"/>
				</Component>
			</Directory>
		</Directory>
	</Module>
</Wix>
"""


class MergeModuleTest(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        cb = create_cookbook(self.config)
        store = create_store(self.config)
        cb.add_recipe(Recipe1(self.config))
        self.package = Package(self.config, store, cb)
        self.mergemodule = MergeModule(self.config, self.package.files_list(), self.package)

    def test_add_root(self):
        self.mergemodule._add_root()
        self.assertEqual(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi" />', etree.tostring(self.mergemodule.root)
        )

    def test_add_module(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.assertEqual(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
            '<Module Id="_gstreamer_test" Language="1033" Version="1.0" />'
            '</Wix>',
            etree.tostring(self.mergemodule.root),
        )

    def test_add_package(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.mergemodule._add_package()
        self.assertEqual(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
            '<Module Id="_gstreamer_test" Language="1033" Version="1.0">'
            '<Package Comments="test" Description="GStreamer Test" Id="1" '
            'Manufacturer="GStreamer Project" />'
            '</Module>'
            '</Wix>',
            etree.tostring(self.mergemodule.root),
        )

    def test_add_root_dir(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.mergemodule._add_package()
        self.mergemodule._add_root_dir()
        self.assertEqual(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
            '<Module Id="_gstreamer_test" Language="1033" Version="1.0">'
            '<Package Comments="test" Description="GStreamer Test" Id="1" '
            'Manufacturer="GStreamer Project" />'
            '<Directory Id="TARGETDIR" Name="SourceDir" />'
            '</Module>'
            '</Wix>',
            etree.tostring(self.mergemodule.root),
        )

    def test_add_directory(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.mergemodule._add_package()
        self.mergemodule._add_root_dir()
        self.assertEqual(len(self.mergemodule._dirnodes), 1)
        self.assertEqual(self.mergemodule._dirnodes[''], self.mergemodule.rdir)
        self.mergemodule._add_directory('lib/gstreamer-0.10')
        self.assertEqual(len(self.mergemodule._dirnodes), 3)
        self.assertTrue('lib' in self.mergemodule._dirnodes)
        self.assertTrue('lib/gstreamer-0.10' in self.mergemodule._dirnodes)
        self.mergemodule._add_directory('bin')
        self.assertEqual(len(self.mergemodule._dirnodes), 4)
        self.assertTrue('bin' in self.mergemodule._dirnodes)

    def test_add_file(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.mergemodule._add_package()
        self.mergemodule._add_root_dir()
        self.assertEqual(len(self.mergemodule._dirnodes), 1)
        self.assertEqual(self.mergemodule._dirnodes[''], self.mergemodule.rdir)
        self.mergemodule._add_file('bin/gst-inspect-0.10.exe')
        self.assertEqual(len(self.mergemodule._dirnodes), 2)
        self.assertTrue('bin' in self.mergemodule._dirnodes)
        self.assertTrue('gstreamer-0.10.exe' not in self.mergemodule._dirnodes)
        self.mergemodule._add_file('bin/gst-launch-0.10.exe')
        self.assertEqual(len(self.mergemodule._dirnodes), 2)
        self.assertTrue('bin' in self.mergemodule._dirnodes)
        self.assertTrue('gstreamer-0.10.exe' not in self.mergemodule._dirnodes)

    def test_render_xml(self):
        self.config.platform = Platform.WINDOWS
        self.mergemodule._get_uuid = lambda: '1'
        self.mergemodule.fill()
        tmp = io.StringIO()
        self.mergemodule.write(tmp)
        # self._compstr(tmp.getvalue(), MERGE_MODULE)
        self.assertEqual(MERGE_MODULE, tmp.getvalue())

    def _compstr(self, str1, str2):
        str1 = str1.split('\n')
        str2 = str2.split('\n')
        for i in range(len(str1)):
            if str1[i] != str2[i]:
                print(str1[i])
                print(str2[i])
                print('')


class InstallerTest(unittest.TestCase):
    def setUp(self):
        pass

    def testAddRoot(self):
        pass

    def testAddProduct(self):
        pass

    def testAddPackage(self):
        pass

    def testAddInstallDir(self):
        pass

    def testAddUIProps(self):
        pass

    def testAddMedia(self):
        pass

    def testAddMergeModules(self):
        pass

    def testRender(self):
        pass
