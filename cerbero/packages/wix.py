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
import shutil

from cerbero.utils import etree, to_winepath, shell, xmlwrite
from cerbero.errors import FatalError
from cerbero.config import Platform, Architecture
from cerbero.packages import PackageType
from cerbero.packages.package import Package, SDKPackage, App, InstallerPackage

WIX_SCHEMA = 'http://wixtoolset.org/schemas/v4/wxs'
WIX_UI_SCHEMA = 'http://wixtoolset.org/schemas/v4/wxs/ui'
WIX_VS_SCHEMA = 'http://wixtoolset.org/schemas/v4/wxs/vs'

NS = {'': WIX_SCHEMA, 'ui': WIX_UI_SCHEMA, 'vs': WIX_VS_SCHEMA}

for k, v in NS.items():
    etree.register_namespace(k, v)


class VSTemplatePackage(Package):
    """
    A Package for Visual Studio templates

    @cvar: vs_template_name: name of the template
    @type vs_template_name: string
    @cvar vs_template_dir: directory of the template files
    @type vs_template_dir: string
    @cvar: vs_wizard_dir: directory of the wizard files
    @type vs_wizard_dir: string
    """

    vs_template_dir = None
    vs_wizard_dir = None
    vs_template_name = None

    def __init__(self, config, store, cookbook):
        Package.__init__(self, config, store, cookbook)

    def devel_files_list(self):
        files = []
        for f in [self.vs_template_dir, self.vs_wizard_dir]:
            files += shell.ls_dir(os.path.join(self.config.prefix, f), self.config.prefix)
        return files


class WixBase:
    def __init__(self, config, package):
        self.config = config
        self.package = package
        self.platform = config.platform
        self.target_platform = config.target_platform
        self._with_wine = self.platform != Platform.WINDOWS
        self.prefix = config.prefix
        self.filled = False
        self.id_count = 0
        self.ids = {}

    def fill(self):
        if self.filled:
            return
        self._fill()
        self.filled = True

    def write(self, filepath):
        self.fill()
        tree = etree.ElementTree(self.root)
        xmlwrite(tree, filepath)

    def _format_level(self, selected):
        return selected and '1' or '4'

    def _format_absent(self, required):
        return required and 'yes' or 'no'

    def _add_root(self):
        self.root = etree.Element('Wix', xmlns=WIX_SCHEMA)

    def _format_id(self, string, replace_dots=False):
        ret = string
        ret = ret.replace('_', '__')
        for r in ['/', '-', ' ', '@', '+']:
            ret = ret.replace(r, '_')
        if replace_dots:
            ret = ret.replace('.', '')
        # For directories starting with a number
        ret = '_' + ret

        if len(ret) > 38:
            return ret[0:37]

        return ret

    def _make_unique_id(self, id):
        # Wix Id length is limited to 72 characters which can be short
        # for some files paths. To guaranty Id unicity we add a number
        # at the end of duplicated Id, so we're gonna limit our max length
        # to 68 characters to reserve until 3 digits for that purpose.
        id = id[:68]
        if id not in self.ids:
            self.ids[id] = 0
        else:
            self.ids[id] += 1
        if self.ids[id] != 0:
            id = '%s_%s' % (id, self.ids[id])
        return id

    def _format_path_id(self, path, replace_dots=False):
        ret = self._format_id(os.path.split(path)[1], replace_dots)
        ret = ret.lower()
        ret = self._make_unique_id(ret)
        return ret

    def _format_dir_id(self, string, path, replace_dots=False):
        ret = self._format_id(string, replace_dots) + '_' + self._format_path_id(path, replace_dots)
        ret = self._make_unique_id(ret)
        return ret

    def _format_group_id(self, string, replace_dots=False):
        return self._format_id(string, replace_dots) + '_group'

    def _get_uuid(self):
        return '%s' % uuid.uuid1()

    def _format_version(self, version):
        # The heuristics to generate a valid version can get
        # very complicated, so we leave it to the user
        url = 'https://docs.microsoft.com/en-us/windows/desktop/Msi/productversion'
        versions = (version.split('.', 3) + ['0', '0', '0'])[:3]
        for idx, val in enumerate(versions):
            i = int(val)
            if idx in [0, 1] and i > 255:
                raise FatalError(
                    'Invalid version string, major and minor' 'must have a maximum value of 255.\nSee: {}'.format(url)
                )
            elif idx in [2] and i > 65535:
                raise FatalError(
                    'Invalid version string, build ' 'must have a maximum value of 65535.\nSee: {}'.format(url)
                )
        return '.'.join(versions)


