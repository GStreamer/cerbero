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

from cerbero.ide.pkgconfig import PkgConfig
from cerbero.errors import EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.package import Package, MetaPackage, SDKPackage, App,\
        PackageBase
from cerbero.packages.osx.pmdoc import PMDoc
from cerbero.packages.osx.bundles import FrameworkBundlePackager,\
    ApplicationBundlePackager
from cerbero.packages.osx.packagemaker import PackageMaker
from cerbero.tools.osxrelocator import OSXRelocator
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

    def pack(self, output_dir, devel=True, force=False, keep_temp=False,
             version=None, target='10.5', install_dir=None,
             include_dirs=None, sdk_version=None):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        self.install_dir = install_dir or self.package.get_install_dir()
        self.version = version or self.package.version
        self.sdk_version = sdk_version or version
        self.include_dirs = include_dirs or PkgConfig.list_all_include_dirs()

        # create the runtime package
        try:
            runtime_path = self._create_package(PackageType.RUNTIME,
                    output_dir, force, target)
        except EmptyPackageError, e:
            if not devel:
                raise e
            runtime_path = None

        if not devel:
            return [runtime_path, None]

        try:
            # create the development package
            devel_path = self._create_package(PackageType.DEVEL, output_dir,
                    force, target)
        except EmptyPackageError, e:
            if runtime_path is None:
                raise e
            devel_path = None

        return [runtime_path, devel_path]

    def _get_install_dir(self):
        return os.path.join(self.install_dir, 'Versions',
                self.sdk_version, self.config.target_arch)

    def _create_package(self, package_type, output_dir, force, target):
        self.package.set_mode(package_type)
        files = self.files_list(package_type, force)
        output_file = os.path.join(output_dir, '%s-%s-%s.pkg' %
                (self.package.name, self.version, self.config.target_arch))
        root, resources = self._create_bundle(files, package_type)
        packagemaker = PackageMaker()
        packagemaker.create_package(root, self.package.identifier(),
            self.package.version, self.package.shortdesc, output_file,
            self._get_install_dir(), target, scripts_path=resources)
        return output_file

    def _create_bundle(self, files, package_type):
        '''
        Moves all the files that are going to be package to a temporary
        directory to create the bundle
        '''
        tmp = tempfile.mkdtemp()
        root = os.path.join(tmp, 'Root')
        resources = os.path.join(tmp, 'Resources')
        for f in files:
            in_path = os.path.join(self.config.prefix, f)
            if not os.path.exists(in_path):
                m.warning("File %s is missing and won't be added to the "
                          "package" % in_path)
                continue
            out_path = os.path.join(root, f)
            out_dir = os.path.split(out_path)[0]
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            shutil.copy(in_path, out_path)
        if package_type == PackageType.DEVEL:
            self._create_framework_headers(root)

        # Copy scripts to the Resources directory
        os.makedirs(resources)
        if os.path.exists(self.package.resources_preinstall):
            shutil.copy(os.path.join(self.package.resources_preinstall,
                        os.path.join(resources, 'preflight')))
        return root, resources

    def _create_framework_headers(self, tmp):
        '''
        To create a real OS X Framework we need to get rid of the versioned
        directories for headers.
        We should still keep the current tree in $PREFIX/include/ so that it
        still works with pkg-config, but we will create a new $PREFIX/Headers
        folder with links to the include directories removing the versioned
        directories with the help of pkg-config getting something like:
          include/gstreamer-0.10/gst/gst.h -> Headers/gst/gst.h
          include/zlib.h -> Headers/zlib.h
        '''
        # Replace prefix path with the temporal directory one
        include_dirs = [x.replace(self.config.prefix, tmp) for x in
                        self.include_dirs]
        # Remove trailing /
        include_dirs = [os.path.abspath(x) for x in include_dirs]
        # Remove 'include' dir
        include_dirs = [x for x in include_dirs if not x.endswith('include')]

        include = os.path.join(tmp, 'include/')
        headers = os.path.join(tmp, 'Headers')
        self._copy_unversioned_headers(include, include, headers, include_dirs)
        self._copy_versioned_headers(headers, include_dirs)

    def _copy_versioned_headers(self, headers, include_dirs):
        # Path is listed as an includes dir by pkgconfig
        # Copy files and directories to Headers
        for inc_dir in include_dirs:
            if not os.path.exists(inc_dir):
                continue
            for p in os.listdir(inc_dir):
                src = os.path.join(inc_dir, p)
                dest = os.path.join(headers, p)
                if not os.path.exists(os.path.dirname(dest)):
                    os.makedirs(os.path.dirname(dest))
                # include/cairo/cairo.h -> Headers/cairo.h
                if os.path.isfile(src):
                    shutil.copy(src, dest)
                # include/gstreamer-0.10/gst -> Headers/gst
                elif os.path.isdir(src):
                    shell.copy_dir(src, dest)

    def _copy_unversioned_headers(self, dirname, include, headers,
                                  include_dirs):
        if not os.path.exists(dirname):
            return

        for path in os.listdir(dirname):
            path = os.path.join(dirname, path)
            rel_path = path.replace(include, '')
            # include/zlib.h -> Headers/zlib.h
            if os.path.isfile(path):
                p = os.path.join(headers, rel_path)
                d = os.path.dirname(p)
                if not os.path.exists(d):
                    os.makedirs(d)
                shutil.copy(path, p)
            # scan sub-directories
            elif os.path.isdir(path):
                if path in include_dirs:
                    continue
                else:
                    # Copy the directory
                    self._copy_unversioned_headers(path, include,
                            headers, include_dirs)


