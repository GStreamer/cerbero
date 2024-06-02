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
import shutil

from cerbero.build import recipe
from cerbero.config import Platform
from cerbero.packages import package
from cerbero.packages.wix import MergeModule
from cerbero.utils import shell, etree
from test.test_build_common import create_cookbook
from test.test_packages_common import create_store
from test.test_common import DummyConfig


class Recipe(recipe.Recipe):
    name = 'recipe-test'
    version = '0.0.1'
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
<?xml version='1.0' encoding='utf-8'?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
	<Module Id="_gstreamer_test" Version="1.0.0" Guid="1" Language="1033">
		<SummaryInformation Description="GStreamer Test" Manufacturer="GStreamer Project" />
		<Component Id="_readme" Guid="1">
			<File Id="_readme_1" Name="README" Source="z:%(prefix)s\README" />
		</Component>
		<Directory Id="_bin" Name="bin">
			<Component Id="_test.exe" Guid="1">
				<File Id="_testexe" Name="test.exe" Source="z:%(prefix)s\\bin\\test.exe" />
			</Component>
			<Component Id="_test2.exe" Guid="1">
				<File Id="_test2exe" Name="test2.exe" Source="z:%(prefix)s\\bin\\test2.exe" />
			</Component>
			<Component Id="_test3.exe" Guid="1">
				<File Id="_test3exe" Name="test3.exe" Source="z:%(prefix)s\\bin\\test3.exe" />
			</Component>
		</Directory>
		<Directory Id="_lib" Name="lib">
			<Directory Id="_gstreamer_0.10" Name="gstreamer-0.10">
				<Component Id="_libgstplugins.dll" Guid="1">
					<File Id="_libgstpluginsdll" Name="libgstplugins.dll" Source="z:%(prefix)s\\lib\\gstreamer-0.10\\libgstplugins.dll" />
				</Component>
			</Directory>
			<Component Id="_libfoo.dll" Guid="1">
				<File Id="_libfoodll" Name="libfoo.dll" Source="z:%(prefix)s\\lib\\libfoo.dll" />
			</Component>
		</Directory>
	</Module>
</Wix>"""


class MergeModuleTest(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.tmp = tempfile.mkdtemp()
        self.config = DummyConfig()
        self.config.prefix = self.tmp
        cb = create_cookbook(self.config)
        store = create_store(self.config)
        cb.add_recipe(Recipe(self.config, {}))
        self.package = Package(self.config, store, cb)
        store.add_package(self.package)
        self.package.load()
        self.addFiles()
        self.mergemodule = MergeModule(self.config, self.package.files_list(), self.package)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def addFiles(self):
        bindir = os.path.join(self.tmp, 'bin')
        libdir = os.path.join(self.tmp, 'lib', 'gstreamer-0.10')
        os.makedirs(bindir)
        os.makedirs(libdir)
        shell.call(
            'touch '
            'bin/test.exe '
            'bin/test2.exe '
            'bin/test3.exe '
            'README '
            'lib/libfoo.dll '
            'lib/gstreamer-0.10/libgstplugins.dll ',
            self.tmp,
        )

    def test_add_root(self):
        self.mergemodule._add_root()
        self.assertEqual(
            '<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs" />',
            etree.tostring(self.mergemodule.root).decode('utf-8'),
        )

    def test_add_module(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.assertEqual(
            '<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">'
            '<Module Id="_gstreamer_test" Version="1.0.0" Guid="1" Language="1033">'
            '<SummaryInformation Description="GStreamer Test" Manufacturer="GStreamer Project" /></Module>'
            '</Wix>',
            etree.tostring(self.mergemodule.root).decode('utf-8'),
        )

    def test_add_package(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.assertEqual(
            '<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">'
            '<Module Id="_gstreamer_test" Version="1.0.0" Guid="1" Language="1033">'
            '<SummaryInformation Description="GStreamer Test" Manufacturer="GStreamer Project" />'
            '</Module>'
            '</Wix>',
            etree.tostring(self.mergemodule.root).decode('utf-8'),
        )

    def test_add_directory(self):
        self.mergemodule._add_root()
        self.mergemodule._add_module()
        self.assertEqual(len(self.mergemodule._dirnodes), 1)
        self.assertEqual(self.mergemodule._dirnodes[''], self.mergemodule.module)
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
        self.assertEqual(len(self.mergemodule._dirnodes), 1)
        self.assertEqual(self.mergemodule._dirnodes[''], self.mergemodule.module)
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
        tmp = tempfile.NamedTemporaryFile('w+t')
        self.mergemodule.write(tmp.name)
        expected = MERGE_MODULE % {'prefix': self.tmp.replace('/', '\\')}
        self.assertEqual(expected, tmp.read())


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