class MergeModule(WixBase):
    """
    Creates WiX merge modules from cerbero packages

    @ivar package: package with the info to build the merge package
    @type pacakge: L{cerbero.packages.package.Package}
    """

    def __init__(self, config, files_list, package):
        WixBase.__init__(self, config, package)
        self.files_list = files_list
        self._dirnodes = {}

    def _fill(self):
        self._add_root()
        self._add_module()
        self._add_files()

    def _add_module(self):
        self.module = etree.SubElement(
            self.root,
            'Module',
            Id=self._format_id(self.package.name),
            Version=self._format_version(self.package.version),
            Guid=self.package.uuid or self._get_uuid(),
            Language='1033',
        )
        self.summary = etree.SubElement(
            self.module,
            'SummaryInformation',
            Description=self.package.shortdesc,
            Manufacturer=self.package.vendor,
        )
        self._dirnodes[''] = self.module

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
        dirnode = etree.SubElement(
            parent, 'Directory', Id=self._format_path_id(dirpath), Name=os.path.split(dirpath)[1]
        )
        self._dirnodes[dirpath] = dirnode

    def _add_file(self, filepath):
        dirpath, filename = os.path.split(filepath)
        self._add_directory(dirpath)
        dirnode = self._dirnodes[dirpath]

        component = etree.SubElement(dirnode, 'Component', Id=self._format_path_id(filepath), Guid=self._get_uuid())

        filepath = os.path.join(self.prefix, filepath)
        p_id = self._format_path_id(filepath, True)
        if self._with_wine:
            filepath = to_winepath(filepath)
        etree.SubElement(component, 'File', Id=p_id, Name=filename, Source=filepath)


class Fragment(WixBase):
    """
    Creates WiX fragment from cerbero packages

    @ivar package: package with the info to build the merge package
    @type pacakge: L{cerbero.packages.package.Package}
    """

    def __init__(self, config, files_list, package):
        WixBase.__init__(self, config, package)
        self.files_list = files_list
        self._dirnodes = {}
        self._dirids = {}

    def _fill(self):
        self._add_root()
        self._add_fragment()
        self._add_component_group()
        self._add_root_dir()
        self._add_files()

    def _add_fragment(self):
        self.fragment = etree.SubElement(self.root, 'Fragment')

    def _add_component_group(self):
        self.component_group = etree.SubElement(
            self.fragment, 'ComponentGroup', Id=self._format_group_id(self.package.name)
        )

    def _add_root_dir(self):
        self.rdir = etree.SubElement(self.fragment, 'DirectoryRef', Id='SDKROOTDIR')
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
        dirid = self._format_dir_id(self.package.name, dirpath)
        dirnode = etree.SubElement(parent, 'Directory', Id=dirid, Name=os.path.split(dirpath)[1])
        self._dirnodes[dirpath] = dirnode
        self._dirids[dirpath] = dirid

    def _add_file(self, filepath):
        dirpath, filename = os.path.split(filepath)
        self._add_directory(dirpath)
        dirid = self._dirids[dirpath]

        component = etree.SubElement(
            self.component_group,
            'Component',
            Id=self._format_dir_id(self.package.name, filepath),
            Guid=self._get_uuid(),
            Directory=dirid,
        )
        filepath = os.path.join(self.prefix, filepath)
        p_id = self._format_dir_id(self.package.name, filepath, True)
        if self._with_wine:
            filepath = to_winepath(filepath)
        etree.SubElement(component, 'File', Id=p_id, Name=filename, Source=filepath)


