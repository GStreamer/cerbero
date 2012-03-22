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
from cerbero.packages.pmdoc import Index
from cerbero.tests.test_packages_common import create_store, DummyConfig
from cerbero.utils import shell, etree


class IndexTest(unittest.TestCase):

    def setUp(self):
        self.config = DummyConfig()
        self.config.target_platform = Platform.LINUX
        self.store = create_store(self.config)
        self.package = self.store.get_package('gstreamer-runtime')
        self.outdir = '/test'
        self.index = Index(self.package, self.store, self.outdir)

    def _find_one(self, el, tag):
        children = list(el.iterfind(tag))
        if len(children) == 0:
            self.fail("Element with tag %s not found in parent %s" % (tag, el))
        return children[0] 

    def _test_attrib(self, parent, tag, attrib, value):
        n = self._find_one(parent, tag)
        if attrib not in n.attrib:
            self.fail("Attribute %s not found in %s" % (attrib, n))
        self.assertEquals(n.attrib[attrib], value)

    def _test_text(self, parent, tag, value):
        n = self._find_one(parent, tag)
        self.assertEquals(n.text, value)
        
    def testAddRoot(self):
        self.index._add_root()
        self.assertEquals(self.index.root.tag, Index.DOCUMENT_TAG)
        self.assertEquals(self.index.root.attrib['spec'], Index.SPEC_VERSION)
        self.assertEquals(len(self.index.root.getchildren()), 0)
    
    def testAddProperties(self):
        self.index._add_root()
        self.index._add_properties()
        children = self.index.root.getchildren()
        self.assertEquals(len(children), 1)
        properties = children[0]
        self.assertEquals(len(properties.getchildren()), 6)
        self._test_text(properties, Index.TAG_ORGANIZATION, self.package.org)
        self._test_text(properties, Index.TAG_TITLE, self.package.title)
        self._test_text(properties, Index.TAG_BUILD,
                os.path.join(self.outdir, '%s.pkg' % self.package.name))
        self._test_attrib(properties, Index.TAG_USER_SEES, 'ui',
                Index.PROP_USER_SEES)
        self._test_attrib(properties, Index.TAG_MIN_TARGET, 'os',
                Index.PROP_MIN_TARGET)
        self._test_attrib(properties, Index.TAG_DOMAIN, 'anywhere',
                Index.PROP_DOMAIN)

    def testAddDistribution(self):
        self.index._add_root()
        self.index._add_distribution()
        children = self.index.root.getchildren()
        self.assertEquals(len(children), 1)
        dist =children[0]
        self._find_one(dist, Index.TAG_SCRIPTS)
        self._test_attrib(dist, Index.TAG_VERSION, Index.ATTR_MIN_SPEC,
                Index.MIN_SPEC)

    def testAddDescription(self):
        self.index._add_root()
        self.index._add_description()
        self._test_text(self.index.root, Index.TAG_DESCRIPTION,
                self.package.shortdesc)

    def testAddFlags(self):
        self.index._add_root()
        self.index._add_flags()
        self._find_one(self.index.root, Index.TAG_FLAGS)

    def testAddContents(self):
        self.index._add_root()
        self.index._add_contents()
        children = self.index.root.getchildren()
        # 1 choice + 4 item
        self.assertEquals(len(children), 5)
        contents = self._find_one(self.index.root, Index.TAG_CONTENTS)
        packages =[]

        for choice in contents.iterfind(Index.TAG_CHOICE):
            if choice.attrib['id'] == 'gstreamer-test1':
                # Should have 2 package ref because it has a dependency in
                # gstreamer-test2
                pkrefs = ['gstreamer-test1', 'gstreamer-test2']
            elif choice.attrib['id'] == 'gstreamer-test3':
                pkrefs = ['gstreamer-test3']
            elif choice.attrib['id'] == 'gstreamer-test-bindings':
                pkrefs = ['gstreamer-test-bindings']
            else:
                self.fail("Incorrect choice %s" % choice)
            elpkrefs = [x.attrib['id'] for x in \
                        choice.iterfind(Index.TAG_PKGREF)] 
            self.assertEquals(sorted(pkrefs), sorted(elpkrefs))
            packages.extend(pkrefs)

        items = [x.text[:-4] for x in self.index.root.iterfind(Index.TAG_ITEM) if
                 x.attrib['type']=='pkgref']
        self.assertEquals(sorted(packages), sorted(items))
