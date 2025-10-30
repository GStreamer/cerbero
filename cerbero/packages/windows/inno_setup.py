# SPDX-FileCopyrightText: 2024 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later

from __future__ import annotations
from io import IOBase
import os
from pathlib import Path
import re
import shutil
import tempfile

from cerbero.config import Architecture, Platform
from cerbero.errors import FatalError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.package import SDKPackage, Package
from cerbero.packages.wix import VSTemplatePackage
from cerbero.utils import decorator_escape_path, m, shell, to_winepath


@decorator_escape_path
def get_inno_setup_path(config):
    if config.cross_compiling():
        return 'C:/Program Files (x86)/Inno Setup 6/iscc.exe'
    progfiles = ('C:/Program Files/', 'C:/Program Files (x86)/')
    tool = 'Inno Setup 6/iscc.exe'
    for d in progfiles:
        iscc = Path(d, tool)
        if iscc.exists():
            return iscc.as_posix()
    raise FatalError('The required packaging tool Inno Setup 5.0 was not found')


def format_inno_feature_id(string):
    ret = string.replace('_', '__')
    for r in ['/', '-', ' ', '@', '+', '.']:
        ret = ret.replace(r, '_')
    # For directories starting with a number
    if re.match(r'[0-9]', ret):
        return 'innogst' + ret
    return ret


def format_win32_version(version):
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


