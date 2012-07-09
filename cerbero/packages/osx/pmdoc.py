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

from cerbero.utils import etree, shell
from cerbero.errors import FatalError
from cerbero.packages import PackageType


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

    def write(self, path):
        tree = etree.ElementTree(self.root)
        tree.write(path, encoding='utf-8')

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
    PROP_DOMAIN = 'true'
    ATTR_MIN_SPEC = 'min-spec'
    ATTR_BG_SCALE = 'bg-scale'
    ATTR_BG_ALIGN = 'bg-align'
    TAG_BUILD = 'build'
    TAG_CHOICE = 'choice'
    TAG_DISTRIBUTION = 'ditribution'
    TAG_DOMAIN = 'domain'
    TAG_ITEM = 'item'
    TAG_LOCALE = 'locale'
    TAG_MIN_TARGET = 'min-target'
    TAG_MOD = 'mod'
    TAG_ORGANIZATION = 'organization'
    TAG_PROPERTIES = 'properties'
    TAG_PKGREF = 'pkgref'
    TAG_RESOURCE = 'resource'
    TAG_RESOURCES = 'resources'
    TAG_SCRIPTS = 'scripts'
    TAG_USER_SEES = 'userSees'

    def __init__(self, package, store, out_dir, emptypkgs=[],
                 package_type=PackageType.RUNTIME, fill=True):
        self.package = package
        self.store = store
        self.out_dir = out_dir
        self.emptypkgs = emptypkgs
        self.package_type = package_type
        self.packagerefs = []
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
        self._add_ui_customization()

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
                (self.TAG_DOMAIN, 'system', self.PROP_DOMAIN)]:
            node = etree.SubElement(properties, e)
            self._set(node, **{k: v})

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

        choices = []
        for p, required, selected in self.package.packages:
            if p in choices:
                continue
            choices.append(p)
            package = self.store.get_package(p)
            package.set_mode(self.package_type)
            if package in self.emptypkgs:
                continue
            self._add_choice(package, not required, selected, contents)

    def _add_choice(self, package, enabled, selected, contents):
        choice = etree.SubElement(contents, self.TAG_CHOICE,
            title=package.shortdesc, id=package.name,
            starts_selected=self._boolstr(selected),
            starts_enabled=self._boolstr(enabled), starts_hidden='false')
        packages = [package] + self.store.get_package_deps(package)
        for package in packages:
            if package in self.emptypkgs:
                continue
            etree.SubElement(choice, self.TAG_PKGREF, id=package.identifier())
            if package not in self.packagerefs:
                item = etree.SubElement(self.root, self.TAG_ITEM, type='pkgref')
                item.text = '%s.xml' % package.name
                self.packagerefs.append(package)

    def _add_ui_customization(self):
        resources = etree.SubElement(self.root, self.TAG_RESOURCES)
        resources.set(self.ATTR_BG_ALIGN, "left")
        resources.set(self.ATTR_BG_SCALE, "none")
        locale = etree.SubElement(resources, self.TAG_LOCALE, lang='en')
        path = self.package.resources_background
        if os.path.exists(path):
            background = etree.SubElement(locale, self.TAG_RESOURCE, mod='true',
                type='background')
            background.text = path
        path = self.package.resources_license_unwrapped
        if os.path.exists(path):
            license = etree.SubElement(locale, self.TAG_RESOURCE, mod='true',
                type='license')
            license.text = path

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

    def __init__(self, package, package_type, package_path, fill=True):
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
            raise FatalError("uuid for package '%s' is None" %
                             self.package.name)
        self.root = etree.Element(self.TAG_PKGREF, spec=self.SPEC_VERSION,
                                  uuid=self.package.uuid)

    def _add_config(self):
        config = etree.SubElement(self.root, self.TAG_CONFIG)
        self._subelement_text(config, self.TAG_VERSION, '1.0')
        self._subelement_text(config, self.TAG_IDENTIFIER,
                self.package.identifier())
        self._subelement_text(config, self.TAG_DESCRIPTION,
                self.package.shortdesc)
        etree.SubElement(config, self.TAG_POST_INSTALL, type="none")
        etree.SubElement(config, self.TAG_REQ_AUTH)
        self._subelement_text(config, self.TAG_INSTALL_TO, '.',
                              relative="true", mod="true")
        etree.SubElement(config, self.TAG_PACKAGE_STORE, type="internal")
        self._add_mods(config, ['installTo.isAbsoluteType', 'installTo.path',
            'installTo.isRelativeType', 'installTo',
            'parent', 'version', 'identifier'])
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



