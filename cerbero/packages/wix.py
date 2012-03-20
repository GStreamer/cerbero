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
import uuid
try:
  from lxml import etree
except ImportError:
    import xml.etree.cElementTree as etree

from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import shell
from cerbero.errors import PackageNotFoundError
from cerbero.config import Platform


class WixBase(object):

    def __init__(self, config, package):
        self.platform = config.platform
        self.target_platform = config.target_platform
        self.config = config
        self._with_wine = self.platform != Platform.WINDOWS
        self.prefix = config.prefix
        self.wix_prefix = config.wix_prefix
        self.package = package
        self.filled = False

    def fill(self):
        if self.filled:
            return
        self._fill()
        self.filled = True

    def render_xml(self):
        self.fill()
        return etree.tostring(self.root, pretty_print=True)

    def _set(self, node, **kwargs):
        for key in sorted(kwargs.keys()):
            value = kwargs[key]
            if value is None or value is "":
                return
            node.set(key, value)

    def _add_root(self):
        self.root = etree.Element("Wix")
        self._set(self.root, xmlns='http://schemas.microsoft.com/wix/2006/wi')

    def _to_wine_path(self, path):
        path = path.replace('/', '\\\\')
        # wine maps the filesystem root '/' to 'z:\'
        path = 'z:\\%s' % path
        return path

    def _format_id(self, path, replace_dots=False):
        ret = path.replace('/', '_').replace('-', '_')
        if replace_dots:
            ret = ret.replace('.', '')
        return ret

    def _get_uuid(self):
        return "%s" % uuid.uuid1()


class MergeModule(WixBase):
    '''
    Creates WiX merge modules from cerbero packages

    @ivar package: package with the info to build the merge package
    @type pacakge: L{cerbero.packages.package.Package}
    '''

    def __init__(self, config, package):
        WixBase.__init__(self, config, package)
        self.files_list = package.get_files_list()
        self._dirnodes = {}

    def build(self, output_dir):
        output_dir = os.path.realpath(output_dir)
        sources = os.path.join(output_dir, "%s.wsx" % self.package.name)
        with open(sources, 'wb') as f:
            f.write(self.render_xml())

        wixobj = os.path.join(output_dir, "%s.wixobj" % self.package.name)

        if self._with_wine:
            wixobj = self._to_wine_path(wixobj)
            sources = self._to_wine_path(sources)

        candle = Candle(self.wix_prefix, self._with_wine)
        candle.compile(sources, output_dir)
        light = Light(self.wix_prefix, self._with_wine)
        light.compile([wixobj], self.package.name, output_dir, True)

    def _fill(self):
        self._add_root()
        self._add_module()
        self._add_package()
        self._add_root_dir()
        self._add_files()

    def _add_module(self):
        self.module = etree.SubElement(self.root, "Module")
        self._set(self.module, Id=self._format_id(self.package.name),
                               Version=self.package.version,
                               Language= '1033')

    def _add_package(self):
        self.pkg = etree.SubElement(self.module, "Package")
        self._set(self.pkg, Id=self.package.uuid or self._get_uuid(),
                            Description=self.package.shortdesc,
                            Comments=self.package.longdesc,
                            Manufacturer=self.package.vendor)

    def _add_root_dir(self):
        self.rdir = etree.SubElement(self.module, "Directory")
        self._set(self.rdir, Id='TARGETDIR', Name='SourceDir')
        self._dirnodes[''] = self.rdir

    def _add_files(self):
        for f in self.files_list:
            self._add_file(f)

    def _add_directory(self, dirpath):
        if dirpath in self._dirnodes:
            return
        parentpath = os.path.split(dirpath)[0]
        if parentpath == []:
            parentpath = ['']

        if parentpath not in self._dirnodes:
            self._add_directory(parentpath)

        parent = self._dirnodes[parentpath]
        dirnode = etree.SubElement(parent, "Directory")
        self._set(dirnode, Id=self._format_id(dirpath),
                           Name=self._format_id(dirpath))
        self._dirnodes[dirpath] = dirnode

    def _add_file(self, filepath):
        dirpath, filename = os.path.split(filepath)
        self._add_directory(dirpath)
        dirnode = self._dirnodes[dirpath]
        component = etree.SubElement(dirnode, 'Component')
        self._set(component, Id=self._format_id(filepath),
                             Guid=self._get_uuid())
        filenode = etree.SubElement(component, 'File')
        filepath = os.path.join(self.prefix, filepath)
        if self._with_wine:
            wfilepath = self._to_wine_path(filepath)
        self._set(filenode, Id=self._format_id(filepath, True), Name=filename,
                            Source=wfilepath)


