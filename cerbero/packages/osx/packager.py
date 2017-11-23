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

from cerbero.config import Architecture, Platform
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.ide.xcode.fwlib import StaticFrameworkLibrary
from cerbero.errors import EmptyPackageError, FatalError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.package import Package, MetaPackage, App,\
        PackageBase, SDKPackage
from cerbero.packages.osx.distribution import DistributionXML
from cerbero.packages.osx.bundles import FrameworkBundlePackager,\
    ApplicationBundlePackager
from cerbero.packages.osx.buildtools import PackageBuild, ProductBuild
from cerbero.tools.osxrelocator import OSXRelocator
from cerbero.utils import shell, _
from cerbero.tools import strip
from cerbero.utils import messages as m


class FrameworkHeadersMixin(object):

    def _create_framework_headers(self, prefix, include_dirs, tmp):
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
        include_dirs = [x.replace(os.path.abspath(prefix), tmp)
                        for x in include_dirs]
        # Remove trailing /
        include_dirs = [os.path.abspath(x) for x in include_dirs]
        # Remove 'include' dir
        include_dirs = [x for x in include_dirs if not
                        x.endswith(os.path.join(tmp, 'include'))]
        include_dirs = [x for x in include_dirs if os.path.isdir(x)]

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


class OSXPackage(PackagerBase, FrameworkHeadersMixin):
    '''
    Creates an osx package from a L{cerbero.packages.package.Package}

    @ivar package: package used to create the osx package
    @type package: L{cerbero.packages.package.Package}
    '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)

    def pack(self, output_dir, devel=True, force=False, keep_temp=False,
             version=None, install_dir=None, include_dirs=None,
             sdk_version=None):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        self.install_dir = install_dir or self.package.get_install_dir()
        self.version = version or self.package.version
        self.sdk_version = sdk_version or self.version
        self.include_dirs = include_dirs or PkgConfig.list_all_include_dirs()

        # create the runtime package
        try:
            runtime_path = self._create_package(PackageType.RUNTIME,
                    output_dir, force)
        except EmptyPackageError, e:
            if not devel:
                raise e
            runtime_path = None

        if not devel:
            return [runtime_path, None]

        try:
            # create the development package
            devel_path = self._create_package(PackageType.DEVEL, output_dir,
                    force)
        except EmptyPackageError, e:
            if runtime_path is None:
                raise e
            devel_path = None

        return [runtime_path, devel_path]

    def _get_install_dir(self):
        #if self.config.target_arch != Architecture.UNIVERSAL:
        #    arch_dir = self.config.target_arch
        #else:
        #    arch_dir = ''
        return os.path.join(self.install_dir, 'Versions',
                self.sdk_version) #, arch_dir)

    def _create_package(self, package_type, output_dir, force):
        self.package.set_mode(package_type)
        files = self.files_list(package_type, force)
        output_file = os.path.join(output_dir, '%s-%s-%s.pkg' %
                (self.package.name, self.version, self.config.target_arch))
        tmp, root, resources = self._create_bundle(files, package_type)
        packagebuild = PackageBuild()
        packagebuild.create_package(root, self.package.identifier(),
            self.package.version, self.package.shortdesc, output_file,
            self._get_install_dir(), scripts_path=resources)
        shutil.rmtree(tmp)
        return output_file

    def _create_bundle(self, files, package_type):
        '''
        Moves all the files that are going to be packaged to a temporary
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
            self._create_framework_headers(self.config.prefix, self.include_dirs, root)

        # Copy scripts to the Resources directory
        os.makedirs(resources)
        if os.path.exists(self.package.resources_preinstall):
            shutil.copy(os.path.join(self.package.resources_preinstall),
                        os.path.join(resources, 'preinstall'))
        if os.path.exists(self.package.resources_postinstall):
            shutil.copy(os.path.join(self.package.resources_postinstall),
                        os.path.join(resources, 'postinstall'))
        return tmp, root, resources



