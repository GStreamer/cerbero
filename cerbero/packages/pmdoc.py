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
import itertools

from cerbero.utils import etree


class Index(object):
    ''' Index file for PackageMake document '''

    DOCUMENT_TAG = 'pkmdoc'
    SPEC_VERSION = '1.12'
    MIN_SPEC = '1.000000'
    PROP_USER_SEES = 'custom'
    PROP_MIN_TARGET = '2'
    PROP_DOMAIN = 'anywhere'
    ATTR_MIN_SPEC = 'min-spec'
    TAG_BUILD = 'build'
    TAG_CHOICE = 'choice'
    TAG_CONTENTS = 'contents'
    TAG_DESCRIPTION = 'description'
    TAG_DISTRIBUTION = 'ditribution'
    TAG_DOMAIN = 'domain'
    TAG_FLAGS = 'flags'
    TAG_ITEM = 'item'
    TAG_MIN_TARGET = 'min-target'
    TAG_MOD = 'mod'
    TAG_ORGANIZATION = 'organization'
    TAG_PROPERTIES = 'properties'
    TAG_PKGREF = 'pkgref'
    TAG_SCRIPTS = 'scripts'
    TAG_TITLE = 'title'
    TAG_USER_SEES = 'userSees'
    TAG_VERSION = 'version'

    def __init__(self, package, store, out_dir):
        self.package = package
        self.store = store
        self.out_dir = out_dir

    def render(self):
        self._add_properties()
        self._add_distribution()
        self._add_description()
        self._add_mod()
        self._add_flags()
        self._add_contents()

    def _add_root(self):
        self.root = etree.Element(self.DOCUMENT_TAG, spec=self.SPEC_VERSION)

    def _add_properties(self):
        properties = etree.SubElement(self.root, self.TAG_PROPERTIES)
        org = etree.SubElement(properties, self.TAG_ORGANIZATION)
        org.text = self.package.org
        title = etree.SubElement(properties, self.TAG_TITLE)
        title.text = self.package.title
        build = etree.SubElement(properties, self.TAG_BUILD)
        build.text = os.path.join(self.out_dir, "%s.pkg" % self.package.name)

        for e, k, v in [(self.TAG_USER_SEES, 'ui', self.PROP_USER_SEES),
                (self.TAG_MIN_TARGET, 'os', self.PROP_MIN_TARGET),
                (self.TAG_DOMAIN, 'anywhere', self.PROP_DOMAIN)]:
            node = etree.SubElement(properties, e)
            self._set(node, **{k:v})

    def _add_distribution(self):
        distribution = etree.SubElement(self.root, self.TAG_DISTRIBUTION)
        scripts = etree.SubElement(distribution, self.TAG_SCRIPTS)
        version = etree.SubElement(distribution, self.TAG_VERSION)
        version.set(self.ATTR_MIN_SPEC, self.MIN_SPEC)

    def _add_description(self):
        desc = etree.SubElement(self.root, self.TAG_DESCRIPTION)
        desc.text = self.package.shortdesc

    def _add_mod(self):
        mod = etree.SubElement(self.root, self.TAG_MOD)
        mod.text = 'description'
        mod = etree.SubElement(self.root, self.TAG_MOD)
        mod.text = 'properties.title'
        mod = etree.SubElement(self.root, self.TAG_MOD)
        mod.text = 'properties.customizeOption'

    def _add_flags(self):
        etree.SubElement(self.root, self.TAG_FLAGS)

    def _add_contents(self):
        contents = etree.SubElement(self.root, self.TAG_CONTENTS)

        # With PackageMaker choices can't be nested so we group all packages
        # no matter the feature they belong to.
        packages = itertools.chain(*self.package.packages.values())

        for p, required, selected in packages:
            package = self.store.get_package(p)
            self._add_choice(package, not required, selected, contents)

    def _add_choice(self, package, enabled, selected, contents):
        choice = etree.SubElement(contents, self.TAG_CHOICE,
            title=package.shortdesc, id=package.name,
            starts_selected=self._boolstr(selected),
            starts_enabled=self._boolstr(enabled), start_hidden='false')
        packages = [package.name] + package.deps
        for p_name in packages:
            etree.SubElement(choice, self.TAG_PKGREF, id=p_name)
            item = etree.SubElement(self.root, self.TAG_ITEM, type='pkgref')
            item.text = '%s.xml' % p_name

    def _boolstr(self, boolean):
        return boolean and 'true' or 'false'
    
    def _set(self, node, **kwargs):
        for key in sorted(kwargs.keys()):
            value = kwargs[key]
            if value is None or value is '':
                continue
            node.set(key, value)