class Installer(WixBase):
    '''Creates an installer package from a
       L{cerbero.packages.package.MetaPackage}

    @ivar package: meta package used to create the installer package
    @type package: L{cerbero.packages.package.MetaPackage}
    '''

    def __init__(self, config, package):
        WixBase.__init__(self, config, package)
        self.store = PackagesStore(config)

    def build(self, output_dir):
        output_dir = os.path.realpath(output_dir)
        mergemodules = []
        for p in self.package.packages:
            package = self.store.get_package(p)
            if package is None:
                raise PackageNotFoundError(p)
            mergemodule = MergeModule(self.config, package)
            mergemodule.build(output_dir)
            mergemodules.append('%s.msm' % package.name)

        sources = os.path.join(output_dir, "%s.wsx" % self.package.name)
        with open(sources, 'wb') as f:
            f.write(self.render_xml())

        wixobjs = [os.path.join(output_dir, "%s.wixobj" % self.package.name)]
        wixobjs.append(os.path.join(output_dir, "ui.wixobj"))

        if self._with_wine:
            wixobjs = [self._to_wine_path(x) for x in wixobjs]
            sources = self._to_wine_path(sources)

        candle = Candle(self.wix_prefix, self._with_wine)
        candle.compile(sources, output_dir)
        light = Light(self.wix_prefix, self._with_wine)
        light.compile(wixobjs, self.package.name, output_dir)

    def _fill(self):
        self._add_root()
        self._add_product()
        self._add_package()
        self._add_install_dir()
        self._add_ui_props()
        self._add_media()
        self._add_merge_modules()

    def _add_product(self):
        self.product = etree.SubElement(self.root, "Product")
        self._set(self.product, Id=self.package.uuid or self._get_uuid(),
                                Version=self.package.version,
                                UpgradeCode=self.package.uuid,
                                Language='1033', Name=self.package.name,
                                Manufacturer=self.package.vendor)

    def _add_package(self):
        self.pkg = etree.SubElement(self.product, "Package")
        self._set(self.pkg, Description=self.package.shortdesc,
                            Comments=self.package.longdesc,
                            Manufacturer=self.package.vendor)

    def _add_dir(self, parent, dir_id, name):
        tdir = etree.SubElement(parent, "Directory")
        self._set(tdir, Id=dir_id, Name=name)
        return tdir

    def _add_install_dir(self):
        tdir = self._add_dir(self.product, 'TARGETDIR', 'SourceDir')
        pfdir = self._add_dir(tdir, 'ProgramFilesFolder', 'PFiles')
        install_dir = self.package.install_dir[self.target_platform]
        sdkdir = self._add_dir(pfdir, self._format_id(install_dir),
                               install_dir)
        self.installdir = self._add_dir(sdkdir, 'INSTALLDIR', '.')

    def _add_merge_modules(self):
        self.main_feature = etree.SubElement(self.product, "Feature")
        self._set(self.main_feature, Id=self._format_id(self.package.name),
                  Title=self.package.title, Level='1', Display="expand",
                  AllowAdvertise="no", ConfigurableDirectory="INSTALLDIR")

        for p in self.package.packages:
            package = self.store.get_package(p)
            if not package:
                raise PackageNotFoundError(p)
            self._add_merge_module(package)

    def _add_ui_props(self):
        prop = etree.SubElement(self.product, 'Property')
        self._set(prop, Id='WIXUI_INSTALLDIR', Value='INSTALLDIR')

    def _add_media(self):
        prop = etree.SubElement(self.product, 'Media')
        self._set(prop, Id='1', Cabinet='product.cab', EmbedCab='yes')

    def _add_merge_module(self, package):
        mergemodule = etree.SubElement(self.installdir, 'Merge')
        self._set(mergemodule, Id=self._format_id(package.name),
                  Language='1033', SourceFile='%s.msm' % package.name,
                  DiskId='1')
        mergeref = etree.SubElement(self.main_feature, "MergeRef")
        self._set(mergeref, Id=self._format_id(package.name))


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


class Light(object):
    ''' Compile WiX objects with light'''

    cmd = '%(wine)s %(q)s%(prefix)s/light.exe%(q)s %(objects)s -o '\
          '%(msi)s.%(ext)s -sval'

    def __init__(self, wix_prefix, with_wine):
        self.options = {}
        self.options['prefix'] = wix_prefix
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
