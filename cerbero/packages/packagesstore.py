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

from cerbero.config import Platform, Architecture, Distro, DistroVersion
from cerbero.packages import package
from cerbero.build import BuildType
from cerbero.source import SourceType
from cerbero.errors import FatalError, PackageNotFoundError
from cerbero.utils import _
from cerbero.utils import messages as m


class PackagesStore (object):
    '''
    Stores a list of L{cerbero.packages.package.Package}

    @ivar packages: L{cerbero.packages.package.Package} availables
    @type packages: dict
    '''

    packages = {}  # package_name -> package

    def __init__(self, config):
        self._config = config
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
        packages = self.packages.values()
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
        if name not in self.packages:
            raise PackageNotFoundError(name)
        return self.packages[name]

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
            return self._list_metapackage_files(p)
        else:
            return p.get_files_list()

    def _list_metapackage_files(self, metapackage):
        l = []
        for p in self._list_metapackage_packages(metapackage):
            l.extend(p.get_files_list())
        # remove duplicates and sort
        return sorted(list(set(l)))

    def _list_metapackage_packages(self, metapackage):

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
        return list(set(deps))

    def _load_packages(self):
        self.packages = {}
        for f in os.listdir(self._config.packages_dir):
            filepath = os.path.join(self._config.packages_dir, f)
            p = self._load_package_from_file(filepath)
            if p is None:
                m.warning(_("Could not found a valid package in %s") %
                                f)
                continue
            self.packages[p.name] = p

    def _load_package_from_file(self, filepath):
        mod_name, file_ext = os.path.splitext(os.path.split(filepath)[-1])
        try:
            d = {'Platform': Platform, 'Architecture': Architecture,
                 'BuildType': BuildType, 'SourceType': SourceType,
                 'Distro': Distro, 'DistroVersion': DistroVersion,
                 'package': package}
            execfile(filepath, d)
            if 'Package' in d:
                p = d['Package'](self._config)
            elif 'MetaPackage' in d:
                p = d['MetaPackage'](self._config)
            return p
        except Exception, ex:
            import traceback
            traceback.print_exc()
            m.warning("Error loading package %s" % ex)
        return None
