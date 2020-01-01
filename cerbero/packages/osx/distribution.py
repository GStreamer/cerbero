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

DISTRO_XML_TPL = '''\
<?xml version="1.0"?>
<installer-gui-script minSpecVesion="1">
  <options require-scripts="false"/>
  <background align="left" file="%(background)s" scale="none"/>
  <license file="%(license)s"/>
  <domains enable_anywhere="false" enable_currentUserHome="%(ehome)s" enable_localSystem="%(elocal)s"/>
  <title>%(title)s</title>
  <choices-outline>
    %(choices)s
  </choices-outline>
  %(choices_desc)s
  %(pkg_refs)s
</installer-gui-script>
'''

class DistributionXML(object):
    ''' Creates a Distribution.xml for productbuild '''

    TAG_CHOICE = 'choice'
    TAG_CHOICES_OUTLINE = 'choices-outline'
    TAG_OPTIONS = 'options'
    TAG_PKGREF = 'pkg-ref'

    PROP_ENABLE_ANYWHERE = 'false'

    def __init__(self, package, store, out_dir, packages_paths, emptypkgs,
                 package_type, target_arch, home_folder=False):
        self.package = package
        self.store = store
        self.out_dir = out_dir
        self.packages_paths = packages_paths
        self.emptypkgs = emptypkgs
        self.package_type = package_type
        self.packagerefs = []
        self.target_arch = target_arch
        self.enable_user_home = self._boolstr(home_folder)
        self.enable_local_system = self._boolstr(not home_folder)
        if os.path.exists(package.resources_distribution):
            self.template = open(package.resources_distribution).read()
        else:
            self.template = DISTRO_XML_TPL
        self._add_choices()

    def write(self, path):
        with open(path, 'w') as f:
            f.write(self._fill_distro())

    def _fill_distro(self):
        return self.template % {'background': self.package.resources_background,
                                'license': self.package.resources_license_rtf,
                                'ehome': self.enable_user_home,
                                'elocal': self.enable_local_system,
                                'title': self.package.shortdesc,
                                'choices': self.choices,
                                'choices_desc': self.choices_desc,
                                'pkg_refs': self.pkg_refs}

    def _add_choices(self):
        self.choices = ''
        self.choices_desc = ''
        self.pkg_refs = ''
        parsed_choices = []
        for p, required, selected in self.package.packages:
            if p in parsed_choices:
                continue
            parsed_choices.append(p)
            package = self.store.get_package(p)
            package.set_mode(self.package_type)
            if package in self.emptypkgs:
                continue
            self.choices += '<line choice="%s"/>\n' % package.identifier()
            self._add_choice(package, not required, selected)

    def _add_choice(self, package, enabled, selected):
        self.choices_desc += '<choice description="default" id="%s" start_enabled="%s"'\
                             ' title="%s">\n' % \
            (package.identifier(), enabled, package.longdesc)

        packages = [package] + self.store.get_package_deps(package)
        for package in packages:
            if package in self.emptypkgs:
                continue
            package.set_mode(self.package_type)
            self.choices_desc += '<pkg-ref id="%s"/>\n' % package.identifier()
            if package not in self.packagerefs:
                self.pkg_refs += '<pkg-ref id="%s" version="%s">%s</pkg-ref>\n' % \
                    (package.identifier(), package.version, self.packages_paths[package])
                self.packagerefs.append(package)
        self.choices_desc += '</choice>\n'

    def _set(self, node, **kwargs):
        for key in sorted(kwargs.keys()):
            value = kwargs[key]
            if value is None or value == '':
                continue
            node.set(key, value)

    def _boolstr(self, boolean):
        return boolean and 'true' or 'false'
