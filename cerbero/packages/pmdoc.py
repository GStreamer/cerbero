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


class PMDocXML(object):

    TAG_CONTENTS = 'contents'
    TAG_DESCRIPTION = 'description'
    TAG_FLAGS = 'flags'
    TAG_MOD = 'mod'
    TAG_PKGREF = 'pkgref'
    TAG_SCRIPTS = 'scripts'
    TAG_TITLE = 'title'
    TAG_VERSION = 'version'
    SPEC_VERSION = '1.12'

    def render(self):
        return etree.tostring(self.root)

    def _add_mods(self, parent, mods):
        for mod in mods:
            el = etree.SubElement(parent, self.TAG_MOD)
            el.text = mod

    def _subelement_text(self, parent, tag, text, **attrib):
        el = etree.SubElement(parent, tag, **attrib)
        el.text = text
        return el


class Index(PMDocXML):
    ''' Index file for PackageMake document '''

    DOCUMENT_TAG = 'pkmdoc'
    MIN_SPEC = '1.000000'
    PROP_USER_SEES = 'custom'
    PROP_MIN_TARGET = '2'
    PROP_DOMAIN = 'anywhere'
    ATTR_MIN_SPEC = 'min-spec'
    TAG_BUILD = 'build'
    TAG_CHOICE = 'choice'
    TAG_DISTRIBUTION = 'ditribution'
    TAG_DOMAIN = 'domain'
    TAG_ITEM = 'item'
    TAG_MIN_TARGET = 'min-target'
    TAG_MOD = 'mod'
    TAG_ORGANIZATION = 'organization'
    TAG_PROPERTIES = 'properties'
    TAG_PKGREF = 'pkgref'
    TAG_SCRIPTS = 'scripts'
    TAG_USER_SEES = 'userSees'

    def __init__(self, package, store, out_dir, fill=True):
        self.package = package
        self.store = store
        self.out_dir = out_dir
        if fill:
            self._fill()

    def _fill(self):
        self._add_root()
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
        self._add_mods(self.root, ['description', 'properties.title',
            'properties.customizeOption'])

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


class PkgRef(PMDocXML):
    ''' PkgRef for packages in a PackageMaker document '''

    TAG_CONFIG = 'config'
    TAG_IDENTIFIER = 'identifier'
    TAG_POST_INSTALL = 'post-install'
    TAG_REQ_AUTH = 'requireAuthorization'
    TAG_INSTALL_TO = 'intallTo'
    TAG_FOLLOW_SYMLINKS = 'followSymbolicLinks'
    TAG_PACKAGE_STORE = 'packageStore'
    TAG_FILE_LIST = 'file-list'
    TAG_FILTER = 'filter'
    TAG_EXTRA = 'extra'
    TAG_PACKAGE_PATH = 'packagePath'
    TAG_SCRIPTS_DIR = 'scripts-dir'


    def __init__(self, package, package_path, fill=True):
        self.package = package
        self.package_path = package_path
        if fill:
            self._fill()

    def _fill(self):
        self._add_root()
        self._add_config()
        self._add_scripts()
        self._add_contents()
        self._add_extra()

    def _add_root(self):
        if self.package.uuid is None:
            raise FatalError("uuid for package '%s' is None" % self.package.name)
        self.root = etree.Element(self.TAG_PKGREF, spec=self.SPEC_VERSION,
                                  uuid=self.package.uuid)

    def _add_config(self):
        config = etree.SubElement(self.root, self.TAG_CONFIG)
        self._subelement_text(config, self.TAG_VERSION, '1.0')
        self._subelement_text(config, self.TAG_IDENTIFIER, self.package.name)
        self._subelement_text(config, self.TAG_DESCRIPTION, self.package.shortdesc)
        etree.SubElement(config, self.TAG_POST_INSTALL, type="none")
        etree.SubElement(config, self.TAG_REQ_AUTH)
        self._subelement_text(config, self.TAG_INSTALL_TO, '.',
                              relative="true", mod="true")
        etree.SubElement(config, self.TAG_PACKAGE_STORE, type="internal")
        self._add_mods(config, ['installTo.isAbsoluteType', 'installTo.path',
            'parent', 'installTo.isRelativeType', 'installTo'])
        flags = etree.SubElement(config, self.TAG_FLAGS)
        etree.SubElement(flags, self.TAG_FOLLOW_SYMLINKS)

    def _add_scripts(self):
        scripts = etree.SubElement(self.root, self.TAG_SCRIPTS)
        self._subelement_text(scripts, self.TAG_SCRIPTS_DIR,
                os.path.join(self.package_path, 'Contents', 'Resources'))

    def _add_contents(self):
        contents = etree.SubElement(self.root, self.TAG_CONTENTS)
        self._subelement_text(contents, self.TAG_FILE_LIST,
                              "%s-contents.xml" % self.package.name)
        for f in ['.DS_Store$']:
            self._subelement_text(contents, self.TAG_FILTER, f)

    def _add_extra(self):
        extra = etree.SubElement(self.root, self.TAG_EXTRA)
        self._subelement_text(extra, self.TAG_TITLE, self.package.shortdesc)
        self._subelement_text(extra, self.TAG_PACKAGE_PATH, self.package_path)
