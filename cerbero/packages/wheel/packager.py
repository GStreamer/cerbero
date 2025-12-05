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


@functools.lru_cache()
def _exe_extensions():
    return os.getenv('PATHEXT', '').lower().split(';')


def _is_executable(source):
    if sys.platform == 'win32':
        return source.suffix.lower() in _exe_extensions()
    else:
        return os.access(source.as_posix(), mode=os.F_OK | os.X_OK)


def _is_gstreamer_executable(source):
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

    LICENSE_CLASSIFIERS = {
        License.Proprietary: 'License :: Other/Proprietary License',
        License.LGPLv2_1Plus: 'License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)',
        License.GPLv2Plus: 'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
    }

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.architecture = config.target_arch
        self.platform = config.target_platform
        self.abi_desc = ' '.join(config._get_toolchain_target_platform_arch(readable=True))

        # complete classifier list: https://pypi.org/pypi?%3Aaction=list_classifiers
        self.classifiers = [
            'Development Status :: 4 - Beta',
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

        self.classifiers += [v for k, v in self.PYTHON_VERSION_CLASSIFIERS.items() if k >= sys.version_info[1]]

        self.license = getattr(self.package, 'license', License.Proprietary)

        self.classifiers.append(self.LICENSE_CLASSIFIERS[self.license])
        if self.license == License.Proprietary:
            m.warning('Unknown package license, assuming unredistributable!')

    def _package_name(self):
        if self.config.variants.uwp:
            platform = 'uwp'
        elif self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'
        if self.config.variants.visualstudio and self.config.variants.vscrt == 'mdd':
            platform += '+debug'
        return '-'.join((self.package.name, platform, self.config.target_arch, self.package.version))

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

        # Set project up
        m.action(f'Creating setuptools project for {self.package.name}')
        base_tree = Path(self.config.data_dir) / 'wheel'
        shutil.copytree(base_tree, self.output_dir, dirs_exist_ok=True)

        m.action(f'Generating MANIFEST.in for {self.package.name}')

        with (self.output_dir / 'MANIFEST.in').open('w', encoding='utf-8') as f:
            # Do I need to copy the whole tree...?
            # FIXME: girfiles are not runtime! (I think when sharding, we'll
            # have to copy them all)
            f.write('graft gstreamer\n')

        scripts = []
        entrypoints = ['\n', '\n']
        packagedeps = self.store.get_package_deps(self.package, True)
        for package in packagedeps:
            files_list = package.files_list()
            if not files_list:
                m.warning('Package %s is empty, skipping payload generation' % package.name)
                continue
            m.action(f'Copying distribution payload for {package.name}')
            for filepath in files_list:
                source = Path(self.config.prefix, filepath)
                dirpath, filename = os.path.split(filepath)
                # FIXME
                dest: Path = Path(self.output_dir) / 'gstreamer' / dirpath
                dest.mkdir(parents=True, exist_ok=True)
                shutil.copy(source, dest)

                # If executable
                # FIXME: as elsewhere, needs sharding
                if dirpath.startswith('bin') and _is_gstreamer_executable(source):
                    m.action(f'Adding entrypoint for {filepath}')
                    entrypoint_name = generate_entrypoint(filepath)
                    scripts.append(f'{source.stem} = gstreamer.entrypoints:{entrypoint_name}')
                    entrypoints += [f'def {entrypoint_name}():\n', f"    __run('{filename}')\n"]

        m.action('Filling up entrypoints in the Python module')
        # FIXME: as elsewhere, needs sharding
        with (self.output_dir / 'gstreamer' / 'entrypoints.py').open('a', encoding='utf-8') as f:
            f.writelines(entrypoints)

        m.action(f'Generating metadata JSON for {self.package.name}')
        gstreamer_vendor = {
            'package_name': self.package.name,
            'version': self.package.version,
            'description': self.package.shortdesc,
            'long_description': self.package.longdesc,
            'url': self.package.url,
            'vendor': self.package.vendor,
            'spdx_license': self.license.acronym,
            'classifiers': self.classifiers,
            'python_version': f'>= 3.{sys.version_info[1]}',
            'entrypoints': {
                'console_scripts': scripts,
            },
        }
        with (self.output_dir / 'gstreamer_vendor.json').open('w', encoding='utf-8') as f:
            f.write(json.dumps(gstreamer_vendor))

        # Ideally the user will have it installed, but can we rely on that?
        # Especially with mismatched versions?
        if self.config.variants.visualstudio:
            m.action('Embedding Visual C++ Runtime')
            vc_tools_redist_dir = self.config.msvc_env_for_toolchain['VCToolsRedistDir']
            if self.config.target_arch == Architecture.X86:
                redist_path = Path(vc_tools_redist_dir.get(), 'x86')
            else:
                redist_path = Path(vc_tools_redist_dir.get(), 'x64')
            dlls = redist_path.glob('**/*.dll')
            # FIXME: this needs to go only in the core
            # FIXME
            dest: Path = Path(self.output_dir) / 'gstreamer' / 'bin'
            for dll in dlls:
                shutil.copy(dll, dest)

        # Execute on the chosen output directory
        m.action(f'Building {self._package_name()} in {self.output_dir}')
        python_exe = os.path.join(self.config.build_tools_prefix, 'bin', 'python')
        shell.new_call([python_exe, '-m', 'pip', 'wheel', '.'], cmd_dir=self.output_dir, env=self.config.env)

        # Copy the outputs to the output directory
        paths = list(f.name for f in self.output_dir.glob('*.whl'))
        for p in paths:
            src = self.output_dir / p
            dst = output_dir / p
            m.action(f'Moving {src} to {output_dir}')
            shutil.move(src, dst)

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