class PMDocPackage(PackagerBase):
    '''
    Creates an osx package from a L{cerbero.package.package.MetaPackage} using
    a packagemaker's pmdoc file.

    @ivar package: package with the info to build the installer package
    @type package: L{cerbero.packages.package.MetaPackage}
    '''

    PKG_EXT = '.pkg'
    DMG_EXT = '.dmg'

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.packages = self.store.get_package_deps(package)
        self.packages_paths = {}
        self.empty_packages = {}

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        self.include_dirs = PkgConfig.list_all_include_dirs()
        self.tmp = tempfile.mkdtemp()

        self.empty_packages = {PackageType.RUNTIME: [], PackageType.DEVEL: []}
        self.packages_paths = {PackageType.RUNTIME: {}, PackageType.DEVEL: {}}

        if isinstance(self.package, SDKPackage):
            self._create_framework_bundle_package()
        self._create_packages()

        paths = []
        # create runtime package
        r_path = self._create_pmdoc(PackageType.RUNTIME)
        paths.append(r_path)

        if devel:
            # create devel package
            d_path = self._create_pmdoc(PackageType.DEVEL)
            paths.append(d_path)

        # FIXME: Figure out why PackageMaker refuses to create flat meta-packages
        # using flat packages created by himself
        self.package.set_mode(PackageType.RUNTIME)
        for path in paths:
            self._create_dmgs(paths)

        if not keep_temp:
            shutil.rmtree(self.tmp)

        return paths

    def _package_name(self, suffix):
        return '%s-%s-%s%s' % (self.package.name, self.package.version,
                self.config.target_arch, suffix)

    def _create_framework_bundle_package(self):
        m.action(_("Creating framework package"))
        packager = FrameworkBundlePackager(self.package, 'osx-framework',
                'Framework Bundle',
                '3ffe67c2-4565-411f-8287-e8faa892f853')
        package = packager.package
        self.store.add_package(package)
        packages = self.package.packages[:] + [(package.name, True, True)]
        self.package.packages = packages
        path = packager.pack(self.output_dir)[0]
        self.packages_paths[PackageType.RUNTIME][package] = path
        self.empty_packages[PackageType.DEVEL].append(package)

    def _create_pmdoc(self, package_type):
        self.package.set_mode(package_type)
        m.action(_("Creating pmdoc for package %s " % self.package))
        pmdoc = PMDoc(self.package, self.store, self.tmp,
                self.packages_paths[package_type],
                self.empty_packages[package_type], package_type)
        pmdoc_path = pmdoc.create()
        output_file = os.path.join(self.output_dir, self._package_name('.pkg'))
        output_file = os.path.abspath(output_file)
        pm = PackageMaker()
        pm.create_package_from_pmdoc(pmdoc_path, output_file)
        return output_file

    def _create_packages(self):
        for p in self.packages:
            m.action(_("Creating package %s ") % p)
            packager = OSXPackage(self.config, p, self.store)
            try:
                paths = packager.pack(self.output_dir, self.devel, self.force,
                        self.keep_temp, self.package.version, target=None,
                        install_dir=self.package.get_install_dir(),
                        include_dirs=self.include_dirs,
                        sdk_version=self.package.sdk_version)
                m.action(_("Package created sucessfully"))
            except EmptyPackageError:
                paths = [None, None]

            if paths[0] is not None:
                self.packages_paths[PackageType.RUNTIME][p] = paths[0]
            else:
                self.empty_packages[PackageType.RUNTIME].append(p)
            if paths[1] is not None:
                self.packages_paths[PackageType.DEVEL][p] = paths[1]
            else:
                self.empty_packages[PackageType.DEVEL].append(p)

    def _create_dmgs(self, paths):
        for path in paths:
            dmg_file = path.replace(self.PKG_EXT, self.DMG_EXT)
            self._create_dmg(dmg_file, [path])
        packages_dmg_file = os.path.join(self.output_dir,
                self._package_name('-packages.dmg'))
        self._create_dmg(packages_dmg_file,
                self.packages_paths[PackageType.RUNTIME].values())

    def _create_dmg(self, dmg_file, pkg_dirs):
        cmd = 'hdiutil create %s -ov' % dmg_file
        for pkg_dir in pkg_dirs:
            cmd += ' -srcfolder %s' % pkg_dir
        shell.call(cmd)


