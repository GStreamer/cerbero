import functools
import json
import keyword
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

from cerbero.enums import Architecture, License, Platform
from cerbero.utils import messages as m, shell
from cerbero.packages import PackagerBase
from cerbero.packages.package import SDKPackage
from cerbero.tools import dsymutil


@functools.lru_cache()
def _exe_extensions():
    return os.getenv('PATHEXT', '').lower().split(';')


def _is_executable(source):
    if sys.platform == 'win32':
        return source.suffix.lower() in _exe_extensions()
    else:
        return os.access(source.as_posix(), mode=os.F_OK | os.X_OK)


def _is_gstreamer_executable(source: Path):
    filename = source.name
    if filename.startswith('gst-') or filename.startswith('ges-'):
        return _is_executable(source)
    return False


def generate_entrypoint(path):
    base = Path(path).name.replace('.', '_')

    # snake_case_ify
    # Insert underscore before any uppercase preceding digit or lowercase
    base = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', base)
    # Separate words and acronyms with underscore
    # (makes sure HTTPFoo.exe becomes HTTP_Foo)
    base = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', base)
    # Remove all non-alphabetic characters
    base = re.sub(r'[^a-zA-Z0-9_]+', '_', base.lower())

    # Collapse repetitions and trim
    base = re.sub(r'_+', '_', base).strip('_')

    # Sanitize if keyword or starts with a digit
    if base[0].isdigit() or keyword.iskeyword(base):
        base = f'_{base}'

    return base


