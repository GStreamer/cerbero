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
import unittest
import tempfile
import shutil
import sys

from cerbero.config import Platform
from cerbero.packages import PackageType
from cerbero.packages.osx.pmdoc import Index, PkgRef, PkgContents, PMDoc
from cerbero.utils import shell
from test.test_packages_common import create_store, Package1
from test.test_common import XMLMixin, DummyConfig


class IndexTest(unittest.TestCase, XMLMixin):
    def setUp(self):
        self.config = DummyConfig()
        self.store = create_store(self.config)
        self.package = self.store.get_package('gstreamer-runtime')
        self.outdir = '/test'
        self.index = Index(self.package, self.store, self.outdir, [], PackageType.RUNTIME, False)

    def testAddRoot(self):
        self.index._add_root()
        self.assertEqual(self.index.root.tag, Index.DOCUMENT_TAG)
        self.assertEqual(self.index.root.attrib['spec'], Index.SPEC_VERSION)
        self.assertEqual(len(self.index.root.getchildren()), 0)

    def testAddProperties(self):
        self.index._add_root()
        self.index._add_properties()
        children = self.index.root.getchildren()
        self.assertEqual(len(children), 1)
        properties = children[0]
        self.assertEqual(len(properties.getchildren()), 6)
        self.check_text(properties, Index.TAG_ORGANIZATION, self.package.org)
        self.check_text(properties, Index.TAG_TITLE, self.package.title)
        self.check_text(properties, Index.TAG_BUILD, os.path.join(self.outdir, '%s.pkg' % self.package.name))
        self.check_attrib(properties, Index.TAG_USER_SEES, 'ui', Index.PROP_USER_SEES)
        self.check_attrib(properties, Index.TAG_MIN_TARGET, 'os', Index.PROP_MIN_TARGET)
        self.check_attrib(properties, Index.TAG_DOMAIN, 'system', Index.PROP_DOMAIN)

    def testAddDistribution(self):
        self.index._add_root()
        self.index._add_distribution()
        children = self.index.root.getchildren()
        self.assertEqual(len(children), 1)
        dist = children[0]
        self.find_one(dist, Index.TAG_SCRIPTS)
        self.check_attrib(dist, Index.TAG_VERSION, Index.ATTR_MIN_SPEC, Index.MIN_SPEC)

    def testAddDescription(self):
        self.index._add_root()
        self.index._add_description()
        self.check_text(self.index.root, Index.TAG_DESCRIPTION, self.package.shortdesc)

    def testAddFlags(self):
        self.index._add_root()
        self.index._add_flags()
        self.find_one(self.index.root, Index.TAG_FLAGS)

    def testAddContents(self):
        self.index._add_root()
        self.index._add_contents()
        children = self.index.root.getchildren()
        # 1 choice + 4 item
        self.assertEqual(len(children), 5)
        contents = self.find_one(self.index.root, Index.TAG_CONTENTS)
        packages = []

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
                self.fail('Incorrect choice %s' % choice)
            elpkrefs = [x.attrib['id'] for x in choice.iterfind(Index.TAG_PKGREF)]
            self.assertEqual(sorted(['default.%s.%s' % (self.config.target_arch, x) for x in pkrefs]), sorted(elpkrefs))
            packages.extend(pkrefs)

        items = [x.text[:-4] for x in self.index.root.iterfind(Index.TAG_ITEM) if x.attrib['type'] == 'pkgref']
        self.assertEqual(sorted(packages), sorted(items))


class PkgRefTest(unittest.TestCase, XMLMixin):
    def setUp(self):
        self.config = DummyConfig()
        self.config.target_platform = Platform.LINUX
        self.package = Package1(self.config, None, None)
        self.package_path = '/test/package.pkg'
        self.pkgref = PkgRef(self.package, PackageType.RUNTIME, self.package_path)

    def testAddRoot(self):
        self.pkgref._add_root()
        self.assertEqual(self.pkgref.root.tag, PkgRef.TAG_PKGREF)
        self.assertEqual(self.pkgref.root.attrib['spec'], PkgRef.SPEC_VERSION)
        self.assertEqual(self.pkgref.root.attrib['uuid'], self.package.uuid)
        self.assertEqual(len(self.pkgref.root.getchildren()), 0)

    def testAddScripts(self):
        self.pkgref._add_root()
        self.pkgref._add_scripts()
        scripts = self.find_one(self.pkgref.root, PkgRef.TAG_SCRIPTS)
        self.check_text(scripts, PkgRef.TAG_SCRIPTS_DIR, os.path.join(self.package_path, 'Contents', 'Resources'))

    def testAddExtra(self):
        self.pkgref._add_root()
        self.pkgref._add_extra()
        extra = self.find_one(self.pkgref.root, PkgRef.TAG_EXTRA)
        self.check_text(extra, PkgRef.TAG_PACKAGE_PATH, self.package_path)
        self.check_text(extra, PkgRef.TAG_TITLE, self.package.shortdesc)

    def testAddContents(self):
        self.pkgref._add_root()
        self.pkgref._add_contents()
        contents = self.find_one(self.pkgref.root, PkgRef.TAG_CONTENTS)
        self.check_text(contents, PkgRef.TAG_FILE_LIST, '%s-contents.xml' % self.package.name)

    def testAddConfig(self):
        self.pkgref._add_root()
        self.pkgref._add_config()
        config = self.find_one(self.pkgref.root, PkgRef.TAG_CONFIG)
        self.check_text(config, PkgRef.TAG_IDENTIFIER, self.package.identifier())
        self.check_text(config, PkgRef.TAG_VERSION, self.package.version)
        self.check_text(config, PkgRef.TAG_DESCRIPTION, self.package.shortdesc)
        self.check_attrib(config, PkgRef.TAG_POST_INSTALL, 'type', 'none')
        self.check_attrib(config, PkgRef.TAG_INSTALL_TO, 'relative', 'true')
        self.check_attrib(config, PkgRef.TAG_INSTALL_TO, 'mod', 'true')
        self.check_text(config, PkgRef.TAG_INSTALL_TO, '.')
        self.find_one(config, PkgRef.TAG_REQ_AUTH)
        mods = [
            'installTo.isAbsoluteType',
            'installTo.path',
            'parent',
            'installTo.isRelativeType',
            'installTo',
            'version',
            'identifier',
        ]
        docmods = [x.text for x in config.iterfind(PkgRef.TAG_MOD)]
        self.assertEqual(sorted(mods), sorted(docmods))
        flags = self.find_one(config, PkgRef.TAG_FLAGS)
        self.find_one(flags, PkgRef.TAG_FOLLOW_SYMLINKS)