class ProductPackage(PackagerBase):
    '''
    Creates an osx package from a L{cerbero.package.package.MetaPackage} using
    productbuild.

    @ivar package: package with the info to build the installer package
    @type package: L{cerbero.packages.package.MetaPackage}
    '''

    PKG_EXT = '.pkg'
    home_folder = False

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.packages = self.store.get_package_deps(package)
        self.packages_paths = {}
        self.empty_packages = {}

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        self._prepare_pack()

        if isinstance(self.package, MetaPackage):
            packager = self._create_framework_bundle_packager()
            self._create_framework_bundle_layout(packager)
            self._create_framework_bundle_package(packager)
        self._create_packages()

        paths = []
        try:
            # create runtime package
            r_path = self._create_product(PackageType.RUNTIME)
            paths.append(r_path)

            if devel:
                # create devel package
                d_path = self._create_product(PackageType.DEVEL)
                paths.append(d_path)

            self.package.set_mode(PackageType.RUNTIME)
            self._create_packages_dmg()
        finally:
            if not keep_temp:
                shutil.rmtree(self.tmp)

        return paths

    def _prepare_pack(self):
        self.include_dirs = PkgConfig.list_all_include_dirs()
        self.tmp = tempfile.mkdtemp()
        self.fw_path = self.tmp

        self.empty_packages = {PackageType.RUNTIME: [], PackageType.DEVEL: []}
        self.packages_paths = {PackageType.RUNTIME: {}, PackageType.DEVEL: {}}


    def _package_name(self, suffix):
        return '%s-%s-%s%s' % (self.package.name, self.package.version,
                self.config.target_arch, suffix)

    def _create_framework_bundle_packager(self):
        m.action(_("Creating framework package"))
        packager = FrameworkBundlePackager(self.package, 'osx-framework',
                'GStreamer',
                'GStreamer OSX Framework Bundle Version %s' % (self.package.version),
                '3ffe67c2-4565-411f-8287-e8faa892f853')
        return packager

    def _create_framework_bundle_layout(self, packager):
        packager.create_bundle(self.fw_path)

    def _create_framework_bundle_package(self, packager):
        package = packager.package
        package.install_dir = self.package.install_dir
        self.store.add_package(package)
        packages = self.package.packages[:] + [(package.name, True, True)]
        self.package.packages = packages
        path = packager.pack(self.output_dir, self.fw_path)[0]
        if self.config.target_platform == Platform.IOS:
            self.packages_paths[PackageType.DEVEL][package] = path
            self.empty_packages[PackageType.RUNTIME].append(package)
        else:
            self.packages_paths[PackageType.RUNTIME][package] = path
            self.empty_packages[PackageType.DEVEL].append(package)

    def _create_product(self, package_type):
        self.package.set_mode(package_type)
        m.action(_("Creating Distribution.xml for package %s " % self.package))
        distro = DistributionXML(self.package, self.store, self.tmp,
            self.packages_paths[package_type],
            self.empty_packages[package_type], package_type,
            self.config.target_arch, home_folder=self.home_folder)
        distro_path = os.path.join(self.tmp, "Distribution.xml")
        distro.write(distro_path)
        output_file = os.path.join(self.output_dir, self._package_name('.pkg'))
        output_file = os.path.abspath(output_file)
        pb = ProductBuild()
        pb.create_package(distro_path, output_file, [self.package.relative_path('.')])
        return output_file

    def _create_packages(self):
        for p in self.packages:
            m.action(_("Creating package %s ") % p)
            packager = OSXPackage(self.config, p, self.store)
            try:
                paths = packager.pack(self.output_dir, self.devel, self.force,
                        self.keep_temp, self.package.version,
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

    def _create_packages_dmg(self):
        paths = self.packages_paths[PackageType.RUNTIME].values()
        dmg_file = os.path.join(self.output_dir,
            self._package_name('-packages.dmg'))

        m.action(_("Creating image %s ") % dmg_file)
        # create a temporary directory to store packages
        workdir = os.path.join (self.tmp, "hdidir")
        os.makedirs(workdir)
        try:
            for p in paths:
                shutil.copy(p, workdir)
            # Create Disk Image
            cmd = 'hdiutil create %s -ov -srcfolder %s' % (dmg_file, workdir)
            shell.call(cmd)
        finally:
            shutil.rmtree(workdir)


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
        self.approot = os.path.join(self.tmp, 'app')
        self.appdir = os.path.join(self.approot, '%s.app' % self.package.app_name)

        # copy files to the bundle. it needs to be done first because the app
        # bundle will try to create links for the main executable
        self._create_bundle()
        self._create_app_bundle()
        self._strip_binaries()
        self._relocate_binaries()
        if self.package.osx_create_pkg:
            pkg = self._create_product()
            self._add_applications_link()
        else:
            pkg = ''
        if self.package.osx_create_dmg:
            dmg = self._create_dmg()
        else:
            dmg = ''

        return [dmg, pkg]

    def _create_bundle(self):
        '''
        Moves all the files that are going to be packaged to the bundle's
        temporary directory
        '''
        out_dir = os.path.join(self.appdir, 'Contents', 'Home')
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
        return packager.create_bundle(self.appdir)

    def _strip_binaries(self):
        if self.package.strip:
            for f in self.package.strip_dirs:
                s_dir = os.path.join(self.appdir, 'Contents', 'Home', f)
                s = strip.Strip(self.config, self.package.strip_excludes)
                s.strip_dir(s_dir)

    def _relocate_binaries(self):
        if not self.package.relocate_osx_binaries:
            return
        prefix = self.config.prefix
        if prefix[-1] == '/':
            prefix = prefix[:-1]
        for path in ['bin', 'lib', 'libexec']:
            relocator = OSXRelocator(
                    os.path.join(self.appdir, 'Contents', 'Home', path),
                    self.config.prefix, '@executable_path/../', True)
            relocator.relocate()

    def _add_applications_link(self):
        # Create link to /Applications
        applications_link = os.path.join(self.approot, 'Applications')
        shell.call('ln -s /Applications %s' % applications_link)

    def _package_name(self, suffix):
        return '%s-%s-%s%s' % (self.package.name, self.package.version,
                self.config.target_arch, suffix)

    def _copy_scripts(self):
        resources = os.path.join(self.tmp, 'Resources')
        # Copy scripts to the Resources directory
        os.makedirs(resources)
        if os.path.exists(self.package.resources_preinstall):
            shutil.copy(os.path.join(self.package.resources_preinstall),
                        os.path.join(resources, 'preinstall'))
        if os.path.exists(self.package.resources_postinstall):
            shutil.copy(os.path.join(self.package.resources_postinstall),
                        os.path.join(resources, 'postinstall'))
        return resources

    def _create_product(self):
        packagebuild = PackageBuild()
        resources = self._copy_scripts()
        app_pkg_name = self._package_name('.pkg')
        app_pkg = os.path.join(self.tmp, app_pkg_name)
        packagebuild.create_package(self.approot, self.package.identifier(),
            self.package.version, self.package.shortdesc, app_pkg,
            '/Applications', scripts_path=resources)
        self.package.packages = [(self.package.name, True, True)]
        m.action(_("Creating Distribution.xml for package %s " % self.package))
        distro = DistributionXML(self.package, self.store, self.tmp,
            {self.package: app_pkg_name},
            self.store.get_package_deps(self.package),
            PackageType.RUNTIME,
            self.config.target_arch, home_folder=False)
        distro_path = tempfile.NamedTemporaryFile().name
        distro.write(distro_path)
        output_file = os.path.join(self.output_dir, self._package_name('.pkg'))
        output_file = os.path.abspath(output_file)
        pb = ProductBuild()
        pb.create_package(distro_path, output_file,
            [self.package.relative_path('.'), self.tmp])
        return output_file

    def _create_dmg(self):
        dmg_file = os.path.join(self.output_dir, '%s-%s-%s.dmg' % (
            self.package.app_name, self.package.version, self.config.target_arch))
        # Create Disk Image
        cmd = 'hdiutil create %s -volname %s -ov -srcfolder %s' % \
                (dmg_file, self.package.app_name, self.approot)
        shell.call(cmd)
        return dmg_file


class IOSPackage(ProductPackage, FrameworkHeadersMixin):
    '''
    Creates an ios Framework package from a
    L{cerbero.package.package.MetaPackage} using productbuild.

    This platform only support static linking, so the final package
    consists on a the framework library and the headers files.
    The framework library is built merging all the static libraries
    listed in this package and the headers are copied unversionned to
    the 'Headers' directory of the framework bundle.
    The product package will only contain the ios-framework package
    '''

    home_folder = True
    user_resources = []

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        framework_name = self.package.osx_framework_library[0]
        self._prepare_pack()
        self.fw_path = os.path.join(self.tmp, '%s.framework' % framework_name)
        os.mkdir(self.fw_path)

        files = [os.path.join(self.config.prefix, x) for x in
                 self.package.all_files_list()]

        version_dir = os.path.join(self.fw_path, 'Versions', self.package.sdk_version)
        libname = os.path.join(version_dir, framework_name)
        packager = self._create_framework_bundle_packager()
        self._create_framework_bundle_layout(packager)
        self._copy_templates(files)
        self._copy_headers(files, version_dir)
        self._create_framework_headers(self.config.prefix,
                                       self.include_dirs, version_dir)
        if os.path.exists(os.path.join(version_dir, 'include')):
            shutil.rmtree(os.path.join(version_dir, 'include'))
        if os.path.exists(os.path.join(version_dir, 'lib')):
            shutil.rmtree(os.path.join(version_dir, 'lib'))
        self._create_merged_lib(libname, files)
        self.package.packages = []
        self.fw_path = self.tmp
        self._create_framework_bundle_package(packager)
        self.fw_path = os.path.join(self.tmp, '%s.framework' % framework_name)

        if isinstance(self.package, SDKPackage):
            pkg_path = self._create_product(PackageType.DEVEL)
            if self.package.user_resources:
                pkg_path = self._create_dmg (pkg_path,
                    pkg_path.replace('.pkg', '.dmg'))
        else:
            pkg_path = self._create_dmg (self.fw_path,
                os.path.join(output_dir, self._package_name('.dmg')))

        if not keep_temp:
            shutil.rmtree(self.tmp)
        return [pkg_path]

    def _copy_files (self, files, root):
        for f in files:
            out_path = f.replace(self.config.prefix, root)
            out_dir = os.path.split(out_path)[0]
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            shutil.copy(f, out_path)

    def _copy_templates(self, files):
        templates_prefix = 'share/xcode/templates/ios'
        templates = [x for x in files if templates_prefix in x]
        for f in templates:
            out_path = f.replace(self.config.prefix,
                    os.path.join(self.tmp, 'Templates'))
            out_path = out_path.replace(templates_prefix, '')
            out_dir = os.path.split(out_path)[0]
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            shutil.copy(f, out_path)

    def _copy_headers(self, files, version_dir):
        # Get the list of headers
        include_files = []
        include_dirs = self.include_dirs
        # Also copy all headers like include/zlib.h that are not in a
        # include path given by pkg-config because it's the default one
        include_dirs.append(os.path.join(self.config.prefix, 'include'))
        for d in include_dirs:
            include_files += [x for x in files if d in x]
        self._copy_files (include_files, version_dir)

    def _create_framework_bundle_packager(self):
        m.action(_("Creating framework package"))
        packager = FrameworkBundlePackager(self.package, 'ios-framework',
                'GStreamer',
                'GStreamer iOS Framework Bundle Version %s' % (self.package.version),
                '3ffe67c2-3421-411f-8287-e8faa892f853')
        return packager

    def _create_merged_lib(self, libname, files):
        # Get the list of static libraries
        static_files = [x for x in files if x.endswith('.a')]

        fwlib = StaticFrameworkLibrary(libname, libname, static_files,
            self.config.target_arch)
        fwlib.use_pkgconfig = False
        if self.config.target_arch == Architecture.UNIVERSAL:
            fwlib.universal_archs = self.config.universal_archs
        fwlib.create()

    def _package_name(self, suffix):
        return '%s-%s-%s-%s%s' % (self.package.name, self.package.version,
                self.config.target_platform, self.config.target_arch, suffix)

    def _create_dmg(self, pkg_path, dmg_file):
        # Create a new folder with the pkg and the user resources
        dmg_dir = os.path.join(self.tmp, 'dmg')
        os.makedirs(dmg_dir)
        for r in self.package.user_resources:
            r = os.path.join(self.config.prefix, r)
            r_dir = os.path.split(r)[1]
            shell.copy_dir (r, os.path.join(dmg_dir, r_dir))
        shutil.move(pkg_path, dmg_dir)

        # Create Disk Image
        cmd = 'hdiutil create %s -volname %s -ov -srcfolder %s' % \
            (dmg_file, self.package.name, dmg_dir)
        shell.call(cmd)
        return dmg_file

class Packager(object):

    def __new__(klass, config, package, store):
        if config.target_platform == Platform.IOS:
            if not isinstance(package, MetaPackage):
                raise FatalError ("iOS platform only support packages",
                                  "for MetaPackage")
            return IOSPackage(config, package, store)
        if isinstance(package, Package):
            return OSXPackage(config, package, store)
        elif isinstance(package, MetaPackage):
            return ProductPackage(config, package, store)
        elif isinstance(package, App):
            return ApplicationPackage(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.OS_X, Packager)
    register_packager(Distro.IOS, Packager)
