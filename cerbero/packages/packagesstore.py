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
import imp
from collections import defaultdict

from cerbero.build.cookbook import CookBook
from cerbero.config import Platform, Architecture, Distro, DistroVersion,\
        License
from cerbero.packages import package, PackageType
from cerbero.errors import FatalError, PackageNotFoundError
from cerbero.utils import _, shell, remove_list_duplicates
from cerbero.utils import messages as m


class PackagesStore (object):
    '''
    Stores a list of L{cerbero.packages.package.Package}
    '''

    PKG_EXT = '.package'

    def __init__(self, config, load=True, offline=False):
        self._config = config

        self._packages = {}  # package_name -> package

        self.cookbook = CookBook(config, load=load, offline=offline)
        # used in tests to skip loading a dir with packages definitions
        if not load:
            return

        if not os.path.exists(config.packages_dir):
            raise FatalError(_("Packages dir %s not found") %
                             config.packages_dir)
        self._load_packages()

    def get_packages_list(self):
        '''
        Gets the list of packages

        @return: list of packages
        @rtype: list
        '''
        packages = list(self._packages.values())
        packages.sort(key=lambda x: x.name)
        return packages

    def get_package(self, name):
        '''
        Gets a recipe from its name

        @param name: name of the package
        @type name: str
        @return: the package instance
        @rtype: L{cerbero.packages.package.Package}
        '''
        if name not in self._packages:
            raise PackageNotFoundError(name)
        return self._packages[name]

    def get_package_deps(self, pkg, recursive=False):
        '''
        Gets the dependencies of a package

        @param package: name of the package or package instance
        @type package: L{cerbero.packages.package.Package}
        @return: a list with the package dependencies
        @rtype: list
        '''
        if isinstance(pkg, str):
            pkg = self.get_package(pkg)
        if isinstance(pkg, package.MetaPackage):
            ret = self._list_metapackage_deps(pkg)
        else:
            ret = [self.get_package(x) for x in pkg.deps]
        # get deps recursively
        if recursive:
            for p in ret:
                ret.extend(self.get_package_deps(p, recursive))
        return remove_list_duplicates(ret)

    def get_package_files_list(self, name):
        '''
        Gets the list of files provided by a package

        @param name: name of the package
        @type name: str
        @return: the package instance
        @rtype: L{cerbero.packages.package.PackageBase}
        '''
        p = self.get_package(name)

        if isinstance(p, package.MetaPackage):
            return sorted(self._list_metapackage_files(p))
        else:
            return sorted(p.files_list())

    def add_package(self, package):
        '''
        Adds a new package to the store

        @param package: the package to add
        @type  package: L{cerbero.packages.package.PackageBase}
        '''
        self._packages[package.name] = package

    def get_package_recipes_deps(self, package_name):
        '''
        Gets the list of recipes needed to create this package

        @param name: name of the package
        @type name: str
        @return: a list with the recipes required to build this package
        @rtype: list
        '''
        deps = self.get_package_deps(package_name)
        return [self.cookbok.get_recipe(x) for x in deps]

    def _list_metapackage_deps(self, metapackage):

        def get_package_deps(package_name, visited=[], depslist=[]):
            if package_name in visited:
                return
            visited.append(package_name)
            p = self.get_package(package_name)
            depslist.append(p)
            for p_name in p.deps:
                get_package_deps(p_name, visited, depslist)
            return depslist

        deps = []
        for p in metapackage.list_packages():
            deps.extend(get_package_deps(p, [], []))
        return remove_list_duplicates(deps)

    def _list_metapackage_files(self, metapackage):
        l = []
        for p in self._list_metapackage_deps(metapackage):
            l.extend(p.files_list())
        # remove duplicates and sort
        return sorted(list(set(l)))

    def _load_packages(self):
        self._packages = {}
        packages = defaultdict(dict)
        repos = self._config.get_packages_repos()
        for reponame, (repodir, priority) in repos.items():
            packages[int(priority)].update(
                    self._load_packages_from_dir(repodir))
        # Add recipes by asceding pripority
        for key in sorted(packages.keys()):
            self._packages.update(packages[key])

    def _load_packages_from_dir(self, repo):
        packages_dict = {}
        packages = shell.find_files('*%s' % self.PKG_EXT, repo)
        packages.extend(shell.find_files('*/*%s' % self.PKG_EXT, repo))
        try:
            custom = None
            m_path = os.path.join(repo, 'custom.py')
            if os.path.exists(m_path):
                custom = imp.load_source('custom', m_path)
        except Exception as ex:
            # import traceback
            # traceback.print_exc()
            # m.warning("Error loading package %s" % ex)
            custom = None
        for f in packages:
            p = self._load_package_from_file(f, custom)
            if p is None:
                m.warning(_("Could not found a valid package in %s") % f)
                continue
            p.__file__ = os.path.abspath(f)
            packages_dict[p.name] = p
        return packages_dict


    def _load_package_from_file(self, filepath, custom=None):
        mod_name, file_ext = os.path.splitext(os.path.split(filepath)[-1])

        try:
            d = {'Platform': Platform, 'Architecture': Architecture,
                 'Distro': Distro, 'DistroVersion': DistroVersion,
                 'License': License, 'package': package,
                 'PackageType': PackageType, 'custom': custom}
            exec(compile(open(filepath).read(), filepath, 'exec'), d)
            if 'Package' in d:
                p = d['Package'](self._config, self, self.cookbook)
            elif 'SDKPackage' in d:
                p = d['SDKPackage'](self._config, self)
            elif 'InstallerPackage' in d:
                p = d['InstallerPackage'](self._config, self)
            elif 'App' in d:
                p = d['App'](self._config, self, self.cookbook)
            else:
                raise Exception('Package, SDKPackage, InstallerPackage or App '
                                'class not found')
            p.prepare()
            # reload files from package now that we called prepare that
            # may have changed it
            p.load_files()
            return p
        except Exception as ex:
            import traceback
            traceback.print_exc()
            m.warning("Error loading package %s" % ex)
        return None
