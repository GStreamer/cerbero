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

import itertools

from cerbero.build.filesprovider import FilesProvider


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
    @cvar license:  package license
    @type license: str
    @cvar vendor: vendor for this package
    @type vendor: str
    @cvar org: organization for this package (eg: net.foo.bar)
    @type org: str
    @cvar url: url for this pacakge
    @type url: str
    @cvar sys_deps: system dependencies for this package
    @type sys_deps: dict
    @cvar ignore_package_prefix: do not use the package prefix set in the config
    @type ignore_package_prefix: bool
    '''
    name = 'default'
    shortdesc = 'default'
    longdesc = 'default'
    version = 'default'
    org = 'default'
    uuid = None
    licenses = ['GPL']
    vendor = 'default'
    url = 'default'
    ignore_package_prefix = False
    sys_deps = {}

    def __init__(self, config, store):
        self.config = config
        self.store = store

    def prepare(self):
        '''
        Can be overrided by subclasses to modify conditionally the package
        '''
        pass

    def files_list(self):
        raise NotImplemented("'files_list' must be implemented by subclasses")

    def devel_files_list(self):
        raise NotImplemented("'devel_files_list' must be implemented by "
                             "subclasses")

    def all_files_list(self):
        raise NotImplemented("'all_files_list' must be implemented by "
                             "subclasses")

    def get_install_dir(self):
        try:
            return self.install_dir[self.config.target_platform]
        except:
            return self.config.install_dir

    def get_sys_deps(self):
        if self.config.target_distro_version in self.sys_deps:
            return self.sys_deps[self.config.target_distro_version]
        if self.config.target_distro in self.sys_deps:
            return self.sys_deps[self.config.target_distro]
        return []

    def __str__(self):
        return self.name


class Package(PackageBase):
    '''
    Describes a set of files to produce disctribution packages for the
    different target platforms

    @cvar deps: list of packages dependencies
    @type deps: list
    @cvar files: list of files included in this package
    @type files: list
    @cvar platform_files: list of platform files included in this package
    @type platform_files: list
    '''

    deps = list()
    files = list()
    platform_files = dict()

    def __init__(self, config, store, cookbook):
        PackageBase.__init__(self, config, store)
        self.cookbook = cookbook
        self._files = self.files + \
                self.platform_files.get(config.target_platform, [])
        self._parse_files()

    def recipes_dependencies(self):
        files = [x.split(':')[0] for x in self._files]
        for name in self.deps:
            p = self.store.get_package(name)
            files += p.recipes_dependencies()
        return files

    def files_list(self):
        files = []
        for recipe_name, categories in self._recipes_files.iteritems():
            recipe = self.cookbook.get_recipe(recipe_name)
            if len(categories) == 0:
                rfiles = recipe.dist_files_list()
            else:
                rfiles = recipe.files_list_by_categories(categories)
            files.extend(rfiles)
        return sorted(files)

    def devel_files_list(self):
        files = []
        for recipe, categories in self._recipes_files.iteritems():
            # only add development files for recipe from which used the 'libs'
            # category
            if len(categories) == 0 or FilesProvider.LIBS_CAT in categories:
                rfiles = self.cookbook.get_recipe(recipe).devel_files_list()
                files.extend(rfiles)
        return sorted(files)

    def all_files_list(self):
        files = self.files_list()
        files.extend(self.devel_files_list())
        return sorted(files)

    def _parse_files(self):
        self._recipes_files = {}
        for r in self._files:
            l = r.split(':')
            self._recipes_files[l[0]] = l[1:]


class MetaPackage(PackageBase):
    '''
    Group of packages used to build an installer package

    @cvar packages: list of packages grouped in this meta package
    @type packages: list
    @cvar platform_packages: list of platform packages
    @type platform_packages: dict
    @cvar icon: filename of the package icon
    @type icon: str
    '''

    icon = None
    packages = []
    platfrom_packages = {}

    def __init__(self, config, store):
        PackageBase.__init__(self, config, store)

    def list_packages(self):
        return [p[0] for p in self.packages]

    def recipes_dependencies(self):
        deps = []
        for package in self.store.get_package_deps(self.name):
            deps.extend(package.recipes_dependencies())
        return list(set(deps))

    def files_list(self):
        return self._list_files(Package.files_list)

    def devel_files_list(self):
        return self._list_files(Package.devel_files_list)

    def all_files_list(self):
        return self._list_files(Package.all_files_list)

    def _list_files(self, func):
        # for each package, call the function that list files
        files = []
        for package in self.store.get_package_deps(self.name):
            files.extend(func(package))
        files.sort()
        return files

    def __getattribute__(self, name):
        if name == 'packages':
            attr = object.__getattribute__(self, name)
            ret = attr[:]
            platform_attr_name = 'platform_%s' % name
            if hasattr(self, platform_attr_name):
                platform_attr = object.__getattribute__(self, platform_attr_name)
                if self.config.target_platform in platform_attr:
                    platform_list = platform_attr[self.config.target_platform]
                    ret.extend(platform_list)
            return ret
        else:
            return object.__getattribute__(self, name)
