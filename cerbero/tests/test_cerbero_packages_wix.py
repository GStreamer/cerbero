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

from cerbero.config import Platform
from cerbero.packages import package
from cerbero.packages.wix import MergeModule
from cerbero.utils import etree


class DummyConfig(object):
    prefix = '/test/'
    target_platform = Platform.WINDOWS
    platform = None
    wix_prefix = ''


class Package(package.Package):

    name = 'gstreamer-test'
    shortdesc = 'GStreamer Test'
    longdesc = 'test'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'
    files = ['bin/test.exe', 'bin/test2.exe', 'bin/test3.exe',
             'README', 'lib/libfoo.dll', 'lib/gstreamer-0.10/libgstplugins.dll']


MERGE_MODULE = \
'''<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi"><Module Id="gstreamer_test" Language="1033" Version="1.0"><Package Comments="test" Description="GStreamer Test" Id="1" Manufacturer="GStreamer Project" /><Directory Id="TARGETDIR" Name="SourceDir"><Component Guid="1" Id="README"><File Id="_test_README" Name="README" Source="/test/README" /></Component><Directory Id="bin" Name="bin"><Component Guid="1" Id="bin_test.exe"><File Id="_test_bin_testexe" Name="test.exe" Source="/test/bin/test.exe" /></Component><Component Guid="1" Id="bin_test2.exe"><File Id="_test_bin_test2exe" Name="test2.exe" Source="/test/bin/test2.exe" /></Component><Component Guid="1" Id="bin_test3.exe"><File Id="_test_bin_test3exe" Name="test3.exe" Source="/test/bin/test3.exe" /></Component></Directory><Directory Id="lib" Name="lib"><Directory Id="lib_gstreamer_0.10" Name="lib_gstreamer_0.10"><Component Guid="1" Id="lib_gstreamer_0.10_libgstplugins.dll"><File Id="_test_lib_gstreamer_010_libgstpluginsdll" Name="libgstplugins.dll" Source="/test/lib/gstreamer-0.10/libgstplugins.dll" /></Component></Directory><Component Guid="1" Id="lib_libfoo.dll"><File Id="_test_lib_libfoodll" Name="libfoo.dll" Source="/test/lib/libfoo.dll" /></Component></Directory></Directory></Module></Wix>'''

class MergeModuleTest(unittest.TestCase):

    def setUp(self):
        self.config = DummyConfig()
        self.package = Package(self.config)

    def test_add_root(self):
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._add_root()
        self.assertEquals(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi" />',
                          etree.tostring(mergemodule.root))

    def test_add_module(self):
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._add_root()
        mergemodule._add_module()
        self.assertEquals(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
                '<Module Id="gstreamer_test" Language="1033" Version="1.0" />'
            '</Wix>', etree.tostring(mergemodule.root))

    def test_add_package(self):
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._add_root()
        mergemodule._add_module()
        mergemodule._add_package()
        self.assertEquals(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
                '<Module Id="gstreamer_test" Language="1033" Version="1.0">'
                    '<Package Comments="test" Description="GStreamer Test" Id="1" '
                    'Manufacturer="GStreamer Project" />'
                '</Module>'
            '</Wix>', etree.tostring(mergemodule.root))

    def test_add_root_dir(self):
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._add_root()
        mergemodule._add_module()
        mergemodule._add_package()
        mergemodule._add_root_dir()
        self.assertEquals(
            '<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">'
                '<Module Id="gstreamer_test" Language="1033" Version="1.0">'
                    '<Package Comments="test" Description="GStreamer Test" Id="1" '
                    'Manufacturer="GStreamer Project" />'
                    '<Directory Id="TARGETDIR" Name="SourceDir" />'
                '</Module>'
            '</Wix>', etree.tostring(mergemodule.root))

    def test_add_directory(self):
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._add_root()
        mergemodule._add_module()
        mergemodule._add_package()
        mergemodule._add_root_dir()
        self.assertEquals(len(mergemodule._dirnodes), 1)
        self.assertEquals(mergemodule._dirnodes[''], mergemodule.rdir)
        mergemodule._add_directory('lib/gstreamer-0.10')
        self.assertEquals(len(mergemodule._dirnodes), 3)
        self.assertTrue('lib' in mergemodule._dirnodes)
        self.assertTrue('lib/gstreamer-0.10' in mergemodule._dirnodes)
        mergemodule._add_directory('bin')
        self.assertEquals(len(mergemodule._dirnodes), 4)
        self.assertTrue('bin' in mergemodule._dirnodes)

    def test_add_file(self):
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._add_root()
        mergemodule._add_module()
        mergemodule._add_package()
        mergemodule._add_root_dir()
        self.assertEquals(len(mergemodule._dirnodes), 1)
        self.assertEquals(mergemodule._dirnodes[''], mergemodule.rdir)
        mergemodule._add_file('bin/gst-inspect-0.10.exe')
        self.assertEquals(len(mergemodule._dirnodes), 2)
        self.assertTrue('bin' in mergemodule._dirnodes)
        self.assertTrue('gstreamer-0.10.exe' not in mergemodule._dirnodes)
        mergemodule._add_file('bin/gst-launch-0.10.exe')
        self.assertEquals(len(mergemodule._dirnodes), 2)
        self.assertTrue('bin' in mergemodule._dirnodes)
        self.assertTrue('gstreamer-0.10.exe' not in mergemodule._dirnodes)

    def test_render_xml(self):
        self.config.platform = Platform.WINDOWS
        mergemodule = MergeModule(self.config, self.package)
        mergemodule._get_uuid = lambda : '1'
        mergemodule.fill()
        self.assertEquals(MERGE_MODULE, mergemodule.render_xml())
