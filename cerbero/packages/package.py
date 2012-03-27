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

from cerbero.config import Platform
from cerbero.utils import shell


class PackageBase(object):
    '''
    Base class for packages with the common field to describe a package

    @cvar name: name of the package
    @type name: str
    @cvar shortdesc: Short description of the package
    @type shortdesc: str
    @cvar longdesc: Long description of the package
    @type longdesc: str
    @cvar version: version of the package
    @type version: str
    @cvar uuid: unique id for this package
    @type uuid: str
    @cvar licenses:  list of the package licenses
    @type licenses: list
    @cvar vendor: vendor for this package
    @type vendor: str
    @cvar org: organization for this package (eg: net.foo.bar)
    @type org: str
    @cvar url: url for this pacakge
    @type url: str
    '''
    name = 'default'
    shortdesc = 'default'
    longdesc = 'default'
    version = 'default'
    org = 'default'
    uuid = None
    licenses = list()
    vendor = 'default'
    url = 'default'


class Package(PackageBase):
    '''
    Describes a set of files to produce disctribution packages for the different
    target platforms

    @cvar deps: list of packages dependencies
    @type deps: list
    @cvar files: list of files included in this package
    @type files: list
    '''

    deps = list()

    def __init__(self, config, cookbook):
        self.cookbook = cookbook
        self._files.extend = self.platform_files.get(config.target_platform, [])
        self._parse_files()

    def recipes_dependencies(self):
        return [x.split(':')[0] for x in self._files]
    
    def files_list(self):
        files = []
        for recipe, categories in self._recipes_files:
            rfiles = self.cookbook.get_recipe(recipe).files_list(categories)
            files.extend(rfiles)
        return files

    def _parse_files(self):
        self._recipes_files = {}
        for r in self.files:
            l = r.split(':')
            self._recipes_files[l[0]] = l[1:]


class MetaPackage(PackageBase):
    '''
    Group of packages used to build an installer package

    @cvar packages: list of packages grouped in this meta package
    @type packages: list
    @cvar icon: filename of the package icon
    @type icon: str
    '''

    icon = None
    packages = []

    def __init__(self, config):
        self.config = config

    def list_packages(self):
        return [p[0] for p in self.packages]
