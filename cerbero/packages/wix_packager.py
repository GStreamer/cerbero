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

from cerbero.errors import EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.package import Package
from cerbero.utils import messages as m
from cerbero.utils import shell, to_winepath
from cerbero.packages.wix import MergeModule, MSI, WixConfig
from cerbero.config import Platform


class MergeModulePackager(PackagerBase):

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self._with_wine = config.platform != Platform.WINDOWS
        self.wix_prefix = config.wix_prefix

    def pack(self, output_dir, devel=False, force=False):
        output_dir = os.path.realpath(output_dir)

        paths = []

        # create runtime package
        p = self.create_merge_module(output_dir, PackageType.RUNTIME, force)
        paths.append(p)

        if devel:
            p = self.create_merge_module(output_dir, PackageType.DEVEL, force)
            paths.append(p)

        return paths

    def create_merge_module(self, output_dir, package_type, force):
        self.package.set_mode(package_type)
        files_list = self.files_list(package_type, force)
        mergemodule = MergeModule(self.config, files_list, self.package)
        sources = os.path.join(output_dir, "%s.wsx" % self.package.name)
        mergemodule.write(sources)

        wixobj = os.path.join(output_dir, "%s.wixobj" % self.package.name)

        if self._with_wine:
            wixobj = to_winepath(wixobj)
            sources = to_winepath(sources)

        candle = Candle(self.wix_prefix, self._with_wine)
        candle.compile(sources, output_dir)
        light = Light(self.wix_prefix, self._with_wine)
        return light.compile([wixobj], self.package.name, output_dir, True)


class MSIPackager(PackagerBase):

    UI_EXT = '-ext WixUIExtension'
    UI_SOURCES = 'wix/ui.wxs'

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self._with_wine = config.platform != Platform.WINDOWS
        self.wix_prefix = config.wix_prefix

    def pack(self, output_dir, devel=False, force=False):
        output_dir = os.path.realpath(output_dir)

        paths = []

        # create runtime package
        p = self._create_msi_installer(output_dir, PackageType.RUNTIME, force)
        paths.append(p)

        if devel:
            p = self._create_msi_installer(output_dir, PackageType.DEVEL, force)
            paths.append(p)

        return paths

    def _create_msi_installer(self, output_dir, package_type, force=False):
        self.package.set_mode(package_type)
        output_dir = os.path.realpath(output_dir)
        self.packagedeps = self.store.get_package_deps(self.package.name)
        self.output_dir = output_dir
        self.force = force
        self._create_merge_modules(package_type)
        config_path = self._create_config()
        self._create_msi(config_path)

    def _create_merge_modules(self, package_type):
        packagedeps = []
        for package in self.packagedeps:
            package.set_mode(package_type)
            m.action("Creating Merge Module for %s" % package)
            packager = MergeModulePackager(self.config, package, self.store)
            try:
                packager.create_merge_module(self.output_dir,
                        package_type, self.force)
                packagedeps.append(package)
            except EmptyPackageError:
                m.warning("Package %s is empty" % package)
        self.packagedeps = packagedeps

    def _create_config(self):
        config = WixConfig(self.config, self.package)
        config_path = config.write(self.output_dir)
        candle = Candle(self.wix_prefix, self._with_wine)
        ui_path = os.path.join(self.config.data_dir, self.UI_SOURCES)
        if self._with_wine:
            ui_path = to_winepath(ui_path)
        candle.compile(ui_path, self.output_dir)
        return config_path

    def _create_msi(self, config_path):
        sources = os.path.join(self.output_dir, "%s.wsx" % self.package.name)
        msi = MSI(self.config, self.package, self.packagedeps, config_path,
                  self.store)
        msi.write(sources)


        wixobjs = [os.path.join(self.output_dir, "%s.wixobj" % self.package.name)]
        wixobjs.append(os.path.join(self.output_dir, "ui.wixobj"))

        if self._with_wine:
            wixobjs = [to_winepath(x) for x in wixobjs]
            sources = to_winepath(sources)

        candle = Candle(self.wix_prefix, self._with_wine)
        candle.compile(sources, self.output_dir)
        light = Light(self.wix_prefix, self._with_wine, self.UI_EXT)
        return light.compile(wixobjs, self.package.name, self.output_dir)


class Packager(object):

    def __new__(klass, config, package, store):
        if isinstance(package, Package):
            return MergeModulePackager(config, package, store)
        else:
            return MSIPackager(config, package, store)

class Candle(object):
    ''' Compile WiX objects with candle '''

    cmd = '%(wine)s %(q)s%(prefix)s/candle.exe%(q)s %(source)s'

    def __init__(self, wix_prefix, with_wine):
        self.options = {}
        self.options['prefix'] = wix_prefix
        if with_wine:
            self.options['wine'] = 'wine'
            self.options['q'] = '"'
        else:
            self.options['wine'] = ''
            self.options['q'] = ''

    def compile(self, source, output_dir):
        self.options['source'] = source
        shell.call(self.cmd % self.options, output_dir)
        return os.path.join(output_dir, source, '.msm')


class Light(object):
    ''' Compile WiX objects with light'''

    cmd = '%(wine)s %(q)s%(prefix)s/light.exe%(q)s %(objects)s -o '\
          '%(msi)s.%(ext)s -sval %(extra)s'

    def __init__(self, wix_prefix, with_wine, extra=''):
        self.options = {}
        self.options['prefix'] = wix_prefix
        self.options['extra'] = extra
        if with_wine:
            self.options['wine'] = 'wine'
            self.options['q'] = '"'
        else:
            self.options['wine'] = ''
            self.options['q'] = ''

    def compile(self, objects, msi_file, output_dir, merge_module=False):
        self.options['objects'] = ' '.join(objects)
        self.options['msi'] = msi_file
        if merge_module:
            self.options['ext'] = 'msm'
        else:
            self.options['ext'] = 'msi'
        shell.call(self.cmd % self.options, output_dir)
        return os.path.join(output_dir, '%(msi)s.%(ext)s' % self.options)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.WINDOWS, Packager)