class VSMergeModule(MergeModule):
    """
    Creates a Merge Module for Visual Studio templates

    @ivar package: package with the info to build the merge package
    @type pacakge: L{cerbero.packages.package.Package}
    """

    def __init__(self, config, files_list, package):
        MergeModule.__init__(self, config, files_list, package)
        self.year = self.package.year

    def _add_module(self):
        MergeModule._add_module(self)
        self._add_vs_templates()

    def _add_vs_templates(self):
        self.root.attrib['xmlns:vs'] = WIX_VS_SCHEMA

        etree.SubElement(self.module, 'CustomActionRef', Id=f'VS{self.year}InstallVSTemplates')
        etree.SubElement(self.module, 'PropertyRef', Id=f'VS{self.year}_IDE_DIR')
        tpl_base = etree.SubElement(self.module, 'Directory', Id=f'VS{self.year}_IDE_DIR')
        tpl_base = etree.SubElement(tpl_base, 'Directory', Name='VC')
        # In 2015 onwards "wizard" files go into VCProjects
        self._wizard_dir = etree.SubElement(tpl_base, 'Directory', Name='VCProjects')
        self._wizard_dir = etree.SubElement(self._wizard_dir, 'Directory', Name=self.package.vs_template_name)
        self._dirnodes[self.package.vs_wizard_dir] = self._wizard_dir
        # In 2015 onwards "template" files go into VCWizards
        # **NOTE**: the end path is <VS IDE root>/<RELATIVE_PATH>/<wizard name>
        self._tpl_dir = etree.SubElement(tpl_base, 'Directory', Name='VCWizards')
        self._tpl_dir = etree.SubElement(self._tpl_dir, 'Directory', Name=self.package.vs_template_name)
        self._dirnodes[self.package.vs_template_dir] = self._tpl_dir


class VSFragment(Fragment):
    """
    Creates a Merge Module for Visual Studio templates

    @ivar package: package with the info to build the merge package
    @type pacakge: L{cerbero.packages.package.Package}

    FIXME (remove this special casing): https://github.com/wixtoolset/issues/issues/8558
    """

    def __init__(self, config, files_list, package):
        Fragment.__init__(self, config, files_list, package)
        self.year = self.package.year

    def _fill(self):
        self._add_root()
        self._add_fragment()
        self._add_component_group()
        self._add_vs_templates()
        self._add_files()

    def _add_vs_templates(self):
        self.root.attrib['xmlns:vs'] = WIX_VS_SCHEMA

        etree.SubElement(self.fragment, 'CustomActionRef', Id=f'VS{self.year}InstallVSTemplates')
        etree.SubElement(self.fragment, 'PropertyRef', Id=f'VS{self.year}_IDE_DIR')
        tpl_base = etree.SubElement(self.fragment, 'Directory', Id=f'VS{self.year}_IDE_DIR')
        tpl_base = etree.SubElement(tpl_base, 'Directory', Name='VC')
        dirpath = self.package.vs_template_name
        dirid = self._format_dir_id(self.package.name, 'VCProjects' + dirpath)
        # In 2015 onwards "wizard" files go into VCProjects
        self._wizard_dir = etree.SubElement(tpl_base, 'Directory', Name='VCProjects')
        self._wizard_dir = etree.SubElement(self._wizard_dir, 'Directory', Id=dirid, Name=dirpath)
        self._dirnodes[self.package.vs_wizard_dir] = self._wizard_dir
        self._dirids[self.package.vs_wizard_dir] = dirid
        # In 2015 onwards "template" files go into VCWizards
        # **NOTE**: the end path is <VS IDE root>/<RELATIVE_PATH>/<wizard name>
        dirid = self._format_dir_id(self.package.name, 'VCWizards' + dirpath)
        self._tpl_dir = etree.SubElement(tpl_base, 'Directory', Name='VCWizards')
        self._tpl_dir = etree.SubElement(self._tpl_dir, 'Directory', Id=dirid, Name=self.package.vs_template_name)
        # In 2015 onwards they all go into the same folder
        self._dirnodes[self.package.vs_template_dir] = self._tpl_dir
        self._dirids[self.package.vs_template_dir] = dirid