class ApplicationPackage(PackagerBase):
    '''
    Creates an osx package from a L{cerbero.packages.package.Package}

    @ivar package: package used to create the osx package
    @type package: L{cerbero.packages.package.Package}
    '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        self.tmp = tempfile.mkdtemp()
        self.tmp = os.path.join(self.tmp, '%s.app' % self.package.app_name)

        # copy files to the bundle. it needs to be done first because the app
        # bundle will try to create links for the main executable
        self._create_bundle()
        self._create_app_bundle()
        self._strip_binaries()
        self._relocate_binaries()
        dmg = self._create_dmg()

        return [dmg, None]

    def _create_bundle(self):
        '''
        Moves all the files that are going to be packaged to the bundle's
        temporary directory
        '''
        out_dir = os.path.join(self.tmp, 'Contents', 'Home')
        os.makedirs(out_dir)
        for f in self.package.files_list():
            in_path = os.path.join(self.config.prefix, f)
            if not os.path.exists(in_path):
                m.warning("File %s is missing and won't be added to the "
                          "package" % in_path)
                continue
            out_path = os.path.join(out_dir, f)
            odir = os.path.split(out_path)[0]
            if not os.path.exists(odir):
                os.makedirs(odir)
            shutil.copy(in_path, out_path)

    def _create_app_bundle(self):
        ''' Creates the OS X Application bundle in temporary directory '''
        packager = ApplicationBundlePackager(self.package)
        return packager.create_bundle(self.tmp)

    def _strip_binaries(self):
        pass

    def _relocate_binaries(self):
        prefix = self.config.prefix
        if prefix[-1] == '/':
            prefix = prefix[:-1]
        for path in ['bin']:
            relocator = OSXRelocator(
                    os.path.join(self.tmp, 'Contents', 'Home', path),
                    self.config.prefix, '@executable_path/../', True)
            relocator.relocate()
        for path in ['lib', 'libexec']:
            relocator = OSXRelocator(
                    os.path.join(self.tmp, 'Contents', 'Home', path),
                    self.config.prefix, '@loader_path/../', True)
            relocator.relocate()
        relocator = OSXRelocator(
                    os.path.join(self.tmp, 'Contents', 'MacOS', path),
                    self.config.prefix, '@executable_path/../Home/', False)
        relocator.relocate()

    def _create_dmg(self):
        #applications_link = os.path.join(self.tmp, 'Applications')
        #shell.call('ln -s /Applications %s' % applications_link)
        # Create link to /Applications
        dmg_file = os.path.join(self.output_dir, '%s-%s-%s.dmg' % (
            self.package.app_name, self.package.version, self.config.target_arch))
        # Create Disk Image
        cmd = 'hdiutil create %s -volname %s -ov -srcfolder %s' % \
                (dmg_file, self.package.app_name, self.tmp)
        shell.call(cmd)
        return dmg_file



class Packager(object):

    def __new__(klass, config, package, store):
        if isinstance(package, Package):
            return OSXPackage(config, package, store)
        elif isinstance(package, MetaPackage):
            return PMDocPackage(config, package, store)
        elif isinstance(package, App):
            return ApplicationPackage(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.OS_X, Packager)