class PkgContentsWrap(PkgContents):
    dirs = ['.', './bin', './lib', './lib/gstreamer-0.10', '']
    files = ['./bin/gst-inspect', './lib/libgstreamer.so.1.0', './lib/gstreamer-0.10/libgstplugin.so', './README', '']

    def _list_bom_dirs(self):
        return '\n'.join(self.dirs)

    def _list_bom_files(self):
        paths = self.dirs + self.files
        return '\n'.join(['%s\t00000' % f for f in paths])


class PkgContentsTest(unittest.TestCase, XMLMixin):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pkgcontents = PkgContentsWrap(self.tmp)
        os.makedirs(os.path.join(self.tmp, 'bin'))
        os.makedirs(os.path.join(self.tmp, 'lib/gstreamer-0.10'))
        shell.call('touch %s' % ' '.join(PkgContentsWrap.files), self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def testAddRoot(self):
        self.pkgcontents._add_root()
        self.assertEqual(self.pkgcontents.root.tag, PkgContents.TAG_PKG_CONTENTS)
        self.assertEqual(self.pkgcontents.root.attrib['spec'], PkgContents.SPEC_VERSION)
        self.assertEqual(len(self.pkgcontents.root.getchildren()), 0)

    def testAddPackageRoot(self):
        self.pkgcontents._add_root()
        self.pkgcontents._add_package_root()
        for k, v in [
            ('n', 'PackageRoot'),
            ('o', PkgContents.OWNER),
            ('g', PkgContents.GROUP),
            ('pt', '.'),
            ('m', 'true'),
            ('t', 'bom'),
        ]:
            self.check_attrib(self.pkgcontents.root, PkgContents.TAG_F, k, v)

    def testFill(self):
        self.pkgcontents._fill()
        children = [x for x in self.pkgcontents.proot.getchildren() if x.tag == PkgContents.TAG_F]
        children_path = [x.attrib['n'] for x in children]
        self.assertEqual(sorted(children_path), sorted(['bin', 'lib', 'README']))
        for c in children:
            if c.attrib['n'] == 'bin':
                self.check_attrib(c, PkgContents.TAG_F, 'n', 'gst-inspect')
            elif c.attrib['n'] == 'lib':
                for c in c.getchildren():
                    if c.attrib['n'] == 'gstreamer-0.10':
                        self.check_attrib(c, PkgContents.TAG_F, 'n', 'libgstplugin.so')
                    else:
                        self.assertEqual(c.attrib['n'], 'libgstreamer.so.1.0')
            else:
                self.assertEqual(c.attrib['n'], 'README')


class TestPMDoc(unittest.TestCase):
    # if not sys.platform.startswith('darwin'):

    def setUp(self):
        self.config = DummyConfig()
        self.store = create_store(self.config)
        self.tmp = tempfile.mkdtemp()
        self.package = self.store.get_package('gstreamer-runtime')
        self.packages_path = os.path.join(self.tmp, 'test.pkg')
        os.mkdir(self.packages_path)
        shell.call('touch %s file1 file2 file3', self.packages_path)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @unittest.skipUnless(sys.platform.startswith('darwin'), 'requires OSX')
    def testAllFilesCreated(self):
        d = dict()
        packages = ['gstreamer-test1', 'gstreamer-test3', 'gstreamer-test-bindings', 'gstreamer-test2']
        for name in packages:
            p = self.store.get_package(name)
            d[p] = self.packages_path
        self.package.__file__ = ''
        pmdoc = PMDoc(self.package, self.store, self.tmp, d)
        path = pmdoc.create()
        files = os.listdir(path)

        expected_files = ['index.xml']
        for p in packages:
            expected_files.append('%s.xml' % p)
            expected_files.append('%s-contents.xml' % p)
        self.assertEqual(sorted(files), sorted(expected_files))