class WixConfig(WixBase):
    wix_config = 'wix/Config.wxi'
    ui_path = 'wix/wixui_Mondo_GStreamer.wxi'

    def __init__(self, config, package):
        self.config_path = os.path.join(config.data_dir, self.wix_config)
        self.ui_path = os.path.join(config.data_dir, self.ui_path)
        self.arch = config.target_arch
        self.abi_desc = ' '.join(config._get_toolchain_target_platform_arch(readable=True))
        self.package = package
        if isinstance(self.package, App):
            self.ui_type = 'WixUI_InstallDir'
        else:
            self.ui_type = 'WixUI_Mondo_GStreamer'
        # Wine doesn't support other than mszip
        if config.cross_compiling():
            self.compression = 'mszip'
        else:
            self.compression = 'high'

    def write(self, output_dir):
        config_out_path = os.path.join(output_dir, os.path.basename(self.wix_config) + self.package.package_mode)
        shutil.copy(self.config_path, config_out_path)
        replacements = {
            '@ProductID@': '*',
            '@UpgradeCode@': self.package.get_wix_upgrade_code(),
            '@Language@': '1033',
            '@Manufacturer@': self.package.vendor,
            '@Version@': self._format_version(self.package.version),
            '@PackageComments@': self.package.longdesc,
            '@Description@': f'{self.package.shortdesc} ({self.abi_desc})',
            '@ProjectURL@': self.package.url,
            '@ProductName@': f'{self.package.shortdesc} ({self.abi_desc})',
            '@ProgramFilesFolder@': self._program_folder(),
            '@Platform@': self._platform(),
            '@UIType@': self.ui_type,
            '@Compression@': self.compression,
        }
        shell.replace(config_out_path, replacements)
        if self.ui_type == 'WixUI_Mondo_GStreamer':
            ui_out_path = os.path.join(output_dir, os.path.basename(self.ui_path))
            shutil.copy(self.ui_path, ui_out_path)
            return (config_out_path, ui_out_path)
        else:
            return (config_out_path, None)

    def _program_folder(self):
        if self.arch == Architecture.X86:
            return 'ProgramFilesFolder'
        return 'ProgramFiles64Folder'

    def _platform(self):
        if self.arch == Architecture.X86_64:
            return 'x64'
        return 'x86'


