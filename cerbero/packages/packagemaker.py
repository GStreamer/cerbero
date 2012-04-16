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
import tempfile
import shutil

from cerbero.errors import EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.package import Package
from cerbero.packages.pmdoc import PMDoc
from cerbero.utils import shell, _
from cerbero.utils import messages as m


class OSXPackage(PackagerBase):
    '''
    Creates an osx package from a L{cerbero.packages.package.Package}

    @ivar package: package used to create the osx package
    @type package: L{cerbero.packages.package.Package}
    '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)

    def pack(self, output_dir, devel=True, force=False):
        output_dir = os.path.realpath(output_dir)

        # create the runtime package
        runtime_path = self._create_package(PackageType.RUNTIME, output_dir,
                force)

        if not devel:
            return [runtime_path]

        try:
            # create the development package
            devel_path = self._create_package(PackageType.DEVEL, output_dir,
                    force)
        except EmptyPackageError:
            devel_path = None
        return [runtime_path, devel_path]

    def _create_package(self, package_type, output_dir, force):
        package_name = self.package.name + package_type
        files = self.files_list(package_type, force)
        output_file = os.path.join(output_dir, '%s.pkg' % package_name)
        root = self._create_bundle(files)
        packagemaker = PackageMaker()
        packagemaker.create_package(root, package_name,
            self.package.version, self.package.shortdesc, output_file,
            self.package.get_install_dir())
        return output_file

    def _create_bundle(self, files):
        '''
        Moves all the files that are going to be package to a temporary
        directory to create the bundle
        '''
        tmp = tempfile.mkdtemp()
        for f in files:
            in_path = os.path.join(self.config.prefix, f)
            if not os.path.exists(in_path):
                m.warning("File %s is missing and won't be added to the "
                          "package" % in_path)
                continue
            out_path = os.path.join(tmp, f)
            out_dir = os.path.split(out_path)[0]
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            shutil.copy(in_path, out_path)
        return tmp


class PMDocPackage(PackagerBase):
    '''
    Creates an osx package from a L{cerbero.package.package.MetaPackage} using
    a packagemaker's pmdoc file

    @ivar package: package with the info to build the installer package
    @type package: L{cerbero.packages.package.MetaPackage}
    '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.packages = self.store.get_package_deps(package.name)
        self.packages_paths = dict()

    def pack(self, output_dir, devel=False, force=False):
        self.tmp = tempfile.mkdtemp()

        self._create_packages(devel, force)

        paths = []
        # create runtime package
        r_path = self._create_pmdoc(PackageType.RUNTIME, force, output_dir)
        paths.append(r_path)

        if devel:
            # create devel package
            d_path = self._create_pmdoc(PackageType.DEVEL, force, output_dir)
            paths.append(d_path)

        return paths

    def _create_pmdoc(self, package_type, force, output_dir):
        m.action(_("Creating pmdoc for package %s " % self.package))
        pmdoc = PMDoc(self.package, self.store, self.tmp, self.packages_paths,
                      self.empty_packages, package_type)
        pmdoc_path = pmdoc.create()

        output_file = os.path.abspath(os.path.join(output_dir, '%s.pkg' %
            (self.package.name + package_type)))
        pm = PackageMaker()
        pm.create_package_from_pmdoc(pmdoc_path, output_file)
        return output_file

    def _create_packages(self, devel, force):
        self.empty_packages = []
        for p in self.packages:
            m.action(_("Creating package %s ") % p)
            packager = OSXPackage(self.config, p, self.store)
            try:
                paths = packager.pack(self.tmp, devel, force)
            except EmptyPackageError:
                self.empty_packages.append(p.name)
                m.warning(_("Package %s is empty") % p)
            m.action(_("Package created sucessfully"))
            self.packages_paths[p.name] = paths[0]
            if devel:
                devel_name = p.name + PackageType.DEVEL
                if paths[1] is not None:
                    self.packages_paths[devel_name] = paths[1]
                else:
                    self.empty_packages.append(devel_name)


class PackageMaker(object):
    ''' Wrapper for the PackageMaker application '''

    PACKAGE_MAKER_PATH = \
        '/Developer/Applications/Utilities/PackageMaker.app/Contents/MacOS/'
    CMD = './PackageMaker'

    def create_package(self, root, pkg_id, version, title, output_file,
                       destination='/opt/'):
        '''
        Creates an osx package, where all files are properly bundled in a
        directory that is set as the package root

        @param root: root path
        @type  root: str
        @param pkg_id: package indentifier
        @type  pkg_id: str
        @param version: package version
        @type  version: str
        @param title: package title
        @type  title: str
        @param output_file: path of the output file
        @type  output_file: str
        @param destination: installation path
        @type  destination: str
        '''
        args = {'r': root, 'i': pkg_id, 'n': version, 't': title,
                'l': destination, 'o': output_file}
        self._execute(self._cmd_with_args(args))

    def create_package_from_pmdoc(self, pmdoc_path, output_file):
        '''
        Creates an osx package from a pmdoc configuration files
        '''
        args = {'d': pmdoc_path, 'o': output_file}
        self._execute(self._cmd_with_args(args))

    def _cmd_with_args(self, args):
        args_str = ''
        for k, v in args.iteritems():
            args_str += " -%s '%s'" % (k, v)
        return '%s %s' % (self.CMD, args_str)

    def _execute(self, cmd):
        shell.call(cmd, self.PACKAGE_MAKER_PATH)


class Packager(object):

    def __new__(klass, config, package, store):
        if isinstance(package, Package):
            return OSXPackage(config, package, store)
        else:
            return PMDocPackage(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.OS_X, Packager)
