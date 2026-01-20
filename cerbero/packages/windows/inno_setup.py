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
from cerbero.utils import decorator_escape_path, determine_num_of_cpus, m, shell, to_winepath


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


def format_inno_feature_id(string, package_type):
    # Remove suffix if present
    if package_type and string.endswith(package_type):
        string = string.removesuffix(package_type)
    # converting it into a nested component
    if package_type:
        package_type = package_type[1:]
    else:
        package_type = 'runtime'

    ret = string.replace('_', '__')
    for r in ['/', '-', ' ', '@', '+', '.']:
        ret = ret.replace(r, '_')
    # For directories starting with a number
    if re.match(r'[0-9]', ret):
        return package_type + '/' + 'innogst' + ret
    return package_type + '/' + ret


def feature_type(package_type):
    if package_type == PackageType.DEVEL:
        return ['full', 'custom']
    elif package_type == PackageType.DEBUG:
        return ['full', 'custom']
    else:
        return ['full', 'compact', 'custom']


def description(package_type):
    if package_type == PackageType.DEVEL:
        return 'Development'
    elif package_type == PackageType.DEBUG:
        return 'Debugging'
    else:
        return 'Runtime'


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
        elif package_type == PackageType.DEBUG:
            files_list = package.debug_files_list()
        else:
            files_list = package.files_list()
        if not files_list:
            m.warning('Package %s is empty, skipping listing generation' % package.name)
            return {}

        listing = {}
        listing['component'] = format_inno_feature_id(package.name, package_type)
        # Shortdesc incorporates the "(Development files)"
        listing['description'] = package.shortdesc
        listing['types'] = feature_type(package_type)

        if required:
            listing['flags'] = ['fixed']

        if isinstance(package, VSTemplatePackage):
            listing['check'] = f"gst_is_vs_version_installed('{package.year}') and is_admin_install"

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
        return listing

    def _create_features(self, package_type: str, rules: IOBase, force=False):
        self.package.set_mode(package_type)
        packagedeps = {self.store.get_package(x[0]): (x[1], x[2]) for x in self.package.packages}
        transitive_deps = {}
        for package, (required, selected) in packagedeps.items():
            for p in self.store.get_package_deps(package, True):
                if p not in packagedeps:
                    if p in transitive_deps:
                        old = transitive_deps[p]
                        transitive_deps[p] = (old[0] or required, old[1] or selected)
                    else:
                        transitive_deps[p] = (required, selected)
        packagedeps.update(transitive_deps)
        features = [
            {
                'component': package_type[1:] if package_type else 'runtime',
                'types': feature_type(package_type),
                'description': description(package_type),
            }
        ]
        features.extend(
            [
                self._create_listing(rules, package, package_type, required=required, force=force)
                for package, (required, _) in packagedeps.items()
            ]
        )
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
            rules.write(f'AppVersion={self.package.version}\n')
            # https://jrsoftware.org/ishelp/topic_setup_versioninfoversion.htm
            # Missing entries (e.g. patch and revision) will be completed with zeros
            rules.write(f'VersionInfoVersion={self.package.version}\n')
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
            rules.write('Compression=lzma2/max\nCompressionThreads=auto\nLZMAUseSeparateProcess=yes\n')
            # Solid compression allows parallelization but makes
            # unused files unable to be skipped during decompression
            # See https://jrsoftware.org/ishelp/index.php?topic=setup_solidcompression
            cores = determine_num_of_cpus()
            if cores > 1:
                rules.write(f'SolidCompression=yes\nLZMANumBlockThreads={cores}\n')

            # Output filename
            rules.write(f'OutputBaseFilename={self._package_name()}\n')
            rules.write('OutputDir=.\n')
            rules.write('DefaultDirName={autopf}/gstreamer/1.0\n')

            # Logging
            rules.write('SetupLogging=yes\n')
            rules.write('UninstallLogging=yes\n')

            # Detect portable mode
            rules.write('Uninstallable=not is_portable_mode_enabled\n')
            # Template install and registration requires admin access
            rules.write('PrivilegesRequired=admin\n')
            rules.write('PrivilegesRequiredOverridesAllowed=dialog\n')

            features = []
            for t in [PackageType.RUNTIME, PackageType.DEVEL, PackageType.DEBUG]:
                features += self._create_features(t, rules, force)

            # Now take all the files in each feature, label them by component
            files = {}
            for feature in features:
                if 'files' not in feature:
                    continue
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
                if 'check' in feature:
                    rules.write(f" Check: {feature['check']}; ")
                if 'flags' in feature:
                    flags = ' '.join(feature['flags'])
                    rules.write(f' Flags: {flags};')
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
                    'Name: "install_vcredist"; Description: "Install the Visual C++ Redistributable (2015-2022)"; Components: runtime/gstreamer_1_0_core; Check: is_admin_install;\n'
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
                f'Name: "environment_variables"; Description: "Set or update the {root_env_var} environment variable"; Components: runtime/gstreamer_1_0_core; Flags: checkedonce; Check: is_admin_install;\n'
            )
            rules.write(
                f'Name: "registry_install_dir"; Description: "Set or update the {registry_subkey_name} Registry variable"; Components: runtime/gstreamer_1_0_core; Flags: checkedonce; Check: is_admin_install;\n'
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
