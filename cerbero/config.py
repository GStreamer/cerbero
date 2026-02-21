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
import sys
import copy
import sysconfig
from functools import lru_cache
from pathlib import PurePath, Path

# FIXME: these unused imports are here for backwards compatibility with modules
# that import them cerbero.config instead of cerbero.enums
from cerbero.enums import Architecture, Subsystem, Platform, Distro, DistroVersion, License, LibraryType  # noqa: F401
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import _, system_info, validate_packager, shell
from cerbero.utils import to_unixpath, to_winepath, parse_file, detect_qt5, detect_qt6
from cerbero.utils import merge_str_env, merge_env_value_env
from cerbero.utils import messages as m
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.ide.vs.env import get_vs_year_version


CONFIG_EXT = 'cbc'
USER_CONFIG_DIR = Path('~/.cerbero').expanduser()
USER_CONFIG_FILENAME = 'cerbero.%s' % CONFIG_EXT
USER_CONFIG_FILE = (USER_CONFIG_DIR / USER_CONFIG_FILENAME).as_posix()
DEFAULT_GIT_ROOT = 'https://gitlab.freedesktop.org/gstreamer'
DEFAULT_ALLOW_PARALLEL_BUILD = True
DEFAULT_PACKAGER = 'Default <default@change.me>'
CERBERO_UNINSTALLED = 'CERBERO_UNINSTALLED'
DEFAULT_MIRRORS = ['https://gstreamer.freedesktop.org/src/mirror']
RUST_TRIPLE_MAPPING = {
    (Platform.ANDROID, Architecture.ARM64): 'aarch64-linux-android',
    (Platform.ANDROID, Architecture.ARMv7): 'armv7-linux-androideabi',
    (Platform.ANDROID, Architecture.X86): 'i686-linux-android',
    (Platform.ANDROID, Architecture.X86_64): 'x86_64-linux-android',
    (Platform.LINUX, Architecture.ARM): 'arm-unknown-linux-gnueabi',
    (Platform.LINUX, Architecture.ARMv7): 'armv7-unknown-linux-gnueabihf',
    (Platform.LINUX, Architecture.ARM64): 'aarch64-unknown-linux-gnu',
    (Platform.LINUX, Architecture.X86): 'x86-unknown-linux-gnu',
    (Platform.LINUX, Architecture.X86_64): 'x86_64-unknown-linux-gnu',
    (Platform.DARWIN, Architecture.ARM64): 'aarch64-apple-darwin',
    (Platform.DARWIN, Architecture.X86_64): 'x86_64-apple-darwin',
    (Platform.IOS, Architecture.ARM64, Subsystem.IOS): 'aarch64-apple-ios',
    (Platform.IOS, Architecture.ARM64, Subsystem.IOS_SIMULATOR): 'aarch64-apple-ios-sim',
    (Platform.IOS, Architecture.X86_64, Subsystem.IOS_SIMULATOR): 'x86_64-apple-ios',
    (Platform.TVOS, Architecture.ARM64, Subsystem.TVOS): 'aarch64-apple-tvos',
    (Platform.TVOS, Architecture.ARM64, Subsystem.TVOS_SIMULATOR): 'aarch64-apple-tvos-sim',
    (Platform.TVOS, Architecture.X86_64, Subsystem.TVOS_SIMULATOR): 'x86_64-apple-tvos',
    (Platform.WINDOWS, Architecture.X86_64, 'gnu'): 'x86_64-pc-windows-gnu',
    (Platform.WINDOWS, Architecture.X86_64, 'msvc'): 'x86_64-pc-windows-msvc',
    (Platform.WINDOWS, Architecture.ARM64, 'msvc'): 'aarch64-pc-windows-msvc',
    (Platform.WINDOWS, Architecture.X86, 'gnu'): 'i686-pc-windows-gnu',
    (Platform.WINDOWS, Architecture.X86, 'msvc'): 'i686-pc-windows-msvc',
}


def set_nofile_ulimit():
    """
    Some newer toolchains such as our GCC 8.2 cross toolchain exceed the
    1024 file ulimit, so let's increase it.
    See: https://gitlab.freedesktop.org/gstreamer/cerbero/issues/165
    """
    try:
        import resource
    except ImportError:
        return
    want = 2048
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < want or hard < want:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, want))
        except (OSError, ValueError):
            print('Failed to increase file ulimit, you may see linker failures')


class Variants(object):
    # Variants that are booleans, and are unset when prefixed with 'no'
    __disabled_variants = [
        'x11',
        'alsa',
        'pulse',
        'cdparanoia',
        'v4l2',
        'gi',
        'unwind',
        'rpi',
        'visualstudio',
        'mingw',
        'qt5',
        'intelmsdk',
        'python',
        'werror',
        'va',
        'rust',
        'qt6',
        'gtk',
    ]
    __enabled_variants = ['debug', 'optimization', 'testspackage', 'assert', 'checks']
    __bool_variants = __enabled_variants + __disabled_variants
    # Variants that are `key: (values)`, with the first value in the tuple
    # being the default
    __mapping_variants = {'vscrt': ('auto', 'md', 'mdd')}
    __aliases = {
        'visualstudio': ['nomingw'],
        'mingw': ['novisualstudio'],
    }

    def __init__(self, variants):
        # Keeps a list of variants overriden by the user after initialization
        self.__overridden_variants = set()
        # Set default values
        self.reset()
        self.override(variants)

    def reset(self):
        for v in self.__enabled_variants:
            setattr(self, v, True)
        for v in self.__disabled_variants:
            setattr(self, v, False)
        for v, choices in self.__mapping_variants.items():
            setattr(self, v, choices[0])
        # reset after all inits
        self.__overridden_variants.clear()

    def set_bool(self, key):
        val = True
        if key.startswith('no'):
            key = key[2:]
            val = False
        if key not in self.__bool_variants:
            m.warning('Variant {!r} is unknown or obsolete'.format(key))
        setattr(self, key, val)

    def override(self, variants, force=True):
        """
        Override existing variants using value (str) or values (list) from `variants`.

        If `force` is `False`, do not override those variants that are already overridden
        after the object initialization.
        """

        if not isinstance(variants, list):
            variants = [variants]
        if not force:
            variants = [v for v in variants if not self._is_overridden(v)]

        # Set the configured values
        for v in variants:
            if '=' in v:
                key, value = v.split('=', 1)
                key = key.replace('-', '_')
                if key not in self.__mapping_variants:
                    raise AttributeError('Mapping variant {!r} is unknown'.format(key))
                if value not in self.__mapping_variants[key]:
                    raise AttributeError('Mapping variant {!r} value {!r} is unknown'.format(key, value))
                setattr(self, key, value)
            else:
                self.set_bool(v)
                for alias in self.__aliases.get(v, []):
                    self.set_bool(alias)
        # Auto-set vscrt variant if it wasn't set explicitly
        if self.vscrt == 'auto':
            self.vscrt = 'md'
            if self.debug and not self.optimization:
                self.vscrt = 'mdd'

    def __setattr__(self, attr, value):
        if '-' in attr:
            raise AssertionError("Variant name {!r} must not contain '-'".format(attr))
        super().__setattr__(attr, value)
        if attr in ['_Variants__overridden_variants']:
            return

        self.__overridden_variants.add(attr)

    def __getattr__(self, name):
        if name.startswith('no') and name[2:] in self.bools():
            return not getattr(self, name[2:])
        if name in self.bools() or name in self.mappings():
            return getattr(self, name)
        raise AttributeError('No such variant called {!r}'.format(name))

    def __repr__(self):
        return '<Variants: {}>'.format(self.__dict__)

    def bools(self):
        return sorted(self.__bool_variants)

    def mappings(self):
        return sorted(self.__mapping_variants)

    def _is_overridden(self, variant):
        if not isinstance(variant, str):
            return False
        if variant.startswith('no'):
            real_name = variant[2:]
            if real_name not in self.bools():
                return False
        else:
            real_name = variant
        return real_name in self.__overridden_variants