class MSI(WixBase):
    """Creates an installer package from a
       L{cerbero.packages.package.MetaPackage}

    @ivar package: meta package used to create the installer package
    @type package: L{cerbero.packages.package.MetaPackage}
    """

    wix_sources = 'wix/installer.wxs'
    REG_ROOT = 'HKLM'
    BANNER_BMP = 'banner.bmp'
    DIALOG_BMP = 'dialog.bmp'
    LICENSE_RTF = 'license.rtf'
    ICON = 'icon.ico'

    def __init__(self, config, package, packages_deps, wix_config, store):
        WixBase.__init__(self, config, package)
        self.packages_deps = packages_deps
        self.store = store
        self.wix_config = wix_config
        self._parse_sources()
        self.product = self.root.find('Package', namespaces=NS)
        if not self.product:
            raise RuntimeError
        self._add_include()
        self._add_compression(not config.cross_compiling())
        self._customize_ui()
        self._add_vs_properties()

    def _parse_sources(self):
        sources_path = self.package.resources_wix_installer or os.path.join(self.config.data_dir, self.wix_sources)
        with open(sources_path, 'r', encoding='utf-8') as f:
            self.root = etree.fromstring(f.read())

    def _add_include(self):
        if self._with_wine:
            self.wix_config = to_winepath(self.wix_config)
        inc = etree.PI('include %s' % self.wix_config)
        self.root.insert(0, inc)

    def _add_compression(self, shard):
        mediatemplate = etree.SubElement(
            self.product,
            'MediaTemplate',
            EmbedCab='yes',
            CompressionLevel='$(var.Compression)',
        )
        if shard:
            # On Wine this yields corrupted sharded cabinets.
            mediatemplate.set('MaximumUncompressedMediaSize', '50')

    def _fill(self):
        self._add_install_dir()
        if isinstance(self.package, App):
            self._add_application_merge_module()
        else:
            self._add_merge_modules()
        if isinstance(self.package, SDKPackage):
            if self.package.package_mode == PackageType.RUNTIME:
                self._add_registry_install_dir()
                self._add_sdk_root_env_variable()
        if isinstance(self.package, App):
            self._add_start_menu_shortcuts()
        self._add_get_install_dir_from_registry()

    def _add_application_merge_module(self):
        self.main_feature = etree.SubElement(
            self.product,
            'Feature',
            Id=self._format_id(self.package.name + '_app'),
            Title=self.package.title,
            Level='1',
            Display='expand',
            AllowAdvertise='no',
            ConfigurableDirectory='INSTALLDIR',
        )
        if self.package.wix_use_fragment:
            etree.SubElement(self.main_feature, 'ComponentGroupRef', Id=self._format_group_id(self.package.name))
        else:
            self._add_merge_module(self.package, True, True, [])
            etree.SubElement(
                self.installdir,
                'Merge',
                Id=self._package_id(self.package.name),
                Language='1033',
                SourceFile=self.packages_deps[self.package],
                DiskId='1',
            )

    def _add_merge_modules(self):
        self.main_feature = etree.SubElement(
            self.product,
            'Feature',
            Id=self._format_id(self.package.name),
            Title=self.package.title,
            Level='1',
            Display='expand',
            AllowAdvertise='no',
            ConfigurableDirectory='INSTALLDIR',
        )

        packages = [(self.store.get_package(x[0]), x[1], x[2]) for x in self.package.packages]

        # Remove empty packages
        packages = [x for x in packages if x[0] in list(self.packages_deps.keys())]
        if len(packages) == 0:
            raise FatalError('All packages are empty: %s' % [x[0] for x in self.package.packages])

        # Fill the list of required packages, which are the ones installed by
        # a package that is always installed
        req = [x[0] for x in packages if x[1] is True]
        required_packages = req[:]
        for p in req:
            required_packages.extend(self.store.get_package_deps(p, True))

        if not self.package.wix_use_fragment:
            for package, required, selected in packages:
                if package in self.packages_deps:
                    self._add_merge_module(package, required, selected, required_packages)

        # Add a merge module ref for all the packages or use ComponentGroupRef when using
        # wix_use_fragment
        for package, path in self.packages_deps.items():
            if self.package.wix_use_fragment:
                etree.SubElement(self.main_feature, 'ComponentGroupRef', Id=self._format_group_id(package.name))
            # FIXME: https://github.com/wixtoolset/issues/issues/8558
            elif isinstance(package, VSTemplatePackage):
                etree.SubElement(self.main_feature, 'ComponentGroupRef', Id=self._format_group_id(package.name))
            else:
                etree.SubElement(
                    self.installdir,
                    'Merge',
                    Id=self._package_id(package.name),
                    Language='1033',
                    SourceFile=path,
                    DiskId='1',
                )

    def _add_dir(self, parent, dir_id, name):
        tdir = etree.SubElement(parent, 'Directory', Id=dir_id, Name=name)
        return tdir

    def _add_install_dir(self):
        self.target_dir = etree.SubElement(self.product, 'StandardDirectory', Id='ProgramFiles6432Folder')
        if isinstance(self.package, App):
            installdir = self.target_dir
            self.installdir = self._add_dir(installdir, 'INSTALLDIR', '$(var.ProductName)')
            self.bindir = self._add_dir(self.installdir, 'INSTALLBINDIR', 'bin')
        else:
            installdir = self._add_dir(self.target_dir, 'INSTALLDIR', self.package.get_install_dir())
            versiondir = self._add_dir(installdir, 'Version', self.package.sdk_version)
            # archdir has to be toolchain-specific: mingw_x86_64, msvc-debug_arm64, etc
            platform_arch = '_'.join(self.config._get_toolchain_target_platform_arch())
            archdir = self._add_dir(versiondir, 'Architecture', platform_arch)
            self.installdir = self._add_dir(archdir, 'SDKROOTDIR', '.')

    def _package_id(self, package_name):
        return self._format_id(package_name)

    def _package_var(self):
        package_type = self.package.package_mode
        self.package.set_mode(PackageType.RUNTIME)
        name = self.package.shortdesc
        self.package.set_mode(package_type)
        return name

    def _registry_key(self, name):
        return 'Software\\%s\\%s' % (name, self.config.target_arch)

    def _customize_ui(self):
        # Banner Dialog and License
        for path, var in [
            (self.BANNER_BMP, 'BannerBmp'),
            (self.DIALOG_BMP, 'DialogBmp'),
            (self.LICENSE_RTF, 'LicenseRtf'),
        ]:
            path = self.package.relative_path(path)
            if os.path.exists(path):
                if self._with_wine:
                    path = to_winepath(path)
                etree.SubElement(self.product, 'WixVariable', Id='WixUI%s' % var, Value=path)
        # Icon
        path = self.package.relative_path(self.ICON)
        if os.path.exists(path):
            if self._with_wine:
                path = to_winepath(path)
            etree.SubElement(self.product, 'Icon', Id='MainIcon', SourceFile=path)

    def _add_sdk_root_env_variable(self):
        envcomponent = etree.SubElement(self.installdir, 'Component', Id='EnvironmentVariables', Guid=self._get_uuid())
        # archdir has to be toolchain-specific: mingw_x86_64, msvc-debug_arm64, etc
        platform_arch = '_'.join(self.config._get_toolchain_target_platform_arch())
        root_env_var = self.package.get_root_env_var(platform_arch)
        etree.SubElement(
            envcomponent,
            'Environment',
            Id='SdkRootEnv',
            Action='set',
            Part='all',
            Name=root_env_var,
            System='yes',
            Permanent='no',
            Value='[SDKROOTDIR]',
        )
        etree.SubElement(self.main_feature, 'ComponentRef', Id='EnvironmentVariables')

    def _add_registry_install_dir(self):
        # Get the package name. Both devel and runtime will share the same
        # installation folder
        name = self._package_var().replace(' ', '')

        # Add INSTALLDIR in the registry only when missing
        regcomponent = etree.SubElement(
            self.installdir,
            'Component',
            Id='RegistryInstallDir',
            Guid=self._get_uuid(),
            Condition='NOT GSTINSTALLDIR',
        )
        regkey = etree.SubElement(
            regcomponent,
            'RegistryKey',
            Id='RegistryInstallDirRoot',
            ForceCreateOnInstall='yes',
            ForceDeleteOnUninstall='yes',
            Key=self._registry_key(name),
            Root=self.REG_ROOT,
        )
        etree.SubElement(
            regkey,
            'RegistryValue',
            Id='RegistryInstallDirValue',
            Type='string',
            Name='InstallDir',
            Value='[INSTALLDIR]',
        )
        etree.SubElement(
            regkey,
            'RegistryValue',
            Id='RegistryVersionValue',
            Type='string',
            Name='Version',
            Value=self.package.version,
        )
        etree.SubElement(
            regkey,
            'RegistryValue',
            Id='RegistrySDKVersionValue',
            Type='string',
            Name='SdkVersion',
            Value=self.package.sdk_version,
        )
        etree.SubElement(self.main_feature, 'ComponentRef', Id='RegistryInstallDir')

    def _add_get_install_dir_from_registry(self):
        name = self._package_var().replace(' ', '')
        if isinstance(self.package, InstallerPackage):
            name = self.package.windows_sdk_reg or name

        key = self._registry_key(name)

        # Get INSTALLDIR from the registry key
        installdir_prop = etree.SubElement(self.product, 'Property', Id='GSTINSTALLDIR')
        etree.SubElement(
            installdir_prop, 'RegistrySearch', Id=name, Type='raw', Root=self.REG_ROOT, Key=key, Name='InstallDir'
        )

    def _add_merge_module(self, package, required, selected, required_packages):
        # Create a new feature for this package
        feature = etree.SubElement(
            self.main_feature,
            'Feature',
            Id=self._format_id(package.name),
            Title=package.shortdesc,
            Level=self._format_level(selected),
            Display='expand',
        )
        if required:
            feature.set('AllowAbsent', 'no')
        deps = self.store.get_package_deps(package, True)

        # Add all the merge modules required by this package, but excluding
        # all the ones that are forced to be installed
        if not required:
            mergerefs = list(set(deps) - set(required_packages))
        else:
            mergerefs = [x for x in deps if x in required_packages]

        # don't add empty packages
        mergerefs = [x for x in mergerefs if x in list(self.packages_deps.keys())]

        for p in mergerefs:
            etree.SubElement(feature, 'MergeRef', Id=self._package_id(p.name))
        # FIXME (remove this special casing): https://github.com/wixtoolset/issues/issues/8558
        if isinstance(package, VSTemplatePackage):
            etree.SubElement(feature, 'ComponentGroupRef', Id=self._format_group_id(package.name))
            etree.SubElement(feature, 'Level', Value='0', Condition=f'NOT VS{package.year}DEVENV')
        else:
            etree.SubElement(feature, 'MergeRef', Id=self._package_id(package.name))

    def _add_start_menu_shortcuts(self):
        # Create a folder with the application name in the Start Menu folder
        programs = etree.SubElement(self.target_dir, 'Directory', Id='ProgramMenuFolder')
        etree.SubElement(programs, 'Directory', Id='ApplicationProgramsFolder', Name='$(var.ProductName)')
        # Add the shortcut to the installer package
        appf = etree.SubElement(self.product, 'DirectoryRef', Id='ApplicationProgramsFolder')
        apps = etree.SubElement(appf, 'Component', Id='ApplicationShortcut', Guid=self._get_uuid())
        for desc, path, _, _ in self.package.commands[self.config.target_platform]:
            etree.SubElement(
                apps,
                'Shortcut',
                Id='ApplicationStartMenuShortcut',
                Name=desc,
                Description=desc,
                Target='[INSTALLBINDIR]' + path,
                WorkingDirectory='INSTALLBINDIR',
                Icon='MainIcon',
            )
        etree.SubElement(apps, 'RemoveFolder', Id='ApplicationProgramsFolder', On='uninstall')
        etree.SubElement(
            apps,
            'RegistryValue',
            Root='HKCU',
            Key=r'Software\Microsoft\%s' % self.package.name,
            Name='installed',
            Type='integer',
            Value='1',
            KeyPath='yes',
        )
        # Ref it in the main feature
        etree.SubElement(self.main_feature, 'ComponentRef', Id='ApplicationShortcut')

    def _add_vs_properties(self):
        etree.SubElement(self.product, f'{{{WIX_VS_SCHEMA}}}FindVisualStudio')
        etree.SubElement(self.product, 'PropertyRef', Id='VS2017DEVENV')
        etree.SubElement(self.product, 'PropertyRef', Id='VS2019DEVENV')
        etree.SubElement(self.product, 'PropertyRef', Id='VS2022DEVENV')
