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

from cerbero.config import Architecture
from cerbero.packages import PackagerBase
from cerbero.packages.package import Package
from cerbero.packages.osx.buildtools import PackageBuild
from cerbero.packages.osx.info_plist import FrameworkPlist, ApplicationPlist
from cerbero.utils import shell


class BundlePackagerBase(PackagerBase):
    '''
    Creates a package with the basic structure of a bundle, to be included
    in a MetaPackage.
    '''

    def __init__(self, package, name, desc, uuid):
        self.package = Package(package.config, package.store, None)
        self.package.name = name
        self.package.shortdesc = desc
        self.package.version = package.version
        self.package.sdk_version = package.sdk_version
        self.package.uuid = uuid
        self.package.deps = []
        self.package.org = package.org
        self.package.install_dir = package.install_dir
        self.package.osx_framework_library = package.osx_framework_library
        self.package.resources_preinstall = package.resources_preinstall
        self.package.resources_postinstall = package.resources_postinstall
        self.package.__file__ = package.__file__
        PackagerBase.__init__(self, package.config, self.package, package.store)

    def pack(self, output_dir, root=None):
        output_dir = os.path.realpath(output_dir)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        path = self._create_package(output_dir, self.package.get_install_dir(),
                self.package.version, root)
        return [path, None]


    def _create_package(self, output_dir, install_dir, version, root):
        output_file = os.path.join(output_dir, '%s-%s-%s.pkg' %
                (self.name, self.package.version,
                 self.config.target_arch))
        if not root:
            root = self.create_bundle()

        resources = tempfile.mkdtemp()
        if os.path.exists(self.package.resources_preinstall):
            shutil.copy(os.path.join(self.package.resources_preinstall),
                        os.path.join(resources, 'preinstall'))
        if os.path.exists(self.package.resources_postinstall):
            shutil.copy(os.path.join(self.package.resources_postinstall),
                        os.path.join(resources, 'postinstall'))
        packagebuild = PackageBuild()
        packagebuild.create_package(root, self.package.identifier(),
            self.package.version, self.title, output_file, install_dir,
            resources)
        shutil.rmtree(resources)
        return output_file

    def create_bundle(self, target_dir=None):
        '''
        Creates the bundle structure
        '''
        raise NotImplemented('Subclasses should implement create_bundle')


class FrameworkBundlePackager(BundlePackagerBase):
    '''
    Creates a package with the basic structure of a framework bundle,
    adding links for Headears, Libraries, Commands, and Current Versions,
    and the Framework info.
    '''

    name = 'osx-framework'
    title = 'Framework Bundle'

    def __init__(self, package, name, desc, uuid):
        BundlePackagerBase.__init__(self, package, name, desc, uuid)

    def create_bundle(self, target_dir=None):
        '''
        Creates the bundle structure

        Commands -> Versions/Current/Commands
        Headers -> Versions/Current/Headers
        Libraries -> Versions/Current/Libraries
        Home -> Versions/Current
        Resources -> Versions/Current/Resources
        Versions/Current -> Version/$VERSION/$ARCH
        Framework -> Versions/Current/Famework
        '''
        if target_dir:
            tmp = target_dir
        else:
            tmp = tempfile.mkdtemp()

        #if self.config.target_arch == Architecture.UNIVERSAL:
        #    arch_dir = ''
        #else:
        #    arch_dir = self.config.target_arch

        vdir = os.path.join('Versions', self.package.sdk_version) #, arch_dir)
        rdir = '%s/Resources/' % vdir
        shell.call ('mkdir -p %s' % rdir, tmp)

        links = {'Versions/Current': '../%s' % vdir,
                 'Resources': 'Versions/Current/Resources',
                 'Commands': 'Versions/Current/Commands',
                 'Headers': 'Versions/Current/Headers',
                 'Libraries': 'Versions/Current/Libraries'}
        inner_links = {'Commands': 'bin',
                       'Libraries': 'lib'}

        # Create the frameworks Info.plist file
        framework_plist = FrameworkPlist(self.package.name,
            self.package.org, self.package.version, self.package.shortdesc,
            self.package.config.min_osx_sdk_version)
        framework_plist.save(os.path.join(tmp, rdir, 'Info.plist'))

        # Add a link from Framework to Versions/Current/Framework
        if self.package.osx_framework_library is not None:
            name, link = self.package.osx_framework_library
            # Framework -> Versions/Current/Famework
            links[name] = 'Versions/Current/%s' % name

        # Create all links
        for dest, src in links.items():
            shell.call ('ln -s %s %s' % (src, dest), tmp)
        inner_tmp = os.path.join(tmp, vdir)
        for dest, src in inner_links.items():
            shell.call ('ln -s %s %s' % (src, dest), inner_tmp)

        # Copy the framework library to Versions/$VERSION/$ARCH/Framework
        if self.package.osx_framework_library is not None \
                and os.path.exists(os.path.join(self.config.prefix, link)):
            shell.call ('mkdir -p %s' % vdir, tmp)
            shutil.copy(os.path.join(self.config.prefix, link),
                        os.path.join(tmp, vdir, name))
        return tmp


class ApplicationBundlePackager(object):
    '''
    Creates a package with the basic structure of an Application bundle.
    '''

    def __init__(self, package):
        self.package = package

    def create_bundle(self, tmp=None):
        '''
        Creates the Application bundle structure

        Contents/MacOS/MainExectuable -> Contents/Home/bin/main-executable
        Contents/Info.plist
        '''
        tmp = tmp or tempfile.mkdtemp()

        contents = os.path.join(tmp, 'Contents')
        macos = os.path.join(contents, 'MacOS')
        resources = os.path.join(contents, 'Resources')
        for p in [contents, macos, resources]:
            if not os.path.exists(p):
                os.makedirs(p)

        # Create Contents/Info.plist
        # Use the template if provided in the package
        plist_tpl = None
        if os.path.exists(self.package.resources_info_plist):
            plist_tpl = open(self.package.resources_info_plist).read()
        framework_plist = ApplicationPlist(self.package.app_name,
            self.package.org, self.package.version, self.package.shortdesc,
            self.package.config.min_osx_sdk_version,
            os.path.basename(self.package.resources_icon_icns),
            plist_tpl)
        framework_plist.save(os.path.join(contents, 'Info.plist'))

        # Copy app icon to Resources
        shutil.copy(self.package.resources_icon_icns, resources)

        # Link or create a wrapper for the executables in Contents/MacOS
        for name, path, use_wrapper, wrapper in self.package.get_commands():
            filename = os.path.join(macos, name)
            if use_wrapper:
                wrapper = self.package.get_wrapper(path, wrapper)
                if not wrapper:
                    continue
                with open(filename, 'w') as f:
                    f.write(wrapper)
                shell.call('chmod +x %s' % filename)
            else:
                # FIXME: We need to copy the binary instead of linking, because
                # beeing a different path, @executable_path will be different
                # and it we will need to set a different relative path with
                # install_name_tool
                shutil.copy(os.path.join(contents, 'Home', path), filename)
        return tmp