class WheelPackager(PackagerBase):
    PYTHON_VERSION_CLASSIFIERS = {
        9: 'Programming Language :: Python :: 3.9',
        10: 'Programming Language :: Python :: 3.10',
        11: 'Programming Language :: Python :: 3.11',
        12: 'Programming Language :: Python :: 3.12',
        13: 'Programming Language :: Python :: 3.13',
        14: 'Programming Language :: Python :: 3.14',
        15: 'Programming Language :: Python :: 3.15',
    }

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.architecture = config.target_arch
        self.platform = config.target_platform
        self.abi_desc = ' '.join(config._get_toolchain_target_platform_arch(readable=True))

    def _get_classifiers(self, license):
        """
        Complete classifier list: https://pypi.org/pypi?%3Aaction=list_classifiers
        """
        versions = list(map(int, self.package.version.split('.', maxsplit=3)))
        classifiers = []
        if versions[1] % 2 == 0:
            classifiers += ['Development Status :: 5 - Production/Stable']
        elif versions[2] == 0:
            classifiers += ['Development Status :: 2 - Pre-Alpha']
        elif versions[2] >= 50:
            classifiers += ['Development Status :: 4 - Beta']
        else:
            classifiers += ['Development Status :: 3 - Alpha']

        classifiers += [
            'Intended Audience :: Developers',
            'Programming Language :: Python :: 3',
            'Topic :: Multimedia :: Graphics',
            'Topic :: Multimedia :: Sound/Audio',
            'Topic :: Multimedia :: Video',
            'Topic :: Software Development',
            'Topic :: Utilities',
            'Environment :: MacOS X',
            'Operating System :: MacOS :: MacOS X',
            'Environment :: Win32 (MS Windows)',
            'Operating System :: Microsoft :: Windows',
        ]

        return classifiers

    def _package_name(self):
        if self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'
        if self.config.variants.visualstudio and self.config.variants.vscrt == 'mdd':
            platform += '+debug'
        return '-'.join((self.package.name, platform, self.config.target_arch, self.package.version))

    def _create_wheel(
        self,
        package_name,
        files_list=(),
        license=License.LGPLv2_1Plus.acronym,
        classifiers=(),
        dependencies=(),
        features=None,
        desc='',
    ):
        # Set project up
        m.action(f'Creating setuptools project for {package_name}')
        base_tree = Path(self.config.data_dir) / 'wheel'
        output_dir = self.output_dir / package_name

        longdesc = ''
        if package_name in ('gstreamer', 'gstreamer_bundle'):
            with open(base_tree / 'gstreamer.md', 'r') as f:
                longdesc = f.read()
        elif package_name == 'gstreamer_meta':
            with open(base_tree / 'gstreamer_meta.md', 'r') as f:
                longdesc = f.read()

        if longdesc:
            longdesc += '\n'
            with open(base_tree / 'about.md', 'r') as f:
                longdesc += f.read()
        else:
            longdesc = (
                'This wheel is not self-contained, it is meant to be used as part of the '
                '[gstreamer_bundle](/project/gstreamer-bundle/) or '
                '[gstreamer_meta](/project/gstreamer-meta/) packages.'
            )

        # Copy files manually (the last one needs to match the package name)
        shutil.copy(base_tree / 'setup.py', output_dir)
        shutil.copy(base_tree / 'pyproject.toml', output_dir)
        shutil.copytree(base_tree / package_name, output_dir / package_name, dirs_exist_ok=True)
        m.action(f'Generating MANIFEST.in for {package_name}')
        with (output_dir / 'MANIFEST.in').open('w', encoding='utf-8', newline='\n') as f:
            f.write(f'graft {package_name}\n')

        scripts = []
        entrypoints = []
        if files_list:
            m.action(f'Copying distribution payload for {package_name}')
            for filepath in files_list:
                source = Path(self.config.prefix, filepath)
                dirpath, filename = os.path.split(filepath)
                # If executable
                if dirpath.startswith('bin') and _is_gstreamer_executable(source):
                    m.action(f'Adding entrypoint for {filepath}')
                    entrypoint_name = generate_entrypoint(filepath)
                    if source.name.endswith('.exe'):
                        source_name = source.stem
                    else:
                        source_name = source.name
                    scripts.append(f'{source_name} = {package_name}.entrypoints:{entrypoint_name}')
                    entrypoints += [f'def {entrypoint_name}():\n', f"    return __run('{filename}')\n"]

        if entrypoints:
            entrypoints = ['\n', '\n', *entrypoints]
            m.action('Filling up entrypoints in the Python module')
            with (output_dir / package_name / 'entrypoints.py').open('a', encoding='utf-8', newline='\n') as f:
                f.writelines(entrypoints)

        m.action(f'Generating metadata JSON for {package_name}')
        package_info = {
            'package_name': package_name,
            'version': self.package.version,
            'description': desc,
            'long_description': longdesc,
            'long_description_content_type': 'text/markdown',
            'url': self.package.url,
            'vendor': self.package.vendor,
            'spdx_license': license,
            'classifiers': classifiers,
            # This should be set to the same version for all wheels for
            # a particular package/project/"release". It refers to the
            # source-level compatibility for the project.
            # https://docs.astral.sh/uv/reference/internals/resolver/#metadata-consistency
            'python_version': '>= 3.9',
            'install_requires': dependencies,
            'extras_require': features,
            'entrypoints': {
                'console_scripts': scripts,
            }
            if scripts
            else {},
            # A fancy way of saying "metapackage"
            'needs_environment': not files_list,
        }
        with (output_dir / 'gstreamer_vendor.json').open('w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(package_info))

        # Execute on the chosen output directory
        m.action(f'Building {package_name} in {self.output_dir}')
        python_exe = os.path.join(self.config.build_tools_prefix, 'bin', 'python')
        # Need to set PYTHONPATH correctly on (at least) macOS to use the
        # specified Python inside the venv for pip, but on Windows that
        # completely breaks Python and it can't find pip.
        python_env = self.config.env if self.config.platform != Platform.WINDOWS else None
        shell.new_call(
            [python_exe, '-m', 'pip', 'wheel', f'--find-links={self.output_dir.as_posix()}', output_dir],
            cmd_dir=self.output_dir,
            env=python_env,
        )

    def get_file_type(self, filepath):
        return shell.check_output(['file', '-bh', filepath])[:-1]  # remove trailing \n

    def _create_wheels(self):
        packagedeps = self.store.get_package_deps(self.package, True)

        debuginfo_files_list = []
        gpl_files_list = []
        gpl_restricted_files_list = []
        restricted_files_list = []
        plugins_list = []
        frei0r_list = []
        gtk_list = []
        plugins_libs_list = []
        libs_list = []
        python_list = []
        cli_list = []

        gpl_restricted_licenses = set()
        restricted_licenses = set()
        gpl_licenses = set()
        gtk_licenses = set()
        python_licenses = set()
        libs_licenses = set()
        plugins_licenses = set()
        plugins_libs_licenses = set()

        def _parse_licenses(package):
            result = set()
            for _recipe, categories in p.recipes_licenses().items():
                for _c, lst in categories.items():
                    result.update(lst)
            return result

        for p in packagedeps:
            m.action(f'Parsing distribution payload for {p.name}')
            debuginfo_files_list += p.debug_files_list()
            if '-gpl-restricted' in p.name:
                gpl_restricted_files_list += p.files_list()
                gpl_restricted_licenses.update(_parse_licenses(p))
            elif '-restricted' in p.name:
                restricted_files_list += p.files_list()
                restricted_licenses.update(_parse_licenses(p))
            elif '-gpl' in p.name:
                gpl_files_list += p.files_list()
                gpl_licenses.update(_parse_licenses(p))
            elif p.name.startswith('base-'):
                libs_list += p.files_list()
                libs_licenses.update(_parse_licenses(p))
            elif p.name.endswith('-editing'):
                for f in p.files_list():
                    if 'gstreamer-1.0' in f:
                        plugins_libs_list.append(f)
                    elif f.startswith('bin/'):
                        cli_list.append(f)
                    else:
                        libs_list.append(f)
                libs_licenses.update(_parse_licenses(p))
            elif p.name.endswith('-python'):
                python_list += p.files_list()
                python_licenses.update(_parse_licenses(p))
            elif p.name.endswith('-gtk'):
                gtk_list += p.files_list()
                gtk_licenses.update(_parse_licenses(p))
            else:
                for f in p.files_list():
                    source = Path(self.config.prefix, f)
                    if _is_gstreamer_executable(source) and 'libexec' not in source.parts:
                        cli_list.append(f)
                    elif p.name.endswith('-core') or p.name.endswith('-devtools'):
                        libs_licenses.update(_parse_licenses(p))
                        libs_list.append(f)
                    elif 'frei0r' in f:
                        frei0r_list.append(f)
                    elif 'gstreamer-1.0' in f:
                        plugins_list.append(f)
                        plugins_licenses.update(_parse_licenses(p))
                    else:
                        plugins_libs_list.append(f)
                        plugins_libs_licenses.update(_parse_licenses(p))

        # HERE IS THE MAIN SOURCE OF TRUTH. IF ANYTHING NEEDS FIXING IT'S HERE.
        # (package name, payload, license (SPDX is acronym?), and dependencies/features)
        # When adding a new package here, also edit
        # data/wheel/gstreamer_libs/__init__.py:gstreamer_env()
        package_files_list = {
            'gstreamer_libs': libs_list,
            'gstreamer_plugins_libs': plugins_libs_list,
            'gstreamer_debuginfo': debuginfo_files_list,
            'gstreamer_plugins': plugins_list,
            'gstreamer_plugins_frei0r': frei0r_list,
            'gstreamer_plugins_gpl': gpl_files_list,
            'gstreamer_plugins_gpl_restricted': gpl_restricted_files_list,
            'gstreamer_plugins_restricted': restricted_files_list,
            'gstreamer_cli': cli_list,
            'gstreamer_python': python_list,
            'gstreamer_gtk': gtk_list,
            'gstreamer_meta': [],
            'gstreamer_bundle': [],
            'gstreamer': [],
        }
        package_files_list['gstreamer_bundle'] = package_files_list['gstreamer']

        package_desc = {
            'gstreamer_libs': 'GStreamer API Libraries',
            'gstreamer_plugins_libs': 'Third-party libraries used by GStreamer Plugins',
            'gstreamer_debuginfo': 'Debug symbols for all GStreamer wheels',
            'gstreamer_plugins': 'GStreamer plugins',
            'gstreamer_plugins_frei0r': 'GStreamer frei0r plugin, including frei0r-plugins',
            'gstreamer_plugins_gpl': 'GStreamer GPL/AGPL plugins',
            'gstreamer_plugins_gpl_restricted': 'GStreamer GPL/AGPL plugins that are known to be patent encumbered',
            'gstreamer_plugins_restricted': 'GStreamer plugins that are known to be patent encumbered',
            'gstreamer_cli': 'GStreamer command-line utilities',
            'gstreamer_python': 'Python bindings and plugins for GStreamer',
            'gstreamer_gtk': 'GStreamer gtk4paintablesink plugin and dependencies, including GTK4 itself',
            'gstreamer_meta': "Meta-package to install a subset of GStreamer plugins via 'extras'",
            'gstreamer': 'Meta-package to install all GStreamer plugins and libraries',
        }
        package_desc['gstreamer_bundle'] = package_desc['gstreamer']

        package_licenses = {
            'gstreamer_debuginfo': set()
            .union(gpl_restricted_licenses)
            .union(restricted_licenses)
            .union(gpl_licenses)
            .union(gtk_licenses)
            .union(python_licenses)
            .union(libs_licenses)
            .union(plugins_licenses)
            .union(plugins_libs_licenses),
            'gstreamer_plugins_gpl_restricted': gpl_restricted_licenses,
            'gstreamer_plugins_restricted': restricted_licenses,
            'gstreamer_plugins_gpl': gpl_licenses,
            # (fixed)
            'gstreamer_plugins_frei0r': [License.GPLv2Plus],
            'gstreamer_plugins_libs': plugins_libs_licenses,
            'gstreamer_libs': libs_licenses,
            # GStreamer supplied
            'gstreamer_cli': [License.LGPLv2_1Plus],
            'gstreamer_plugins': plugins_licenses,
            'gstreamer_python': python_licenses,
            'gstreamer_gtk': gtk_licenses,
            # GStreamer supplied
            'gstreamer_meta': [License.LGPLv2_1Plus],
            'gstreamer': [License.LGPLv2_1Plus],
        }
        package_licenses['gstreamer_bundle'] = package_licenses['gstreamer']

        package_dependencies = {
            'gstreamer_debuginfo': [],
            'gstreamer_libs': [
                'setuptools >= 80.9.0',
            ],
            # NOTE: gstreamer_python should not depend on gstreamer_libs,
            # because people should be able to install it standalone and point
            # it to their own gstreamer install.
            'gstreamer_cli': [f'gstreamer_libs ~= {self.package.version}'],
            'gstreamer_plugins_libs': [f'gstreamer_libs ~= {self.package.version}'],
            'gstreamer_plugins': [f'gstreamer_plugins_libs ~= {self.package.version}'],
            'gstreamer_plugins_frei0r': [f'gstreamer_plugins_libs ~= {self.package.version}'],
            'gstreamer_plugins_gpl': [f'gstreamer_plugins_libs ~= {self.package.version}'],
            'gstreamer_plugins_gpl_restricted': [f'gstreamer_plugins_libs ~= {self.package.version}'],
            'gstreamer_plugins_restricted': [f'gstreamer_plugins_libs ~= {self.package.version}'],
            'gstreamer_meta': [
                f'gstreamer_libs ~= {self.package.version}',
                f'gstreamer_plugins ~= {self.package.version}',
                f'gstreamer_python ~= {self.package.version}',
            ],
            'gstreamer': [
                f'gstreamer_cli ~= {self.package.version}',
                f'gstreamer_libs ~= {self.package.version}',
                f'gstreamer_plugins ~= {self.package.version}',
                f'gstreamer_plugins_gpl ~= {self.package.version}',
                f'gstreamer_plugins_gpl_restricted ~= {self.package.version}',
                f'gstreamer_plugins_restricted ~= {self.package.version}',
                f'gstreamer_python ~= {self.package.version}',
                f'gstreamer_gtk ~= {self.package.version}',
            ],
        }
        package_dependencies['gstreamer_bundle'] = package_dependencies['gstreamer']

        package_features = {
            'gstreamer_meta': {
                'cli': [f'gstreamer_cli ~= {self.package.version}'],
                'debuginfo': [f'gstreamer_debuginfo ~= {self.package.version}'],
                'frei0r': [f'gstreamer_plugins_frei0r ~= {self.package.version}'],
                'gpl': [f'gstreamer_plugins_gpl ~= {self.package.version}'],
                'gpl-restricted': [f'gstreamer_plugins_gpl_restricted ~= {self.package.version}'],
                'gtk': [f'gstreamer_gtk ~= {self.package.version}'],
                'restricted': [f'gstreamer_plugins_gpl ~= {self.package.version}'],
            },
            'gstreamer': {
                'frei0r': [f'gstreamer_plugins_frei0r ~= {self.package.version}'],
                'debuginfo': [f'gstreamer_debuginfo ~= {self.package.version}'],
            },
        }
        package_features['gstreamer_bundle'] = package_features['gstreamer']

        with (self.output_dir / 'categories.json').open('w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(package_files_list, indent=1))

        # Process the runtime wheel before anything else to prevent conflicts
        if self.config.variants.visualstudio:
            m.action('Adding wheel for Visual C++ Runtime')
            vc_tools_redist_dir = self.config.msvc_env_for_toolchain['VCToolsRedistDir']
            if self.config.target_arch == Architecture.X86:
                redist_path = Path(vc_tools_redist_dir.get(), 'x86')
            else:
                redist_path = Path(vc_tools_redist_dir.get(), 'x64')

            package_name = 'gstreamer_msvc_runtime'
            files_list = [f.as_posix() for f in redist_path.glob('**/*.dll')]
            license = License.Proprietary.acronym
            dependencies = []
            features = {}

            output_dir = self.output_dir / package_name
            output_dir.mkdir(parents=True, exist_ok=True)

            for source in files_list:
                dest = output_dir / package_name / 'bin'
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, dest)

            classifiers = self._get_classifiers(license)

            self._create_wheel(
                package_name,
                files_list,
                license,
                classifiers,
                dependencies,
                features,
                'MSVC runtime redist for GStreamer',
            )

            package_dependencies['gstreamer_libs'].append(f'{package_name} ~= {self.package.version}')

        for package_name, files_list in package_files_list.items():
            license = ' AND '.join(lic.acronym for lic in package_licenses[package_name])
            dependencies = package_dependencies.get(package_name, [])
            features = package_features.get(package_name, {})

            m.action(f'Copying distribution payload for {package_name}')

            output_dir = self.output_dir / package_name
            output_dir.mkdir(parents=True, exist_ok=True)

            for filepath in files_list:
                source = Path(self.config.prefix, filepath)
                dirpath = os.path.dirname(filepath)
                dest = output_dir / package_name / dirpath
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, dest)
                rpath_args = []
                if self.config.target_platform == Platform.DARWIN:
                    if source.suffix not in ('.so', '.dylib') and dest.name != 'bin':
                        continue
                    # We should not modify this, it's codesigned and copied as-is from the Vulkan SDK
                    if source.name == 'libMoltenVK.dylib':
                        continue
                    destpath = dest / source.name
                    if not dsymutil.is_macho_file(destpath):
                        continue
                    # Add rpath from the gi loader to other wheels that ship
                    # libs that have typelibs
                    if package_name == 'gstreamer_libs':
                        if 'girepository' in source.name or 'gmodule' in source.name:
                            for whl in ('gstreamer_gtk',):
                                relpath = os.path.relpath(f'{whl}/lib', f'{package_name}/{dirpath}')
                                rpath_args += ['-add_rpath', f'@loader_path/{relpath}']
                            shell.new_call(['install_name_tool'] + rpath_args + [destpath], env=self.config.env)
                        continue
                    # We need to route an RPATH from, say,
                    # ~/Library/Python/3.9/lib/python/site-packages/gstreamer_python/{dirpath}
                    # to
                    # ~/Library/Python/3.9/lib/python/site-packages/gstreamer_libs/lib
                    relpath = os.path.relpath('gstreamer_libs/lib', f'{package_name}/{dirpath}')
                    rpath_args += ['-add_rpath', f'@loader_path/{relpath}']
                    for dep in dependencies:
                        pkg = dep.split('~=')[0].strip()
                        if pkg == 'gstreamer_libs':
                            # Already added above
                            continue
                        relpath = os.path.relpath(f'{pkg}/lib', f'{package_name}/{dirpath}')
                        rpath_args += ['-add_rpath', f'@loader_path/{relpath}']
                    shell.new_call(['install_name_tool'] + rpath_args + [destpath], env=self.config.env)

            classifiers = self._get_classifiers(license)
            self._create_wheel(
                package_name, files_list, license, classifiers, dependencies, features, package_desc[package_name]
            )

        return list(self.output_dir.glob('**/gstreamer*.whl'))

    def pack(self, output_dir, devel=False, force=False, keep_temp=False):
        """
        Create the scroll of incantation and then call setup.py to assemble it
        """

        # As a first try, package the whole of gstreamer
        # entrypoints for all bin prefixed by `gst-` and `ges-`
        output_dir = Path(output_dir).absolute()
        self.output_dir = Path(tempfile.mkdtemp(prefix=f'wheel-{self._package_name()}-', dir=output_dir))

        # Calm Git if you're running this interactively
        with (self.output_dir / '.gitignore').open('w', encoding='utf-8') as f:
            f.write('*\n')

        # Create packages here (returns full paths!)
        paths = self._create_wheels()

        # Copy the outputs to the output directory
        for src in paths:
            dst = output_dir / src.name
            m.action(f'Moving {src} to {dst}')
            shutil.copy(src, dst)

        # Clean up the temporary build directory
        if keep_temp:
            m.action(f'Temporary build directory is at {self.output_dir}')
        else:
            shutil.rmtree(self.output_dir)

        return paths


class Packager(object):
    ARTIFACT_TYPE = 'wheel'

    def __new__(cls, config, package, store):
        if isinstance(package, SDKPackage):
            return WheelPackager(config, package, store)
        else:
            raise RuntimeError('Wheel is a singleton SDK generator')


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro

    register_packager(Distro.WINDOWS, Packager)
    register_packager(Distro.OS_X, Packager)