class PkgContents(PMDocXML):
    '''
    Creates a contents.xml files list for PackageMaker documents,
    using lsbom to list the files inside a packages.
    '''

    TAG_PKG_CONTENTS = 'pkg-contents'
    TAG_F = 'f'
    OWNER = 'root'
    GROUP = 'admin'

    def __init__(self, package_path, fill=True):
        self.package_path = package_path
        self.bom_path = os.path.join(self.package_path, 'Contents',
                                     'Archive.bom')
        if fill:
            self._fill()

    def _fill(self):
        self._add_root()
        self._list_directories()
        self._list_files()
        self._add_dirs()
        self._add_files()

    def _list_bom_dirs(self):
        return shell.check_call('lsbom %s -s -d' % self.bom_path)

    def _list_bom_files(self):
        return shell.check_call('lsbom %s -p fm' % self.bom_path)

    def _list_directories(self):
        self.dirs = self._list_bom_dirs().split('\n')
        try:
            self.dirs.remove('')
        except:
            pass

    def _list_files(self):
        self.files_modes = dict()
        for line in self._list_bom_files().split('\n')[1:]:
            if line == '':
                continue
            path, mode = line.split('\t')
            # convert from unix shell permissions to stat mode
            self.files_modes[path] = str(int(mode, 8))
        try:
            del self.files_modes['']
        except:
            pass

    def _add_root(self):
        self.root = etree.Element(self.TAG_PKG_CONTENTS,
                spec=self.SPEC_VERSION)

    def _add_package_root(self):
        self.proot = etree.SubElement(self.root, self.TAG_F,
            n='PackageRoot', o=self.OWNER, g=self.GROUP, pt='.', m='true',
            t='bom', p='16877')
        for mod in ['name']:
            self._subelement_text(self.proot, self.TAG_MOD, mod)
        return self.proot

    def _add_dirs(self):
        self.dirs_nodes = dict()
        for path in self.dirs:
            parent, dirname = os.path.split(path)
            if dirname == '.':
                self.dirs_nodes['.'] = self._add_package_root()
            else:
                # all directories are listed in the correct order, so we
                # assume that the parent has already been created
                parent_node = self.dirs_nodes[parent]
                self.dirs_nodes[path] = self._add_entry(parent_node, dirname,
                        self.files_modes[path])

    def _add_files(self):
        for f, m in self.files_modes.iteritems():
            if f in self.dirs:
                continue
            parent, filename = os.path.split(f)
            self._add_entry(self.dirs_nodes[parent], filename, m)

    def _add_entry(self, parent, name, mode):
        return etree.SubElement(parent, self.TAG_F, n=name, o=self.OWNER,
                g=self.GROUP, p=mode)


class PMDoc(object):
    '''
    Creates a .pmdoc file from a metapackage

    '''

    def __init__(self, package, store, output_dir, pkgspath,
                 emptypkgs=[], package_type=PackageType.RUNTIME):
        self.package_type = package_type
        self.package = package
        self.pkgspath = pkgspath
        self.emptypkgs = emptypkgs
        self.store = store
        self.package_type = package_type
        self.done_packages = []
        self.outdir = os.path.join(output_dir, "%s.pmdoc" % self.package.name)
        os.makedirs(self.outdir)

    def create(self):
        packages = self.store.get_package_deps(self.package)
        for p in packages:
            p.set_mode(self.package_type)
            self._create_pkgref_and_contents(p)

        index = Index(self.package, self.store, self.outdir, self.emptypkgs,
                      self.package_type)
        index.write(os.path.join(self.outdir, "index.xml"))
        return self.outdir

    def _create_pkgref_and_contents(self, package):
        # package already created
        if package in self.done_packages:
            return
        # package is empty
        if package in self.emptypkgs:
            return
        pkgref = PkgRef(package, self.package_type,
                        self.pkgspath[package])
        pkgref.write(os.path.join(self.outdir, "%s.xml" % package.name))
        pkgcontents = PkgContents(self.pkgspath[package])
        pkgcontents.write(os.path.join(self.outdir, "%s-contents.xml" %
                                       package.name))
        self.done_packages.append(package)
