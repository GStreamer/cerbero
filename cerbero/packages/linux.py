# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
# Copyright (C) 2012 Collabora Ltd. <http://www.collabora.co.uk/>
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

from cerbero.config import DEFAULT_PACKAGER
from cerbero.errors import EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.disttarball import DistTarball
from cerbero.packages.package import MetaPackage, App
from cerbero.utils import _
from cerbero.utils import messages as m

import shutil


class LinuxPackager(PackagerBase):

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.package_prefix = ''
        self.package_prefix = self._package_prefix(self.package)
        self.full_package_name = self._full_package_name()
        self.packager = self.config.packager
        self._check_packager()

    def pack(self, output_dir, devel=True, force=False, keep_temp=False,
             pack_deps=True, tmpdir=None):
        self.install_dir = self.package.get_install_dir()
        self.devel = devel
        self.force = force
        self._empty_packages = []

        # Create a tmpdir for packages
        tmpdir, packagedir, srcdir = self.create_tree(tmpdir)

        # only build each package once
        if isinstance(self.package, App) and self.package.embed_deps:
            pass
        elif pack_deps:
            self.pack_deps(output_dir, tmpdir, force)

        if not isinstance(self.package, MetaPackage):
            # create a tarball with all the package's files
            tarball_packager = DistTarball(self.config, self.package,
                    self.store)
            tarball = tarball_packager.pack(tmpdir, devel, True,
                    split=False, package_prefix=self.full_package_name)[0]
            tarname = self.setup_source(tarball, tmpdir, packagedir, srcdir)
        else:
            # metapackages only contains Requires dependencies with
            # other packages
            tarname = None

        m.action(_('Creating package for %s') % self.package.name)

        try:
            # do the preparations, fill spec file, write debian files, etc
            self.prepare(tarname, tmpdir, packagedir, srcdir)

            # and build the package
            paths = self.build(output_dir, tarname, tmpdir, packagedir, srcdir)

            stamp_path = os.path.join(tmpdir, self.package.name + '-stamp')
            open(stamp_path, 'w').close()
        finally:
            if not keep_temp:
                m.action(_('Removing temporary dir %s') % tmpdir)
                shutil.rmtree(tmpdir)

        return paths

    def setup(self):
        pass

    def create_tree(self, tmpdir):
        pass

    def setup_source(self, tarball, tmpdir, packagedir, srcdir):
        pass

    def prepare(self, tarname, tmpdir, packagedir, srcdir):
        pass

    def build(self, output_dir, tarname, tmpdir, packagedir, srcdir):
        pass

    def pack_deps(self, output_dir, tmpdir, force):
        for p in self.store.get_package_deps(self.package.name):
            stamp_path = os.path.join(tmpdir, p.name + '-stamp')
            if os.path.exists(stamp_path):
                # already built, skipping
                continue

            m.action(_('Packing dependency %s for package %s') %
                     (p.name, self.package.name))
            packager = self.__class__(self.config, p, self.store)
            try:
                packager.pack(output_dir, self.devel, force, True, True, tmpdir)
            except EmptyPackageError:
                self._empty_packages.append(p)

    def get_meta_requires(self, package_type, package_suffix):
        requires = []
        suggests = []
        recommends = []
        for p in self.package.packages:
            package = self.store.get_package(p[0])
            if package_type == PackageType.RUNTIME:
                if not self._has_runtime_package(package):
                    continue
            if package_type == PackageType.DEVEL:
                if not self._has_devel_package(package):
                    continue
            package_name = '%s%s' % (self._package_prefix(package), p[0])
            if package_type == PackageType.DEVEL:
                package_name += package_suffix
            if p[1]:
                requires.append(package_name)
            elif p[2]:
                recommends.append(package_name)
            else:
                suggests.append(package_name)
        # Development packages should depend on the runtime package
        if package_type == PackageType.DEVEL:
            requires.append(self.package.name)
        return (requires, recommends, suggests)

    def get_requires(self, package_type, devel_suffix):
        deps = self.store.get_package_deps(self.package.name)
        deps = list(set(deps) - set(self._empty_packages))

        def dep_name(p):
            name = '%s%s' % (self._package_prefix(p), p.name)
            if package_type == PackageType.DEVEL:
                name += devel_suffix
            return name

        if package_type == PackageType.DEVEL:
            deps = [x for x in deps if self._has_devel_package(x)]

        deps = [dep_name(x) for x in deps]

        # Development packages should depend on the runtime package
        if package_type == PackageType.DEVEL:
            if self._has_runtime_package(self.package):
                deps.append("%s%s" % (self._package_prefix(self.package), self.package.name))

        deps.extend(self.package.get_sys_deps(package_type))
        return sorted(deps)

    def recipes_licenses(self):
        licenses = []
        recipes_licenses = self.package.recipes_licenses()
        recipes_licenses.update(self.package.devel_recipes_licenses())
        for recipe_name, categories_licenses in recipes_licenses.iteritems():
            for category_licenses in categories_licenses.itervalues():
                licenses.extend(category_licenses)
        return sorted(list(set(licenses)))

    def files_list(self, package_type):
        if isinstance(self.package, MetaPackage):
            return ''
        return PackagerBase.files_list(self, package_type, self.force)

    def _package_prefix(self, package):
        if self.config.packages_prefix not in [None, '']:
            if not package.ignore_package_prefix:
                return '%s-' % self.config.packages_prefix
        return ''

    def _full_package_name(self):
        return '%s%s-%s' % (self.package_prefix, self.package.name,
                            self.package.version)

    def _check_packager(self):
        if self.packager == DEFAULT_PACKAGER:
            m.warning(_('No packager defined, using default '
                        'packager "%s"') % self.packager)

    def _has_runtime_package(self, package):
        if hasattr(package, 'has_runtime_package'):
            return package.has_runtime_package
        return False

    def _has_devel_package(self, package):
        if hasattr(package, 'has_devel_package'):
            return package.has_devel_package
        return False
