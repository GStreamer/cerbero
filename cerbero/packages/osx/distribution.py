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

from cerbero.config import Architecture
from cerbero.utils import etree


class DistributionXML(object):
    ''' Creates a Distribution.xml for productbuild '''

    TAG_ALLOWED_OS_VERSIONS = 'allowed-os-versions'
    TAG_BACKGOUND = 'background'
    TAG_CHOICE = 'choice'
    TAG_CHOICES_OUTLINE = 'choices-outline'
    TAG_DOMAINS = 'domains'
    TAG_INSTALLER_GUI_SCRIPT = 'installer-gui-script'
    TAG_LICENSE = 'license'
    TAG_LINE = 'line'
    TAG_OPTIONS = 'options'
    TAG_OS_VERSION = 'os-version'
    TAG_PKGREF = 'pkg-ref'
    TAG_TITLE = 'title'

    ATTR_MIN_SPEC = 'min-spec'
    ATTR_REQUIRE_SCRIPTS = 'require-scripts'
    ATTR_HOST_ARCHS = 'hostArchitectures'

    PROP_ALIGN = 'left'
    PROP_ENABLE_ANYWHERE = 'false'
    PROP_ENABLE_LOCAL_SYSTEM = 'true'
    PROP_ENABLE_USER_HOME = 'false'
    PROP_SCALE = 'none'
    PROP_SPEC_VERSION = '1'

    def __init__(self, package, store, out_dir, packages_paths, emptypkgs,
                 package_type, target_arch, home_folder=False, fill=True):
        self.package = package
        self.store = store
        self.out_dir = out_dir
        self.packages_paths = packages_paths
        self.emptypkgs = emptypkgs
        self.package_type = package_type
        self.packagerefs = []
        self.target_arch = target_arch
        self.PROP_ENABLE_USER_HOME = self._boolstr(home_folder)
        self.PROP_ENABLE_LOCAL_SYSTEM = self._boolstr(not home_folder)
        if fill:
            self._fill()

    def render(self):
        return etree.tostring(self.root)

    def write(self, path):
        tree = etree.ElementTree(self.root)
        tree.write(path, encoding='utf-8')

    def _fill(self):
        self._add_root()
        self._add_options()
        self._add_customization()
        self._add_choices()

    def _add_root(self):
        self.root = etree.Element(self.TAG_INSTALLER_GUI_SCRIPT,
                                  minSpecVesion=self.PROP_SPEC_VERSION)

    def _add_options(self):
        options = etree.SubElement(self.root, self.TAG_OPTIONS)
        options.set(self.ATTR_REQUIRE_SCRIPTS, 'false')
        if self.target_arch == Architecture.X86_64:
            arch = 'x86_64'
        else:
            arch = 'i386'
        #options.set(self.ATTR_HOST_ARCHS, arch)

    def _add_customization(self):
        # Background
        etree.SubElement(self.root, self.TAG_BACKGOUND,
                         align=self.PROP_ALIGN,
                         scale=self.PROP_SCALE,
                         file=self.package.resources_background)
        # License
        etree.SubElement(self.root, self.TAG_LICENSE,
                         file=self.package.resources_license_rtf)

        # Domains
        etree.SubElement(self.root, self.TAG_DOMAINS,
                         enable_anywhere=self.PROP_ENABLE_ANYWHERE,
                         enable_currentUserHome=self.PROP_ENABLE_USER_HOME,
                         enable_localSystem=self.PROP_ENABLE_LOCAL_SYSTEM)

        # Title
        title = etree.SubElement(self.root, self.TAG_TITLE)
        title.text = self.package.shortdesc

    def _add_choices(self):
        choices = []
        self.choices_outline = etree.SubElement (self.root,
                self.TAG_CHOICES_OUTLINE)
        for p, required, selected in self.package.packages:
            if p in choices:
                continue
            choices.append(p)
            package = self.store.get_package(p)
            package.set_mode(self.package_type)
            if package in self.emptypkgs:
                continue
            etree.SubElement (self.choices_outline, self.TAG_LINE,
                              choice=package.identifier())
            self._add_choice(package, not required, selected)

    def _add_choice(self, package, enabled, selected):
        choice = etree.SubElement(self.root, self.TAG_CHOICE,
            id=package.identifier(), title=package.shortdesc,
            description=package.longdesc)
        if not selected:
            choice.set('start_selected', 'false')
        if not enabled:
            choice.set('start_enabled', 'false')

        packages = [package] + self.store.get_package_deps(package)
        for package in packages:
            if package in self.emptypkgs:
                continue
            package.set_mode(self.package_type)
            etree.SubElement(choice, self.TAG_PKGREF, id=package.identifier())
            if package not in self.packagerefs:
                item = etree.SubElement(self.root, self.TAG_PKGREF,
                        id=package.identifier(), version=package.version)
                item.text = self.packages_paths[package]
                self.packagerefs.append(package)

    def _set(self, node, **kwargs):
        for key in sorted(kwargs.keys()):
            value = kwargs[key]
            if value is None or value is '':
                continue
            node.set(key, value)

    def _boolstr(self, boolean):
        return boolean and 'true' or 'false'