class Config(object):
    """
    Holds the configuration for the build

    @ivar build_tools_config: Configuration for build tools
    @type build_tools_config: L{cerbero.config.Config}
    @ivar py_prefix: Python purelib prefix eg: lib/pyhton3.8/site-packages
    @type py_prefix: str
    @ivar py_plat_prefix: Python platlib prefix eg: lib64/pyhton3.8/site-packages
    @type py_plat_prefix: str
    @ivar py_win_prefix: Python windows prefix eg: Lib/site-packages
    @type py_win_prefix: str
    @ivar py_prefixes: List of python prefixes
    @type py_prefixes: list
    """

    _properties = [
        'platform',
        'target_platform',
        'target_subsystem',
        'arch',
        'target_arch',
        'prefix',
        'recipes_dir',
        'host',
        'build',
        'target',
        'sources',
        'local_sources',
        'lib_suffix',
        'git_root',
        'distro',
        'target_distro',
        'config_dir',
        'cache_file',
        'toolchain_prefix',
        'toolchain_version',
        'distro_version',
        'target_distro_version',
        'system_recipes_dir',
        'allow_system_recipes',
        'system_recipes_priority',
        'packages_dir',
        'py_prefix',
        'logs',
        'install_dir',
        'allow_parallel_build',
        'allow_universal_parallel_build',
        'num_of_cpus',
        'cargo_build_jobs',
        'use_configure_cache',
        'packages_prefix',
        'packager',
        'data_dir',
        'min_osx_sdk_version',
        'external_recipes',
        'external_packages',
        'use_ccache',
        'force_git_commit',
        'universal_archs',
        'universal_prefix',
        'osx_target_sdk_version',
        'build_tools_prefix',
        'build_tools_sources',
        'build_tools_logs',
        'build_tools_cache',
        'home_dir',
        'recipes_commits',
        'recipes_remotes',
        'ios_platform',
        'tvos_platform',
        'extra_build_tools',
        'override_build_tools',
        'distro_packages_install',
        'interactive',
        'bash_completions',
        'target_arch_flags',
        'sysroot',
        'isysroot',
        'extra_lib_path',
        'cached_sources',
        'tools_prefix',
        'ios_min_version',
        'tvos_min_version',
        'toolchain_path',
        'mingw_perl_prefix',
        'msvc_gl_prefix',
        'msvc_env_for_toolchain',
        'mingw_env_for_toolchain',
        'msvc_env_for_build_system',
        'mingw_env_for_build_system',
        'msvc_version',
        'meson_properties',
        'manifest',
        'extra_properties',
        'qt5_qmake_path',
        'qt5_pkgconfigdir',
        'for_shell',
        'package_tarball_compression',
        'extra_mirrors',
        'extra_bootstrap_packages',
        'override_bootstrap_packages',
        'moltenvk_prefix',
        'vs_install_path',
        'vs_install_version',
        'exe_suffix',
        'rust_prefix',
        'rustup_home',
        'cargo_home',
        'tomllib_path',
        'qt6_qmake_path',
        'system_build_tools',
    ]

    _deprecated_properties = [
        ('environ_dir', 'config_dir'),
    ]

    cookbook = None

    def __init__(self, is_build_tools_config=False):
        self._check_uninstalled()
        self.build_tools_config = None
        self._is_build_tools_config = is_build_tools_config
        self.py_prefixes = []
        self.py_prefix = ''
        self.py_plat_prefix = ''
        self.py_win_prefix = ''

        for a in self._properties:
            setattr(self, a, None)

        self.arch_config = {self.target_arch: self}
        # Starting with Python 3.12, subprocess.py looks at these case-sensitively
        if 'COMSPEC' in os.environ:
            os.environ['ComSpec'] = os.environ['COMSPEC']
        if 'SYSTEMROOT' in os.environ:
            os.environ['SystemRoot'] = os.environ['SYSTEMROOT']
        # Store raw os.environ data
        self._pre_environ = os.environ.copy()
        self.config_env = os.environ.copy()
        # Initialize variants
        self.variants = Variants([])

    def _warn_deprecated_properties(self, config_dict):
        """
        Warn about deprecated properties and map them to new properties.

        Args:
            config_dict: Dict from parsed config file to check for deprecated properties.
        """
        for old_prop, new_prop in self._deprecated_properties:
            if old_prop in config_dict:
                m.deprecation(f'{old_prop} is deprecated, use {new_prop} instead')
                # Map the old property value to the new property in the config dict
                config_dict[new_prop] = config_dict[old_prop]

    def _copy(self, arch):
        c = copy.deepcopy(self)
        c.target_arch = arch
        return c

    def can_use_msvc(self):
        if self.variants.visualstudio and self.msvc_version is not None:
            return True
        return False

    def load(self, filename=None, variants_override=None):
        if variants_override is None:
            variants_override = []

        # Reset variants
        self.variants.reset()
        self.variants.override(variants_override)

        # First load the default configuration
        self.load_defaults()

        # Use Visual Studio by default when building on Windows
        if not self.variants.mingw and not self.variants.visualstudio and self.platform == Platform.WINDOWS:
            self.variants.override(['visualstudio'])

        # Next parse the user configuration file USER_CONFIG_FILE
        # which overrides the defaults
        self._load_user_config()

        # Next, if a config file is provided use it to override the settings
        # again (set the target, f.ex.)
        self._load_cmd_config(filename)

        # Create a copy of the config for each architecture in case we are
        # building Universal binaries
        if self.target_arch == Architecture.UNIVERSAL:
            arch_config = {}

            if isinstance(self.universal_archs, list):
                # Simple list of architectures, just duplicate all the config
                for arch in self.universal_archs:
                    arch_config[arch] = self._copy(arch)
            elif isinstance(self.universal_archs, dict):
                # Map of architectures to the corresponding config file. We
                # do this so that we don't need to duplicate arch specific
                # config again in the universal config.
                for arch, config_file in list(self.universal_archs.items()):
                    arch_config[arch] = self._copy(arch)
                    if config_file is not None:
                        # This works because the override config files are
                        # fairly light. Things break if they are more complex
                        # as load config can have side effects in global state
                        d = os.path.dirname(filename[0])
                        for f in filename:
                            if 'universal' in f:
                                d = os.path.dirname(f)
                        arch_config[arch]._load_cmd_config([Path(d, config_file).as_posix()])
            else:
                raise ConfigurationError('universal_archs must be a list or a dict')

            self.arch_config = arch_config

        # Fill the defaults in the config which depend on the configuration we
        # loaded above
        self._load_last_defaults()
        # Load the platform-specific (linux|windows|android|darwin|ios|tvos).config
        self._load_platform_config()
        # And validate properties
        self._validate_properties()
        self._check_windows_is_x86_64()
        self._init_python_prefixes()

        # The build tools config is required to properly configure the environment
        if not self._is_build_tools_config:
            self._create_build_tools_config()

        for config in list(self.arch_config.values()):
            if self.target_arch == Architecture.UNIVERSAL:
                config.sources = Path(self.sources, config.target_arch).as_posix()
                config.prefix = Path(self.prefix, config.target_arch).as_posix()
                # A universal prefix is only available if arch-prefixes are merged during build
                if 'merged' in self.cross_universal_type():
                    config.universal_prefix = self.prefix
            # qmake_path is different for each arch in android-universal, but
            # not in ios-universal.
            qtpkgdir, qmake5 = detect_qt5(
                config.target_platform, config.target_arch, self.target_arch == Architecture.UNIVERSAL
            )
            config.set_property('qt5_qmake_path', qmake5)
            config.set_property('qt5_pkgconfigdir', qtpkgdir)
            # Qt6
            qmake6 = detect_qt6(config.target_platform, config.target_arch, self.target_arch == Architecture.UNIVERSAL)
            config.set_property('qt6_qmake_path', qmake6)
            # We already called these functions on `self` above
            if config is not self:
                config._load_last_defaults()
                config._load_platform_config()
                config._validate_properties()
                config.build_tools_config = self.build_tools_config
                config._init_python_prefixes()

        # Ensure that variants continue to override all other configuration
        self.variants.override(variants_override)
        if self.variants.gi and not self.gi_supported():
            m.warning(_("gobject introspection requires an executable target, 'gi' variant will be removed"))
            self.variants.gi = False

        for c in list(self.arch_config.values()):
            c.variants = self.variants

        self.do_setup_env()

        if self._is_build_tools_config:
            m.message('Build tools install prefix will be {}'.format(self.prefix))
        else:
            if self.can_use_msvc():
                m.message(
                    'Building recipes with Visual Studio {} whenever possible'.format(
                        get_vs_year_version(self.msvc_version)
                    )
                )
                if self.vs_install_path:
                    m.message('Using Visual Studio installed at {!r}'.format(self.vs_install_path))
            m.message('Install prefix will be {}'.format(self.prefix))
            if self.distro == Distro.MSYS:
                import time

                print('!!!!!!!!!!!!')
                print('DEPRECATION: You are using the old MSYS which is deprecated and will be unsupported SOON!')
                print('!!!!!!!!!!!!')
                for i in range(0, 5):
                    print('.', end='', flush=True)
                    time.sleep(1)
                print('')
                print('!!!!!!!!!!!!')
                print('DEPRECATION: Check the README to migrate to MSYS2 and get faster build times!')
                print('!!!!!!!!!!!!')

        # Store current os.environ data
        arches = []
        if isinstance(self.universal_archs, dict):
            arches = self.arch_config.keys()
        for arch_config in list(self.arch_config.values()):
            arch_config._create_paths()
        if arches:
            m.message('Building the following arches: ' + ' '.join(arches))

        if self.allow_system_recipes and self.target_platform != Platform.LINUX:
            m.message('Force not allow system-recipes because target_platform is not Linux')
            self.allow_system_recipes = False

    def do_setup_env(self):
        self._create_paths()

        self.rel_libdir = 'lib%s' % self.lib_suffix
        libdir = Path(self.prefix, self.rel_libdir).as_posix()
        self.libdir = libdir

        self.env = self.get_env(self.prefix, libdir)

    def get_wine_runtime_env(self, prefix, env):
        """
        When we're creating a cross-winXX shell, these runtime environment
        variables are only useful if the built binaries will be run using Wine,
        so convert them to values that can be understood by programs running
        under Wine.
        """
        runtime_env = (
            'GI_TYPELIB_PATH',
            'XDG_DATA_DIRS',
            'XDG_CONFIG_DIRS',
            'GST_PLUGIN_PATH',
            'GST_PLUGIN_PATH_1_0',
            'GST_REGISTRY',
            'GST_REGISTRY_1_0',
            'MONO_PATH',
            'MONO_GAC_PREFIX',
        )
        for each in runtime_env:
            env[each] = to_winepath(env[each])
        # NOTE: Ensure that whatever directory this goes into is ignored by the
        # .cerbero deps CI job otherwise we will tar up ~1GB of generated data.
        env['WINEPREFIX'] = Path(self.build_tools_prefix, 'var', 'tmp', 'wine').as_posix()
        env['WINEPATH'] = to_winepath(Path(prefix, 'bin').as_posix())
        env['WINEDEBUG'] = 'fixme-all'
        return env

    @lru_cache(maxsize=None)
    def get_env(self, prefix, libdir):
        # Get paths for environment variables
        includedir = Path(prefix, 'include').as_posix()
        bindir = Path(prefix, 'bin').as_posix()
        manpathdir = Path(prefix, 'share', 'man').as_posix()
        infopathdir = Path(prefix, 'share', 'info').as_posix()
        typelibpath = Path(libdir, 'girepository-1.0').as_posix()
        xdgdatadir = Path(prefix, 'share').as_posix()
        xdgconfigdir = Path(prefix, 'etc', 'xdg').as_posix()
        xcursordir = Path(prefix, 'share', 'icons').as_posix()
        aclocalflags = '-I{} -I{}'.format(
            Path(prefix, 'share', 'aclocal').as_posix(), Path(self.build_tools_prefix, 'share', 'aclocal').as_posix()
        )

        perlversionpath = os.path.join(libdir, 'perl5', 'site_perl', self._perl_version())
        if self.target_platform == Platform.WINDOWS:
            # On windows even if perl version is 5.8.8, modules can be
            # installed in 5.8
            perlversionpath = perlversionpath.rsplit('.', 1)[0]

        perl5lib = ':'.join([to_unixpath(Path(libdir, 'perl5').as_posix()), to_unixpath(perlversionpath)])
        gstpluginpath10 = Path(libdir, 'gstreamer-1.0').as_posix()
        gstregistry10 = f'~/.cache/gstreamer-1.0/cerbero-registry-{self.target_arch}'
        gstregistry10 = Path(gstregistry10).expanduser().as_posix()

        pythonpath = []
        for p in (self.prefix, self.build_tools_prefix):
            for pypath in self.py_prefixes:
                # Starting with Python 3.7.1 on Windows, each PYTHONPATH must use the
                # native path separator and must end in a path separator.
                pythonpath += [Path(p, pypath).as_posix() + os.sep]
        pythonpath = os.pathsep.join(pythonpath)

        if self.platform == Platform.LINUX:
            xdgdatadir += ':/usr/share:/usr/local/share'

        ldflags = self.config_env.get('LDFLAGS', '')
        ldflags_libdir = '-L%s ' % libdir
        if ldflags_libdir not in ldflags:
            ldflags = self._join_values(ldflags, ldflags_libdir)

        path = self.config_env.get('PATH', None)
        if not self._is_build_tools_config:
            path = self._join_path(Path(self.build_tools_config.prefix, 'bin').as_posix(), path)
        if self.variants.rust:
            path = self._join_path(Path(self.cargo_home, 'bin').as_posix(), path)
        # Add the prefix bindir after the build-tools bindir so that on Windows
        # binaries are run with the same libraries that they are linked with.
        if bindir not in path and self.prefix_is_executable():
            path = self._join_path(bindir, path)
        ld_library_path = ''
        if not self._is_build_tools_config:
            ld_library_path = Path(self.build_tools_config.libdir).as_posix()
        if self.prefix_is_executable():
            ld_library_path = self._join_path(libdir, ld_library_path)
        if self.extra_lib_path is not None:
            ld_library_path = self._join_path(ld_library_path, self.extra_lib_path)
        if self.toolchain_prefix is not None:
            ld_library_path = self._join_path(ld_library_path, Path(self.toolchain_prefix, 'lib').as_posix())
            includedir = self._join_path(includedir, Path(self.toolchain_prefix, 'include').as_posix())
        if self.lib_suffix and self.variants.python:
            # if there is a lib_suffix and a Python build is present it would sit "next" to the lib_suffix dir rather than in it
            ld_library_path = self._join_path(Path(self.prefix, 'lib').as_posix(), ld_library_path)
        # Most of these variables are extracted from jhbuild
        env = {
            'LD_LIBRARY_PATH': ld_library_path,
            'LDFLAGS': ldflags,
            'PATH': path,
            'MANPATH': manpathdir,
            'INFOPATH': infopathdir,
            'GI_TYPELIB_PATH': typelibpath,
            'XDG_DATA_DIRS': xdgdatadir,
            'XDG_CONFIG_DIRS': xdgconfigdir,
            'XCURSOR_PATH': xcursordir,
            'ACLOCAL_FLAGS': aclocalflags,
            'ACLOCAL': 'aclocal',
            'PERL5LIB': perl5lib,
            'GST_PLUGIN_PATH': gstpluginpath10,
            'GST_PLUGIN_PATH_1_0': gstpluginpath10,
            'GST_REGISTRY': gstregistry10,
            'GST_REGISTRY_1_0': gstregistry10,
            'PYTHONPATH': pythonpath,
            'MONO_PATH': Path(libdir, 'mono', '4.5').as_posix(),
            'MONO_GAC_PREFIX': prefix,
            'GSTREAMER_ROOT': prefix,
            'CERBERO_PREFIX': self.prefix,
            'CERBERO_HOST_SOURCES': self.sources,
            'RUSTUP_HOME': self.rustup_home,
            'CARGO_HOME': self.cargo_home,
        }

        PkgConfig.set_executable(env, self)
        PkgConfig.set_default_search_dir(Path(prefix, 'share', 'pkgconfig').as_posix(), env, self)
        PkgConfig.add_search_dir(Path(libdir, 'pkgconfig').as_posix(), env, self)
        PkgConfig.add_search_dir(self.get_custom_pkg_config_path(), env, self)

        # Some autotools recipes will call the native (non-cross) compiler to
        # build generators, and we don't want it to use these. We will set the
        # include paths using CFLAGS, etc, when cross-compiling.
        if not self.cross_compiling():
            env['C_INCLUDE_PATH'] = includedir
            env['CPLUS_INCLUDE_PATH'] = includedir

        # merge the config env with this new env
        # LDFLAGS and PATH were already merged above
        new_env = merge_str_env(self.config_env, env, override_env=('LDFLAGS', 'PATH'))

        if self.target_platform == Platform.WINDOWS and self.platform != Platform.WINDOWS:
            new_env = self.get_wine_runtime_env(prefix, new_env)

        return new_env

    def load_defaults(self):
        self.set_property('cache_file', None)
        self.set_property('home_dir', self._default_home_dir())
        self.set_property('prefix', None)
        self.set_property('sources', None)
        self.set_property('local_sources', None)
        self.set_property('git_root', DEFAULT_GIT_ROOT)
        self.set_property('allow_parallel_build', DEFAULT_ALLOW_PARALLEL_BUILD)
        self.set_property('allow_universal_parallel_build', DEFAULT_ALLOW_PARALLEL_BUILD)
        self.set_property('host', None)
        self.set_property('build', None)
        self.set_property('target', None)
        platform, subsystem, arch, distro, distro_version, num_of_cpus = system_info()
        target_distro = distro
        # In Windows we do not differenciate between MSYS and MSYS2 for the target_distro
        if platform == Platform.WINDOWS:
            target_distro = Distro.WINDOWS
        self.set_property('platform', platform)
        self.set_property('num_of_cpus', num_of_cpus)
        self.set_property('cargo_build_jobs', None)
        self.set_property('target_platform', platform)
        self.set_property('target_subsystem', subsystem)
        self.set_property('arch', arch)
        self.set_property('target_arch', arch)
        self.set_property('distro', distro)
        self.set_property('target_distro', target_distro)
        self.set_property('distro_version', distro_version)
        self.set_property('target_distro_version', distro_version)
        self.set_property('packages_prefix', None)
        self.set_property('packager', DEFAULT_PACKAGER)
        self.set_property('package_tarball_compression', 'xz')
        stdlibpath = sysconfig.get_path('stdlib', vars={'installed_base': ''})[1:]
        # Ensure that the path uses / as path separator and not \
        self.set_property('py_prefix', PurePath(stdlibpath).as_posix())
        self.set_property('lib_suffix', '')
        self.set_property('exe_suffix', self._get_exe_suffix())
        self.set_property('data_dir', self._find_data_dir())
        self.set_property('cached_sources', self._relative_path('sources'))
        self.set_property('config_dir', self._relative_path('config'))
        self.set_property('recipes_dir', self._relative_path('recipes'))
        self.set_property('system_recipes_dir', self._relative_path('system-recipes'))
        self.set_property('allow_system_recipes', platform == Platform.LINUX)
        self.set_property('system_recipes_priority', 1)
        self.set_property('packages_dir', self._relative_path('packages'))
        self.set_property('use_configure_cache', False)
        self.set_property('external_recipes', {})
        self.set_property('external_packages', {})
        self.set_property('universal_archs', None)
        self.set_property('build_tools_prefix', None)
        self.set_property('build_tools_sources', None)
        self.set_property('build_tools_cache', None)
        # Build tools that are provided by the system (cmake, ninja, etc)
        self.set_property('system_build_tools', [])
        self.set_property('recipes_commits', {})
        self.set_property('recipes_remotes', {})
        self.set_property('extra_build_tools', [])
        self.set_property('override_build_tools', [])
        self.set_property('distro_packages_install', True)
        self.set_property('interactive', m.console_is_interactive())
        self.set_property('meson_properties', {})
        self.set_property('manifest', None)
        self.set_property('extra_properties', {})
        self.set_property('extra_mirrors', [])
        self.set_property('extra_bootstrap_packages', {})
        self.set_property('override_bootstrap_packages', {})
        self.set_property('bash_completions', set())
        # Increase open-files limits
        set_nofile_ulimit()

    def set_property(self, name, value, force=False):
        if name not in self._properties:
            raise ConfigurationError('Unknown key %s' % name)
        if force or getattr(self, name) is None:
            setattr(self, name, value)

    def get_recipes_repos(self):
        recipes_dir = {}
        if self.allow_system_recipes:
            # Setting first system recipes to be loaded first if same priority
            recipes_dir['system'] = (self.system_recipes_dir, self.system_recipes_priority)
        recipes_dir['default'] = (self.recipes_dir, 0)
        for name, (path, priority) in self.external_recipes.items():
            path = Path(os.path.abspath(os.path.expanduser(path))).as_posix()
            recipes_dir[name] = (path, priority)
        return recipes_dir

    def get_packages_repos(self):
        packages_dir = {'default': (self.packages_dir, 0)}
        for name, (path, priority) in self.external_packages.items():
            path = Path(os.path.abspath(os.path.expanduser(path))).as_posix()
            packages_dir[name] = (path, priority)
        return packages_dir

    def recipe_commit(self, recipe_name):
        if self.force_git_commit:
            return self.force_git_commit
        if recipe_name in self.recipes_commits:
            return self.recipes_commits[recipe_name]
        return None

    def cross_compiling(self):
        "Are we building for the host platform or not?"
        # On Windows, building 32-bit on 64-bit is not cross-compilation since
        # 32-bit Windows binaries run on 64-bit Windows via WOW64.
        if self.platform == Platform.WINDOWS:
            if self.arch == Architecture.X86_64 and self.target_arch == Architecture.X86:
                return False
        return (
            self.target_platform != self.platform
            or self.target_arch != self.arch
            or self.target_distro_version != self.distro_version
        )

    def cross_universal_type(self):
        if not self.cross_compiling():
            return None
        if self.target_arch != Architecture.UNIVERSAL and not self.universal_archs:
            return None
        # cross-macos-universal, cross-ios-universal, cross-ios-sim-universal:
        # each arch prefix is merged and flattened into one prefix
        if Platform.is_apple(self.target_platform):

            def subsystem_kind(cf):
                # XXX: Ideally we should look at target_subsystem defined in
                # the file, but that is only known to the parent universal
                # config, not the sub-arch inside. So we use the filename.
                return 'simulator' if '-sim-' in cf else 'device'

            # Detect whether the universal prefix is heterogenous. At the time
            # of writing, only cross-ios-universal met this description: it
            # ships iOS ARM64 and iOS Simulator x86_64.
            subsystem = None
            for arch, config_file in self.universal_archs.items():
                if subsystem is None:
                    subsystem = subsystem_kind(config_file)
                    continue
                if subsystem != subsystem_kind(config_file):
                    return 'merged-hetero'
            return 'merged-homo'
        return 'split'

    def is_automatically_symbolicable(self):
        """
        Can symbols be generated just by strip+objcopy?
        """
        if Platform.is_apple(self.target_platform):
            return False
        if self.variants.visualstudio:
            return False
        return True

    def prefix_is_executable(self):
        """Can the binaries from the target platform can be executed in the
        build env?"""
        if self.target_platform != self.platform:
            return False
        if self.target_arch != self.arch:
            if self.target_arch == Architecture.X86 and self.arch == Architecture.X86_64:
                return True
            if self.target_platform == Platform.DARWIN and self.target_arch == Architecture.X86_64:
                return True
            if self.target_arch == Architecture.UNIVERSAL and 'merged' in self.cross_universal_type():
                return True
            return False
        return True

    def gi_supported(self):
        if not self.prefix_is_executable():
            return False
        # When building cross-macos-universal, the merged prefix is executable
        # on both arm64 and x86_64, but introspection runs executables before
        # merging, so we only support it when running on arm64, where we have
        # Rosetta available.
        if (
            self.target_platform == Platform.DARWIN
            and self.target_arch == Architecture.UNIVERSAL
            and self.arch != Architecture.ARM64
        ):
            return False
        return True

    def prefix_is_build_tools(self):
        return self._is_build_tools_config

    def target_distro_version_gte(self, distro_version):
        assert distro_version.startswith(self.target_distro + '_')
        return self.target_distro_version >= distro_version

    def _create_paths(self):
        if self.toolchain_prefix:
            self._create_path(self.toolchain_prefix)
        self._create_path(self.prefix)
        self._create_path(self.sources)
        self._create_path(self.logs)
        # dict universal arches do not have an active prefix
        if not isinstance(self.universal_archs, dict):
            self._create_path(Path(self.prefix, 'share', 'aclocal').as_posix())

        if self._is_build_tools_config:
            self._create_path(Path(self.prefix, 'var', 'tmp').as_posix())

    def _create_build_tools_config(self):
        # Use a common prefix for the build tools for all the configurations
        # so that it can be reused
        self.build_tools_config = Config(is_build_tools_config=True)
        self.build_tools_config.prefix = self.build_tools_prefix
        self.build_tools_config.home_dir = self.home_dir
        self.build_tools_config.local_sources = self.local_sources
        # We want build tools to use the VS specified by the user manually
        self.build_tools_config.vs_install_path = self.vs_install_path
        self.build_tools_config.vs_install_version = self.vs_install_version
        self.build_tools_config.load()

        self.build_tools_config.prefix = self.build_tools_prefix
        self.build_tools_config.build_tools_prefix = self.build_tools_prefix
        self.build_tools_config.sources = self.build_tools_sources
        self.build_tools_config.build_tools_sources = self.build_tools_sources
        self.build_tools_config.logs = self.build_tools_logs
        self.build_tools_config.build_tools_logs = self.build_tools_logs
        self.build_tools_config.cache_file = self.build_tools_cache
        self.build_tools_config.build_tools_cache = self.build_tools_cache
        self.build_tools_config.system_build_tools = self.system_build_tools
        self.build_tools_config.external_recipes = self.external_recipes
        self.build_tools_config.recipes_remotes = self.recipes_remotes
        self.build_tools_config.recipes_commits = self.recipes_commits
        self.build_tools_config.extra_mirrors = self.extra_mirrors
        self.build_tools_config.cached_sources = self.cached_sources
        self.build_tools_config.vs_install_path = self.vs_install_path
        self.build_tools_config.vs_install_version = self.vs_install_version
        self.build_tools_config.cargo_build_jobs = self.cargo_build_jobs
        self.build_tools_config.num_of_cpus = self.num_of_cpus

        self.build_tools_config.do_setup_env()

    def _init_python_prefixes(self):
        # Explicitly use the posix_prefix scheme because:
        # 1. On Windows, pypath doesn't include Python version although some
        #    packages (pycairo, gi, etc...) install themselves using Python
        #    version scheme like on a posix system.
        # 2. The Python3 that ships with XCode on macOS Big Sur defaults to
        #    a framework path, but setuptools defaults to a posix prefix
        # So just use a posix prefix everywhere consistently.
        pyvars = {'base': '.', 'platbase': '.'}
        self.py_prefix = sysconfig.get_path('purelib', 'posix_prefix', vars=pyvars)
        self.py_plat_prefix = sysconfig.get_path('platlib', 'posix_prefix', vars=pyvars)
        # Make sure we also include the default non-versioned path on
        # Windows in addition to the posix path.
        self.py_win_prefix = sysconfig.get_path('purelib', 'nt', vars=pyvars)
        # And the system prefix for Xcode Python
        # (making it relative as it's appended to the Cerbero root folder)
        self.py_macos_prefix = os.path.splitdrive(sysconfig.get_path('purelib'))[1].lstrip('/')

        self.py_prefixes = [self.py_prefix, self.py_plat_prefix]
        if self.platform == Platform.WINDOWS:
            self.py_prefixes.append(self.py_win_prefix)
        self.py_prefixes = list(set(self.py_prefixes))

        if self.platform == Platform.WINDOWS:
            # pythonpaths start with 'Lib' on Windows, which is extremely
            # undesirable since our libdir is 'lib'. Windows APIs are
            # case-preserving case-insensitive.
            # Running this fix first is necessary because otherwise the WiX
            # logic will enumerate lib/ first, and then Lib/ for the Python
            # package, thus double defining the same artifact folder.
            self.py_prefixes = [path.lower() for path in self.py_prefixes]

        # Ensure python paths exists because setup.py won't create them
        for path in self.py_prefixes:
            path = Path(self.prefix, path).as_posix()
            # dict universal arches do not have an active prefix
            if not isinstance(self.universal_archs, dict):
                self._create_path(path)

    def _parse(self, filename, reset=True):
        config = {
            'os': os,
            '__file__': filename,
            'env': self.config_env,
            'cross': self.cross_compiling(),
            'variants': self.variants,
        }
        if not reset:
            for prop in self._properties:
                if hasattr(self, prop):
                    config[prop] = getattr(self, prop)

        try:
            parse_file(filename, config)
        except Exception:
            raise ConfigurationError(_('Could not include config file (%s)') % filename)

        # Handle deprecated properties from config file first
        self._warn_deprecated_properties(config)

        for key in self._properties:
            if key in config:
                self.set_property(key, config[key], True)

    def _validate_properties(self):
        if not validate_packager(self.packager):
            raise FatalError(_('packager "%s" must be in the format ' '"Name <email>"') % self.packager)

    def _check_windows_is_x86_64(self):
        if self.target_platform == Platform.WINDOWS and self.arch == Architecture.X86:
            raise ConfigurationError('The GCC/MinGW toolchain requires an x86 64-bit OS.')

    def _check_uninstalled(self):
        self.uninstalled = int(os.environ.get(CERBERO_UNINSTALLED, 0)) == 1

    def _create_path(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception:
                raise FatalError(_('directory (%s) can not be created') % path)

    def _join_values(self, value1, value2, sep=' '):
        # Ensure there's no leading or trailing whitespace
        if len(value1) == 0:
            return value2
        if len(value2) == 0:
            return value1
        return '{}{}{}'.format(value1, sep, value2)

    def _join_path(self, path1, path2):
        return self._join_values(path1, path2, os.pathsep)

    def _load_user_config(self):
        if os.path.exists(USER_CONFIG_FILE):
            if not self._is_build_tools_config:
                m.message('Loading default configuration from {}'.format(USER_CONFIG_FILE))
            self._parse(USER_CONFIG_FILE)

    def _load_cmd_config(self, filenames):
        if filenames is not None:
            for f in filenames:
                # Check if the config specified is a complete path, else search
                # in the user config directory and then in the config_dir (cerbero_share/config/)
                uf = (USER_CONFIG_DIR / (f + '.' + CONFIG_EXT)).as_posix()
                ef = Path(self.config_dir, f if f.endswith('.' + CONFIG_EXT) else f + '.' + CONFIG_EXT).as_posix()
                for config_file in [f, uf, ef]:
                    if os.path.exists(config_file):
                        self._parse(config_file, reset=False)
                        break
                else:
                    raise ConfigurationError(_('Configuration file %s or fallbacks %s, %s not found') % (f, uf, ef))

    def _load_platform_config(self):
        platform_config = Path(self.config_dir, f'{self.target_platform}.config').as_posix()
        arch_config = Path(self.config_dir, f'{self.target_platform}_{self.target_arch}.config').as_posix()

        for config_path in [platform_config, arch_config]:
            if os.path.exists(config_path):
                self._parse(config_path, reset=False)

    def _get_toolchain_target_platform_arch(self, readable=False):
        mingw = 'MinGW' if readable else 'mingw'
        msvc = 'MSVC' if readable else 'msvc'
        debug = ' Debug' if readable else '-debug'

        target_platform = self.target_platform
        # When targeting Apple mobile platform with a subsystem
        if Platform.is_apple_app_platform(self.target_platform):
            target_platform = self.target_subsystem
        # When building with Visual Studio, we can target (MSVC, UWP) x (debug, release)
        elif self.target_platform == Platform.WINDOWS:
            if self.variants.visualstudio:
                # Check for invalid configuration of a custom Visual Studio path
                if self.vs_install_path and not self.vs_install_version:
                    raise ConfigurationError('vs_install_path was set, but vs_install_version was not')
                target_platform = msvc

                # Debug CRT needs a separate prefix
                if self.variants.vscrt == 'mdd':
                    target_platform += debug
            else:
                target_platform = mingw

        return (target_platform, self.target_arch)

    def _load_last_defaults(self):
        # Set build tools defaults
        self.set_property('build_tools_prefix', Path(self.home_dir, 'build-tools').as_posix())
        self.set_property('build_tools_sources', Path(self.home_dir, 'sources', 'build-tools').as_posix())
        self.set_property('build_tools_logs', Path(self.home_dir, 'logs', 'build-tools').as_posix())
        self.set_property('build_tools_cache', 'build-tools.cache')
        # Set target platform defaults
        platform_arch = '_'.join(self._get_toolchain_target_platform_arch())
        self.set_property('prefix', Path(self.home_dir, 'dist', platform_arch).as_posix())
        self.set_property('sources', Path(self.home_dir, 'sources', platform_arch).as_posix())
        self.set_property('logs', Path(self.home_dir, 'logs', platform_arch).as_posix())
        self.set_property('cache_file', platform_arch + '.cache')
        self.set_property('install_dir', self.prefix)
        self.set_property('local_sources', self._default_local_sources_dir())
        self.set_property('rust_prefix', Path(self.home_dir, 'rust').as_posix())
        self.set_property('rustup_home', Path(self.rust_prefix, 'rustup').as_posix())
        self.set_property('cargo_home', Path(self.rust_prefix, 'cargo').as_posix())
        self.set_property('tomllib_path', Path(self.rust_prefix, 'tomllib').as_posix())
        if sys.version_info >= (3, 11, 0):
            self.python_exe = Path(self.build_tools_prefix, 'bin', 'python').as_posix()
        else:
            self.python_exe = Path(sys.executable).as_posix()
        if (
            self.platform == Platform.DARWIN
            and self.arch == Architecture.ARM64
            and self.target_arch == Architecture.X86_64
        ):
            # Created by the build-tools bootstrapper
            self.python_exe = Path(self.build_tools_prefix, 'bin', 'python3-x86_64').as_posix()

    def _get_exe_suffix(self):
        if self.platform != Platform.WINDOWS:
            return ''
        return '.exe'

    def _find_data_dir(self):
        """
        Find the directory containing cerbero's data files (recipes, packages, config, data).

        Handles two installation scenarios:
        1. Uninstalled (running from git checkout): data/ is sibling to cerbero/ package
        2. Pip install: data files are in site-packages/cerbero_share/data/
        """
        if self.uninstalled:
            # Running from git checkout - data is ../data relative to this file
            self.data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
            self.data_dir = Path(os.path.abspath(self.data_dir)).as_posix()
            return

        curdir = os.path.dirname(__file__)
        # Check if data files are in cerbero_share package (pip install)
        # In this case, recipes/, packages/, config/, data/ are inside cerbero_share/
        parent_dir = Path(os.path.abspath(os.path.join(curdir, '..'))).as_posix()
        cerbero_share_dir = Path(parent_dir, 'cerbero_share').as_posix()
        if (
            os.path.exists(Path(cerbero_share_dir, 'config').as_posix())
            and os.path.exists(Path(cerbero_share_dir, 'recipes').as_posix())
            and os.path.exists(Path(cerbero_share_dir, 'data').as_posix())
        ):
            # Data directory points to cerbero_share/data/ for pip installs
            self.data_dir = Path(cerbero_share_dir, 'data').as_posix()
            return

        # If we get here, something is wrong
        raise FatalError('Data dir not found. Cerbero must be run from git checkout or installed via pip.')

    def _relative_path(self, path):
        if not self.uninstalled:
            # For pip installs, use cerbero_share as base (parent of data_dir)
            # data_dir is cerbero_share/data, so we go up one level to get cerbero_share
            cerbero_share = os.path.dirname(self.data_dir)
            p = os.path.join(cerbero_share, path)
        else:
            p = os.path.join(os.path.dirname(__file__), '..', path)
        return Path(os.path.abspath(p)).as_posix()

    def _default_home_dir(self):
        if self.uninstalled:
            p = os.path.join(os.path.dirname(__file__), '..', 'build')
        else:
            p = os.path.expanduser('~/cerbero')
        return Path(os.path.abspath(p)).as_posix()

    def _default_local_sources_dir(self):
        # For backwards-compatibility, keep the old value for setups that
        # define their own home_dir inside which all cerbero work must be
        # contained; f.ex. ci.gstreamer.net
        if self.home_dir != self._default_home_dir():
            return Path(self.home_dir, 'sources', 'local').as_posix()
        # Default value should be in a user-specific location so that it can
        # be shared across all cerbero directories and invocations
        if self.platform == Platform.WINDOWS and 'USERPROFILE' in os.environ:
            cache_dir = Path(os.environ['USERPROFILE']) / '.cache'
        elif 'XDG_CACHE_HOME' in os.environ:
            cache_dir = Path(os.environ['XDG_CACHE_HOME'])
        else:
            # Path.home() reads the HOME env var
            cache_dir = Path.home() / '.cache'
        return (cache_dir / 'cerbero-sources').as_posix()

    @lru_cache()
    def _perl_version(self):
        try:
            version = shell.check_output('perl -e \'print "$]";\'')
        except FatalError:
            m.warning(_('Perl not found, you may need to run bootstrap.'))
            version = '0.000000'
        # FIXME: when perl's mayor is >= 10
        mayor = str(version[0])
        minor = str(int(version[2:5]))
        revision = str(int(version[5:8]))
        return '.'.join([mayor, minor, revision])

    @staticmethod
    def rust_triple(arch, platform, subsystem, vs):
        if platform == Platform.WINDOWS:
            if vs:
                key = (Platform.WINDOWS, arch, 'msvc')
            else:
                key = (Platform.WINDOWS, arch, 'gnu')
        elif Platform.is_apple_app_platform(platform):
            key = (platform, arch, subsystem)
        else:
            key = (platform, arch)
        if key in RUST_TRIPLE_MAPPING:
            return RUST_TRIPLE_MAPPING[key]
        else:
            raise FatalError(
                f'Unsupported build platform/arch combination: {platform}/{arch}, subsystem: {subsystem}, vs: {vs}'
            )

    @property
    def rust_build_triple(self):
        return self.rust_triple(self.arch, self.platform, None, self.variants.visualstudio)

    @property
    def rust_target_triples(self):
        if self.target_arch != Architecture.UNIVERSAL:
            targets = {self.target_arch: self}
        else:
            targets = self.arch_config
        triples = []
        for target_arch, c in targets.items():
            triple = self.rust_triple(target_arch, c.target_platform, c.target_subsystem, c.variants.visualstudio)
            triples.append(triple)
        return triples

    def find_toml_module(self, system_only=False):
        import importlib

        if sys.version_info >= (3, 11, 0):
            return importlib.import_module('tomllib')
        for mod in ('tomli', 'toml', 'tomlkit'):
            try:
                return importlib.import_module(mod)
            except ModuleNotFoundError:
                continue
        if not system_only and os.path.exists(self.tomllib_path):
            tomli_dir = Path(self.tomllib_path, 'src').as_posix()
            sys.path.insert(0, os.path.abspath(tomli_dir))
            return importlib.import_module('tomli')
        return None

    def get_build_env(self, in_env=None, using_msvc=False):
        """
        Override/merge toolchain env with `in_env` and return a new dict
        with values as EnvValue objects
        if `in_env` is empty, `self.env` is used.
        """

        # Extract toolchain config for the build system from the appropriate
        # config env dict. Start with `in_env`, since it contains toolchain
        # config set by the recipe and when building for target platforms other
        # than Windows, it also contains build tools and the env for the
        # toolchain set by config/*.config.
        #
        # On Windows, the toolchain config is `msvc_env_for_build_system`
        # or `mingw_env_for_build_system` depending on which toolchain
        # this recipe will use.
        if self.target_platform == Platform.WINDOWS:
            if using_msvc:
                build_env = dict(self.msvc_env_for_build_system)
            else:
                build_env = dict(self.mingw_env_for_build_system)
        else:
            build_env = {}

        return merge_env_value_env(build_env, in_env or self.env)

    # config helpers for recipes with Python dependencies:

    def get_python_ext_suffix(self):
        return sysconfig.get_config_vars().get('EXT_SUFFIX', '%(pext)s')

    def get_python_framework(self):
        """
        Get framework prefix for RPATH
        """
        return sysconfig.get_config_vars().get('PYTHONFRAMEWORKPREFIX', None)

    def get_python_version(self):
        return self.extra_properties.get('python_version', sysconfig.get_python_version())

    def get_python_name(self):
        return f'python{self.get_python_version()}'

    def get_build_python_exe(self):
        py_name = self.get_python_name()
        path = self._get_build_python_path('scripts', py_name)
        if path:
            return path.joinpath(py_name)
        return self.python_exe

    def get_python_prefix(self):
        if self.target_platform == Platform.WINDOWS:
            return Path(self.py_win_prefix)
        else:
            return Path(self.py_plat_prefix)

    def _get_build_python_path(self, path_name, testfile):
        py_version = self.get_python_version()
        py_name = f'python{py_version}'
        if path_name == 'scripts':
            glue = 'bin'
        elif path_name in ['include', 'platinclude']:
            glue = Path('include', py_name)
        else:
            glue = Path('lib', py_name)
        if Path(self.prefix, glue, testfile).exists():
            return Path(self.prefix, glue)
        return None

    def get_custom_pkg_config_path(self):
        return Path(self.libdir, 'system_pkgconfig').as_posix()