class InnoSetup(PackagerBase):
    # FIXME: with_wine throughout this
    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self._with_wine = config.platform != Platform.WINDOWS
        self.architecture = config.target_arch
        self.inno_prefix = get_inno_setup_path(config)
        self.abi_desc = ' '.join(config._get_toolchain_target_platform_arch(readable=True))

    def _package_name(self):
        if self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'
        if self.config.variants.visualstudio and self.config.variants.vscrt == 'mdd':
            platform += '+debug'
        return '-'.join((self.package.name, platform, self.config.target_arch, self.package.version))

    def _create_listing(
        self, rules: IOBase, package: Package, package_type: str, required=False, selected=False, force=False
    ):
        """
        Takes the given Package, extracts the list, and generates a
        dictionary containing the feature's metadata and the list of
        files it will install.
        """
        package.set_mode(package_type)
        m.action(f'Creating feature for {package.name}')
        # FIXME: this should be an Inno Setup subclass returning just the list
        if package_type == PackageType.DEVEL:
            files_list = package.devel_files_list()
        else:
            files_list = package.files_list()
        if not files_list:
            m.warning('Package %s is empty, skipping listing generation' % package.name)
            return {}

        listing = {}
        listing['component'] = format_inno_feature_id(package.name)
        # Shortdesc incorporates the "(Development files)"
        listing['description'] = package.shortdesc
        if package_type == PackageType.DEVEL:
            listing['types'] = ['devel', 'custom']
        # elif package_type == PackageType.DEBUG:
        #     listing['types'] = ['devel', 'debug', 'runtime', 'custom']
        else:
            listing['types'] = ['devel', 'runtime', 'custom']  # , 'debug',

        if required:
            listing['flags'] = ['fixed']

        if isinstance(package, VSTemplatePackage):
            listing['check'] = f"gst_is_vs_version_installed('{package.year}')"

        files = {}
        for filepath in files_list:
            source = os.path.join(self.config.prefix, filepath)
            if self._with_wine:
                source = to_winepath(source)
            dirpath, _ = os.path.split(filepath)
            # Customize install folders
            if isinstance(package, VSTemplatePackage):
                if dirpath.startswith(package.vs_wizard_dir):
                    dirpath = dirpath.replace(
                        package.vs_wizard_dir,
                        f'{{code:gst_vs_wizard_folder|{package.year}}}/{package.vs_template_name}',
                    )
                elif dirpath.startswith(package.vs_template_dir):
                    dirpath = dirpath.replace(
                        package.vs_template_dir,
                        f'{{code:gst_vs_templates_folder|{package.year}}}/{package.vs_template_name}',
                    )
                else:
                    raise RuntimeError(f'Unknown file payload {dirpath}')
            else:
                dirpath = f'{{app}}/{dirpath}'
            files[source] = dirpath
        listing['files'] = files

        listing['requires'] = [format_inno_feature_id(p.name) for p in self.store.get_package_deps(package, True)]
        return listing

    def _create_features(self, package_type: str, rules: IOBase, force=False):
        self.package.set_mode(package_type)
        packagedeps = {self.store.get_package(x[0]): (x[1], x[2]) for x in self.package.packages}
        transitive_deps = {}
        for package, (required, selected) in packagedeps.items():
            for p in self.store.get_package_deps(package, True):
                if p not in packagedeps:
                    # FIXME: assume they're all required/selected equally
                    transitive_deps[p] = (required, selected)
        packagedeps.update(transitive_deps)
        features = [
            self._create_listing(rules, package, package_type, required=required, force=force)
            for package, (required, _) in packagedeps.items()
        ]
        # Remove unused features
        return [f for f in features if f]

    def _registry_key(self, name):
        return 'Software\\%s\\%s' % (name, self.config.target_arch)

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        """
        Create the scroll of incantation and then call Inno Setup to assemble it
        """
        # These are the outputs of the Inno process
        # All the paths must be understood relative to self.output_dir
        paths = PackagerBase.pack(self, output_dir, devel, force, keep_temp)
        # Generate it right now, while we haven't specified a package mode
        paths = [Path(f'{self._package_name()}.exe')]
        registry_subkey_name = self.package.shortdesc.replace(' ', '')
        registry_subkey = self._registry_key(registry_subkey_name)
        # This is the directory where Inno will run
        output_dir = Path(output_dir).absolute()
        self.output_dir = Path(tempfile.mkdtemp(prefix=f'inno-{self._package_name()}-', dir=output_dir))

        # Calm Git if you're running this interactively
        with (self.output_dir / '.gitignore').open('w', encoding='utf-8') as f:
            f.write('*\n')

        # Set project up
        m.action(f'Creating Inno Setup project for {self.package.name}')
        iss_project = self.output_dir / 'installer.iss'
        with iss_project.open('w', encoding='utf-8') as rules:
            rules.write(f'// This is the build file for the installer "{self._package_name()}"\n')
            rules.write('// It is autogenerated by Cerbero.\n')
            rules.write('// Do not edit by hand.\n')

            # Generate Visual Studio setup detection code
            base_iss = Path(self.config.data_dir) / 'inno' / 'base.iss'
            rules.write(f'\n#include "{base_iss.as_posix()}"\n')

            rules.write('\n[Setup]\n')

            # EXE metadata etc.
            rules.write(f'AppId={self.package.get_wix_upgrade_code()}\n')
            rules.write(f'AppName="{self.package.shortdesc} ({self.abi_desc})"\n')
            rules.write(f'AppVersion={format_win32_version(self.package.version)}\n')
            if getattr(self.package, 'vendor', None):
                rules.write(f'AppPublisher={self.package.vendor}\n')
            if getattr(self.package, 'url', None):
                rules.write(f'AppPublisherUrl={self.package.url}\n')

            # UI properties
            rules.write('WizardStyle=modern dynamic\n')
            wizard_image_file = Path(self.package.relative_path('background_inno.png'))
            if wizard_image_file.exists():
                rules.write(f'WizardImageFile={wizard_image_file.as_posix()}\n')
            wizard_image_file = Path(self.package.relative_path('background_inno_dark.png'))
            if wizard_image_file.exists():
                rules.write(f'WizardImageFileDynamicDark={wizard_image_file.as_posix()}\n')
            wizard_small_image_file = Path(self.package.relative_path('icon.png'))
            if wizard_small_image_file.exists():
                rules.write(f'WizardSmallImageFile={wizard_small_image_file.as_posix()}\n')
            rules.write('DisableWelcomePage=no\n')
            icon_file = Path(self.package.relative_path('icon.ico'))
            if icon_file.exists():
                rules.write(f'SetupIconFile={icon_file.as_posix()}\n')
            license_file = Path(self.package.relative_path('license.rtf'))
            if license_file.exists():
                rules.write(f'LicenseFile={license_file.as_posix()}\n')

            # Architectures
            if self.config.target_arch == Architecture.X86:
                rules.write('ArchitecturesAllowed=x86compatible\n')
            else:
                rules.write('ArchitecturesAllowed=x64compatible\n')
                rules.write('ArchitecturesInstallIn64BitMode=x64compatible\n')

            # Compression
            # Solid compression disabled to skip decompression of unused files
            rules.write(
                'Compression=lzma2/max\n'
                'LZMANumBlockThreads=4\n'
                'CompressionThreads=auto\nSolidCompression=no\nLZMAUseSeparateProcess=yes\n'
            )

            # Output filename
            rules.write(f'OutputBaseFilename={self._package_name()}\n')
            rules.write('OutputDir=.\n')
            rules.write('DefaultDirName={autopf}/gstreamer/1.0\n')

            # Logging
            rules.write('SetupLogging=yes\n')
            rules.write('UninstallLogging=yes\n')

            # Template install and registration requires admin access
            rules.write('PrivilegesRequired=admin\n')

            # Generate Runtime + Devel package
            rules.write('\n[Types]\n')
            rules.write('Name: "devel"; Description: "Runtime, debug symbols, and development headers"\n')
            # FIXME uncomment when my split debuginfo MR is merged
            # rules.write('Name: "debug"; Description: "Runtime + debug symbols"\n')
            rules.write('Name: "runtime"; Description: "Only runtime"\n')
            rules.write('Name: "custom"; Description: "Custom installation"; Flags: iscustom\n')

            # FIXME: this needs to cycle between runtime, debug, devel
            features = []
            for t in [PackageType.RUNTIME, PackageType.DEVEL]:
                features += self._create_features(t, rules, force)

            # Now take all the files in each feature, label them by component
            files = {}
            for feature in features:
                feature_name = feature['component']
                m.action(f'Deduplicating files for feature {feature_name}')
                for file, destdir in feature['files'].items():
                    if file in files:
                        if destdir in files[file]:
                            files[file][destdir].add(feature_name)
                        else:
                            files[file][destdir] = set([feature_name])
                    else:
                        files[file] = {destdir: set([feature_name])}

            m.action('Listing components in project')
            # FIXME: improve component matrix -- devel and debug should depend
            # on runtime, maybe with sublevels
            rules.write('\n[Components]\n')
            for feature in features:
                name = feature['component']
                description = feature['description']
                types = ' '.join(feature['types'])
                rules.write(f'Name: {name}; Description: "{description}"; Types: {types};')
                if 'check' in feature.keys():
                    rules.write(f" Check: {feature['check']};")
                if 'flags' in feature.keys():
                    flags = ' '.join(feature['flags'])
                    rules.write(f'Flags: {flags};')
                rules.write('\n')

            # Then generate the complete [Files] Listing
            # Source: "file key"; DestDir: "dest"; Components: "list" "of" "components" "which" "need" "it"
            # (Sorting has no effect here re: compression ratio,
            # it seems Inno is clever enough)
            entries = []
            for file, info in files.items():
                for destdir, components in info.items():
                    entries.append((file, destdir, ' '.join(components)))
            rules.write('\n[Files]\n')
            m.action('Writing file entries')
            for file in entries:
                rules.write(
                    f'Source: "{file[0]}"; DestDir: "{file[1]}"; Components: {file[2]}; Flags: ignoreversion;\n'
                )

            # Embed the Visual C++ Redistributable
            if self.config.variants.visualstudio:
                vc_tools_redist_dir = self.config.msvc_env_for_toolchain['VCToolsRedistDir']
                if self.config.target_arch == Architecture.X86:
                    redist_path = Path(vc_tools_redist_dir.get(), 'vc_redist.x86.exe')
                else:
                    redist_path = Path(vc_tools_redist_dir.get(), 'vc_redist.x64.exe')
                m.action('Embedding Visual C++ Redistributable')
                rules.write('\n[Tasks]\n')
                rules.write(
                    'Name: "install_vcredist"; Description: "Install the Visual C++ Redistributable (2015-2022)"; Components: gstreamer_1_0_core;\n'
                )
                rules.write('\n[Files]\n')
                rules.write(
                    f'Source: "{redist_path.as_posix()}"; DestDir: "{{tmp}}"; DestName: "{redist_path.name}"; Flags: ignoreversion deleteafterinstall; Tasks: install_vcredist;\n'
                )
                rules.write('\n[Run]\n')
                rules.write(
                    f'Filename: "{{tmp}}/{redist_path.name}"; Parameters: "/install /passive /quiet /norestart"; Description: "Installing the Visual C++ Redistributable (2015-2022)"; Flags: logoutput; Tasks: install_vcredist;\n'
                )

            # Set up environment variables and registry key
            platform_arch = '_'.join(self.config._get_toolchain_target_platform_arch())
            root_env_var = self.package.get_root_env_var(platform_arch)
            rules.write('\n[Setup]\n')
            rules.write('ChangesEnvironment=yes\n')
            rules.write('\n[Tasks]\n')
            rules.write(
                f'Name: "environment_variables"; Description: "Set or update the {root_env_var} environment variable"; Components: gstreamer_1_0_core; Flags: checkedonce;\n'
            )
            rules.write(
                f'Name: "registry_install_dir"; Description: "Set or update the {registry_subkey_name} Registry variable"; Components: gstreamer_1_0_core; Flags: checkedonce;\n'
            )
            rules.write('\n[Registry]\n')
            rules.write(
                f'Root: "HKA"; Subkey: "SYSTEM\\CurrentControlSet\\Control\\Session Manager"; ValueType: string; ValueName: "{root_env_var}"; ValueData: "{{app}}"; Flags: createvalueifdoesntexist preservestringtype; Tasks: environment_variables\n'
            )
            rules.write(
                f'Root: "HKA"; Subkey: "{registry_subkey}"; ValueType: string; ValueName: "InstallDir"; ValueData: "{{app}}"; Flags: createvalueifdoesntexist preservestringtype; Tasks: registry_install_dir\n'
            )
            rules.write(
                f'Root: "HKA"; Subkey: "{registry_subkey}"; ValueType: string; ValueName: "Version"; ValueData: "{self.package.version}"; Flags: createvalueifdoesntexist preservestringtype; Tasks: registry_install_dir\n'
            )
            rules.write(
                f'Root: "HKA"; Subkey: "{registry_subkey}"; ValueType: string; ValueName: "SdkVersion"; ValueData: "{self.package.sdk_version}"; Flags: createvalueifdoesntexist preservestringtype; Tasks: registry_install_dir\n'
            )

        # Execute Inno on the chosen output directory
        m.action(f'Building {self._package_name()} in {self.output_dir}')
        # Qp: log progress and errors only
        shell.new_call([self.inno_prefix, '/Qp', iss_project.name], cmd_dir=self.output_dir, env=self.config.env)

        # Copy the outputs to the output directory
        for p in paths:
            src = self.output_dir / p
            dst = output_dir / p
            m.action(f'Moving {p} to {output_dir}')
            shutil.move(src, dst)

        # Clean up the temporary build directory
        if keep_temp:
            m.action(f'Temporary build directory is at {self.output_dir}')
        else:
            shutil.rmtree(self.output_dir)

        return paths


class Packager(object):
    ARTIFACT_TYPE = 'inno'

    def __new__(cls, config, package, store):
        if isinstance(package, SDKPackage):
            return InnoSetup(config, package, store)
        else:
            raise RuntimeError('Inno Setup is a singleton SDK generator')


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro

    register_packager(Distro.WINDOWS, Packager)
