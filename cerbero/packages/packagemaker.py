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
from cerbero.packages.package import Package, PackageBase
from cerbero.packages.osx_framework_plist import FrameworkPlist
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

    def pack(self, output_dir, devel=True, force=False, keep_temp=False,
             version=None, target='10.5', install_dir=None,
             include_dirs=None):
        PackagerBase.pack(self, output_dir, devel, force, keep_temp)

        self.install_dir = install_dir or self.package.get_install_dir()
        self.version = version or self.package.version
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
                self.package.version, self.config.target_arch)

    def _create_package(self, package_type, output_dir, force, target):
        self.package.set_mode(package_type)
        files = self.files_list(package_type, force)
        output_file = os.path.join(output_dir, '%s-%s-%s.pkg' %
                (self.package.name, self.version, self.config.target_arch))
        root = self._create_bundle(files, package_type)
        packagemaker = PackageMaker()
        packagemaker.create_package(root, self.package.name,
            self.package.version, self.package.shortdesc, output_file,
            self._get_install_dir(), target)
        return output_file

    def _create_bundle(self, files, package_type):
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
        if package_type == PackageType.DEVEL:
            self._create_framework_headers(tmp)
        return tmp

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



class FrameworkBundlePackager(PackagerBase):
    ''' Creates a package with the basic structure of a framework bundle,
    adding links for Headears, Libraries, Commands, and Current Versions,
    and the Framework info.
    '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)

    def pack(self, output_dir):
        output_dir = os.path.realpath(output_dir)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        self.install_dir = self.package.get_install_dir()

        path = self._create_package(output_dir, self.package.get_install_dir(),
                self.package.version)
        return [path, None]

    def _get_install_dir(self):
        return os.path.join(self.install_dir, 'Versions',
                self.package.version, self.config.target_arch)

    def _create_package(self, output_dir, install_dir, version):
        output_file = os.path.join(output_dir, '%s-%s-%s.pkg' %
                ('osx-framework', self.package.version,
                 self.config.target_arch))
        root = self._create_bundle()
        packagemaker = PackageMaker()
        packagemaker.create_package(root, 'osx-framework',
            self.package.version, 'Framework Bundle', output_file,
            install_dir, target=None)
        return output_file

    def _create_bundle(self):
        '''
        Creates the bundle structure

        Commands -> Versions/Current/bin
        Headers -> Versions/Current/Headers
        Librarires -> Versions/Current/lib
        Home -> Versions/Current
        Resources -> Versions/Current/Resources
        Versions/Current -> Version/$VERSION/$ARCH
        '''
        tmp = tempfile.mkdtemp()

        vdir = 'Versions/%s/%s' % (self.package.version,
                                  self.config.target_arch)
        rdir = '%s/Resources/' % vdir
        shell.call ('mkdir -p %s' % rdir, tmp)
        links = {'Versions/Current': '../%s' % vdir,
                 'Resources': 'Versions/Current/Resources',
                 'Commands': 'Versions/Current/bin',
                 'Headers': 'Versions/Current/Headers',
                 'Libraries': 'Versions/Current/lib'}
        framework_plist = FrameworkPlist(self.package.name,
            self.package.org, self.package.version, self.package.shortdesc)
        framework_plist.save(os.path.join(tmp, rdir, 'Info.plist'))
        for dest, src in links.iteritems():
            shell.call ('ln -s %s %s' % (src, dest), tmp)
        if self.package.osx_framework_library is not None:
            name, link = self.package.osx_framework_library
            link = os.path.join('Versions', 'Current', link)
            shell.call ('ln -s %s %s' % (link, name), tmp)
        return tmp


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
        package = PackageBase(self.config, self.store)
        package.name = 'osx-framework'
        package.shortdesc = 'Framework Bundle'
        package.version = self.package.version
        package.uuid = '3ffe67c2-4565-411f-8287-e8faa892f853'
        package.deps = []
        self.store.add_package(package)
        packages = self.package.packages[:] + [(package.name, True, True)]
        self.package.packages = packages
        packager = FrameworkBundlePackager(self.config, self.package,
                self.store)
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
                        include_dirs=self.include_dirs)
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


class PackageMaker(object):
    ''' Wrapper for the PackageMaker application '''

    PACKAGE_MAKER_PATH = \
        '/Developer/Applications/Utilities/PackageMaker.app/Contents/MacOS/'
    CMD = './PackageMaker'

    def create_package(self, root, pkg_id, version, title, output_file,
                       destination='/opt/', target='10.5'):
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
        if target is not None:
            args['g'] = target
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
