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
import itertools
from functools import lru_cache
from pathlib import PurePath, Path

from cerbero.enums import Architecture, Platform, Distro, DistroVersion, License, LibraryType
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import _, system_info, validate_packager, shell
from cerbero.utils import to_unixpath, to_winepath, parse_file, detect_qt5, detect_qt6
from cerbero.utils import EnvVar, EnvValue
from cerbero.utils import messages as m
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.ide.vs.env import get_vs_year_version


CONFIG_EXT = 'cbc'
USER_CONFIG_DIR = os.path.expanduser('~/.cerbero')
USER_CONFIG_FILENAME = 'cerbero.%s' % CONFIG_EXT
USER_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, USER_CONFIG_FILENAME)
DEFAULT_GIT_ROOT = 'https://gitlab.freedesktop.org/gstreamer'
DEFAULT_ALLOW_PARALLEL_BUILD = True
DEFAULT_PACKAGER = "Default <default@change.me>"
CERBERO_UNINSTALLED = 'CERBERO_UNINSTALLED'
DEFAULT_MIRRORS = ['https://gstreamer.freedesktop.org/src/mirror/']
RUST_TRIPLE_MAPPING = {
    (Platform.ANDROID, Architecture.ARM64): 'aarch64-linux-android',
    (Platform.ANDROID, Architecture.ARMv7): 'armv7-linux-androideabi',
    (Platform.ANDROID, Architecture.X86): 'i686-linux-android',
    (Platform.ANDROID, Architecture.X86_64): 'x86_64-linux-android',
    (Platform.LINUX, Architecture.ARM): 'arm-unknown-linux-gnueabi',
    (Platform.LINUX, Architecture.ARMv7): 'armv7-unknown-linux-gnueabihf',
    (Platform.LINUX, Architecture.ARM64): 'aarch64-unknown-linux-gnu',
    (Platform.LINUX, Architecture.X86_64): 'x86_64-unknown-linux-gnu',
    (Platform.DARWIN, Architecture.ARM64): 'aarch64-apple-darwin',
    (Platform.DARWIN, Architecture.X86_64): 'x86_64-apple-darwin',
    (Platform.IOS, Architecture.ARM64): 'aarch64-apple-ios',
    (Platform.IOS, Architecture.X86_64): 'x86_64-apple-ios',
    (Platform.WINDOWS, Architecture.X86_64, 'gnu'): 'x86_64-pc-windows-gnu',
    (Platform.WINDOWS, Architecture.X86_64, 'msvc'): 'x86_64-pc-windows-msvc',
    (Platform.WINDOWS, Architecture.X86, 'gnu'): 'i686-pc-windows-gnu',
    (Platform.WINDOWS, Architecture.X86, 'msvc'): 'i686-pc-windows-msvc',
}


def set_nofile_ulimit():
    '''
    Some newer toolchains such as our GCC 8.2 cross toolchain exceed the
    1024 file ulimit, so let's increase it.
    See: https://gitlab.freedesktop.org/gstreamer/cerbero/issues/165
    '''
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
    __disabled_variants = ['x11', 'alsa', 'pulse', 'jack', 'cdparanoia', 'v4l2',
                           'gi', 'unwind', 'rpi', 'visualstudio', 'mingw', 'uwp', 'qt5',
                           'intelmsdk', 'python', 'werror', 'vaapi', 'rust', 'qt6']
    __enabled_variants = ['debug', 'optimization', 'testspackage']
    __bool_variants = __enabled_variants + __disabled_variants
    # Variants that are `key: (values)`, with the first value in the tuple
    # being the default
    __mapping_variants = {'vscrt': ('auto', 'md', 'mdd')}
    __aliases = {
        'visualstudio': ['nomingw'],
        'mingw': ['novisualstudio'],
    }

    def __init__(self, variants):
        # Set default values
        for v in self.__enabled_variants:
            setattr(self, v, True)
        for v in self.__disabled_variants:
            setattr(self, v, False)
        for v, choices in self.__mapping_variants.items():
            setattr(self, v, choices[0])
        self.override(variants)

    def set_bool(self, key):
        if key.startswith('no'):
            key = key[2:]
            if key not in self.__bool_variants:
                m.warning('Variant {!r} is unknown or obsolete'.format(key))
            setattr(self, key, False)
        else:
            if key not in self.__bool_variants:
                m.warning('Variant {!r} is unknown or obsolete'.format(key))
            setattr(self, key, True)

    def override(self, variants):
        if not isinstance(variants, list):
            variants = [variants]
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
                raise AssertionError('Variant name {!r} must not contain \'-\''.format(attr))
            super().__setattr__(attr, value)
            # UWP implies Visual Studio
            if attr == 'uwp' and value:
                self.visualstudio = True
                self.mingw = False

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


class Config (object):
    '''
    Holds the configuration for the build

    @ivar build_tools_config: Configuration for build tools
    @type build_tools_config: L{cerbero.config.Config}
    '''

    _properties = ['platform', 'target_platform', 'arch', 'target_arch',
                   'prefix', 'recipes_dir', 'host', 'build', 'target',
                   'sources', 'local_sources', 'lib_suffix', 'git_root',
                   'distro', 'target_distro', 'environ_dir', 'cache_file',
                   'toolchain_prefix', 'toolchain_version', 'distro_version',
                   'target_distro_version', 'allow_system_libs',
                   'packages_dir', 'py_prefix', 'logs',
                   'install_dir', 'allow_parallel_build', 'num_of_cpus',
                   'use_configure_cache', 'packages_prefix', 'packager',
                   'data_dir', 'min_osx_sdk_version', 'external_recipes',
                   'external_packages', 'use_ccache', 'force_git_commit',
                   'universal_archs', 'osx_target_sdk_version', 'variants',
                   'build_tools_prefix', 'build_tools_sources', 'build_tools_logs',
                   'build_tools_cache', 'home_dir', 'recipes_commits',
                   'recipes_remotes', 'ios_platform', 'extra_build_tools',
                   'distro_packages_install', 'interactive', 'bash_completions',
                   'target_arch_flags', 'sysroot', 'isysroot',
                   'extra_lib_path', 'cached_sources', 'tools_prefix',
                   'ios_min_version', 'toolchain_path', 'mingw_perl_prefix',
                   'msvc_env_for_toolchain', 'mingw_env_for_toolchain',
                   'msvc_env_for_build_system', 'mingw_env_for_build_system',
                   'msvc_version', 'meson_properties', 'manifest',
                   'extra_properties', 'qt5_qmake_path', 'qt5_pkgconfigdir',
                   'for_shell', 'package_tarball_compression', 'extra_mirrors',
                   'extra_bootstrap_packages', 'moltenvk_prefix',
                   'vs_install_path', 'vs_install_version', 'exe_suffix',
                   'rust_prefix', 'rustup_home', 'cargo_home', 'tomllib_path',
                   'qt6_qmake_path', 'system_build_tools']

    cookbook = None

    def __init__(self, is_build_tools_config=False):
        self._check_uninstalled()
        self.build_tools_config = None
        self._is_build_tools_config = is_build_tools_config

        for a in self._properties:
            setattr(self, a, None)

        self.arch_config = {self.target_arch: self}
        # Store raw os.environ data
        self._pre_environ = os.environ.copy()
        self.config_env = os.environ.copy()

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

        # Initialize variants
        self.variants = Variants(variants_override)

        # First load the default configuration
        self.load_defaults()

        # Use Visual Studio by default when building on Windows
        if not self.variants.mingw and not self.variants.visualstudio:
            if self.platform == Platform.WINDOWS:
                self.variants.override(['visualstudio'])
            else:
                self.variants.override(['mingw'])

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
                        arch_config[arch]._load_cmd_config([os.path.join(d, config_file)])
            else:
                raise ConfigurationError('universal_archs must be a list or a dict')

            self.arch_config = arch_config

        # Fill the defaults in the config which depend on the configuration we
        # loaded above
        self._load_last_defaults()
        # Load the platform-specific (linux|windows|android|darwin).config
        self._load_platform_config()
        # And validate properties
        self._validate_properties()
        self._check_windows_is_x86_64()

        # The build tools config is required to properly configure the environment
        if not self._is_build_tools_config:
            self._create_build_tools_config()

        for config in list(self.arch_config.values()):
            if self.target_arch == Architecture.UNIVERSAL:
                config.sources = os.path.join(self.sources, config.target_arch)
                config.prefix = os.path.join(self.prefix)
            # qmake_path is different for each arch in android-universal, but
            # not in ios-universal.
            qtpkgdir, qmake5 = detect_qt5(config.target_platform, config.target_arch,
                                          self.target_arch == Architecture.UNIVERSAL)
            config.set_property('qt5_qmake_path', qmake5)
            config.set_property('qt5_pkgconfigdir', qtpkgdir)
            # Qt6
            qmake6 = detect_qt6(config.target_platform, config.target_arch,
                                          self.target_arch == Architecture.UNIVERSAL)
            config.set_property('qt6_qmake_path', qmake6)
            # We already called these functions on `self` above
            if config is not self:
                config._load_last_defaults()
                config._load_platform_config()
                config._validate_properties()
                config.build_tools_config = self.build_tools_config

        # Ensure that variants continue to override all other configuration
        self.variants.override(variants_override)
        if not self.prefix_is_executable() and self.variants.gi:
            m.warning(_("gobject introspection requires an executable "
                        "prefix, 'gi' variant will be removed"))
            self.variants.gi = False

        for c in list(self.arch_config.values()):
            c.variants = self.variants

        self.do_setup_env()

        if self.can_use_msvc():
            m.message('Building recipes with Visual Studio {} whenever possible'
                      .format(get_vs_year_version(self.msvc_version)))
            if self.vs_install_path:
                m.message('Using Visual Studio installed at {!r}'.format(self.vs_install_path))

        if self._is_build_tools_config:
            m.message('Build tools install prefix will be {}'.format(self.prefix))
        else:
            m.message('Install prefix will be {}'.format(self.prefix))
            if self.distro == Distro.MSYS:
                m.warning('Support for the old MSYS is now deprecated. Check the README to migrate to MSYS2 for faster build times')

        # Store current os.environ data
        arches = []
        if isinstance(self.universal_archs, dict):
            arches = self.arch_config.keys()
        for arch_config in list(self.arch_config.values()):
            arch_config._create_paths()
        if arches:
            m.message('Building the following arches: ' + ' '.join(arches))


    def do_setup_env(self):
        self._create_paths()

        libdir = os.path.join(self.prefix, 'lib%s' % self.lib_suffix)
        self.libdir = libdir

        self.env = self.get_env(self.prefix, libdir, self.py_prefix)

    def get_wine_runtime_env(self, prefix, env):
        '''
        When we're creating a cross-winXX shell, these runtime environment
        variables are only useful if the built binaries will be run using Wine,
        so convert them to values that can be understood by programs running
        under Wine.
        '''
        runtime_env = (
            'GI_TYPELIB_PATH',
            'XDG_DATA_DIRS',
            'XDG_CONFIG_DIRS',
            'GST_PLUGIN_PATH',
            'GST_PLUGIN_PATH_1_0',
            'GST_REGISTRY',
            'GST_REGISTRY_1_0',
        )
        for each in runtime_env:
            env[each] = to_winepath(env[each])
        env['WINEPATH'] = to_winepath(os.path.join(prefix, 'bin'))
        return env

    def _merge_env(self, old_env, new_env, override_env=()):
        ret_env = {}
        for k in new_env.keys():
            new_v = new_env[k]
            # Must not accidentally use this with EnvValue objects
            if isinstance(new_v, EnvValue):
                raise AssertionError('{!r}: {!r}'.format(k, new_v))
            if k not in old_env or k in override_env:
                ret_env[k] = new_v
                continue
            old_v = old_env[k]
            if new_v == old_v:
                ret_env[k] = new_v
            elif EnvVar.is_path(k) or EnvVar.is_arg(k) or EnvVar.is_cmd(k):
                ret_env[k] = new_v
            else:
                raise FatalError("Don't know how to combine the environment "
                    "variable '%s' with values '%s' and '%s'" % (k, new_v, old_v))
        for k in old_env.keys():
            if k not in new_env:
                ret_env[k] = old_env[k]
        return ret_env

    @lru_cache(maxsize=None)
    def get_env(self, prefix, libdir, py_prefix):
        # Get paths for environment variables
        includedir = os.path.join(prefix, 'include')
        bindir = os.path.join(prefix, 'bin')
        manpathdir = os.path.join(prefix, 'share', 'man')
        infopathdir = os.path.join(prefix, 'share', 'info')
        typelibpath = os.path.join(libdir, 'girepository-1.0')
        xdgdatadir = os.path.join(prefix, 'share')
        xdgconfigdir = os.path.join(prefix, 'etc', 'xdg')
        xcursordir = os.path.join(prefix, 'share', 'icons')
        aclocalflags = '-I{} -I{}'.format(
            os.path.join(prefix, 'share', 'aclocal'),
            os.path.join(self.build_tools_prefix, 'share', 'aclocal'))

        perlversionpath = os.path.join(libdir, 'perl5', 'site_perl',
                                       self._perl_version())
        if self.target_platform == Platform.WINDOWS:
            # On windows even if perl version is 5.8.8, modules can be
            # installed in 5.8
            perlversionpath = perlversionpath.rsplit('.', 1)[0]

        perl5lib = ':'.join(
            [to_unixpath(os.path.join(libdir, 'perl5')),
            to_unixpath(perlversionpath)])
        gstpluginpath = os.path.join(libdir, 'gstreamer-0.10')
        gstpluginpath10 = os.path.join(libdir, 'gstreamer-1.0')
        gstregistry = os.path.join('~', '.gstreamer-0.10',
                                   'cerbero-registry-%s' % self.target_arch)
        gstregistry10 = os.path.join('~', '.cache', 'gstreamer-1.0',
                                   'cerbero-registry-%s' % self.target_arch)
        gstregistry = os.path.expanduser(gstregistry)
        gstregistry10 = os.path.expanduser(gstregistry10)

        for p in (prefix, self.build_tools_prefix):
            # Explicitly use the posix_prefix scheme because:
            # 1. On Windows, pypath doesn't include Python version although some
            #    packages (pycairo, gi, etc...) install themselves using Python
            #    version scheme like on a posix system.
            # 2. The Python3 that ships with XCode on macOS Big Sur defaults to
            #    a framework path, but setuptools defaults to a posix prefix
            # So just use a posix prefix everywhere consistently.
            pypath = sysconfig.get_path('purelib', 'posix_prefix', vars={'base': ''})
            # Must strip \/ to ensure that the path is relative
            pypath = PurePath(pypath.strip('\\/'))
            # Starting with Python 3.7.1 on Windows, each PYTHONPATH must use the
            # native path separator and must end in a path separator.
            pythonpath = [str(p / pypath) + os.sep]
            # Make sure we also include the default non-versioned path on
            # Windows in addition to the posix path.
            if self.platform == Platform.WINDOWS:
                pypath = sysconfig.get_path('purelib', vars={'base': ''})
                pypath = PurePath(pypath.strip('\\/'))
                pythonpath += [str(p / pypath) + os.sep]

        # Ensure python paths exists because setup.py won't create them
        for path in pythonpath:
            if self.platform == Platform.WINDOWS:
                # pythonpaths start with 'Lib' on Windows, which is extremely
                # undesirable since our libdir is 'lib'. Windows APIs are
                # case-preserving case-insensitive.
                path = path.lower()
            # dict universal arches do not have an active prefix
            if not isinstance(self.universal_archs, dict):
                self._create_path(path)
        pythonpath = os.pathsep.join(pythonpath)

        if self.platform == Platform.LINUX:
            xdgdatadir += ":/usr/share:/usr/local/share"

        ldflags = self.config_env.get('LDFLAGS', '')
        ldflags_libdir = '-L%s ' % libdir
        if ldflags_libdir not in ldflags:
            ldflags = self._join_values(ldflags, ldflags_libdir)

        path = self.config_env.get('PATH', None)
        if not self._is_build_tools_config:
            path = self._join_path(
                os.path.join(self.build_tools_config.prefix, 'bin'), path)
        if self.variants.rust:
            path = self._join_path(os.path.join(self.cargo_home, 'bin'), path)
        # Add the prefix bindir after the build-tools bindir so that on Windows
        # binaries are run with the same libraries that they are linked with.
        if bindir not in path and self.prefix_is_executable():
            path = self._join_path(bindir, path)
        ld_library_path = ''
        if not self._is_build_tools_config:
            ld_library_path = os.path.join(self.build_tools_config.libdir)
        if self.prefix_is_executable():
            ld_library_path = self._join_path(libdir, ld_library_path)
        if self.extra_lib_path is not None:
            ld_library_path = self._join_path(ld_library_path, self.extra_lib_path)
        if self.toolchain_prefix is not None:
            ld_library_path = self._join_path(ld_library_path,
                os.path.join(self.toolchain_prefix, 'lib'))
            includedir = self._join_path(includedir,
                os.path.join(self.toolchain_prefix, 'include'))

        # Most of these variables are extracted from jhbuild
        env = {'LD_LIBRARY_PATH': ld_library_path,
               'LDFLAGS': ldflags,
               'PATH': path,
               'MANPATH': manpathdir,
               'INFOPATH': infopathdir,
               'GI_TYPELIB_PATH': typelibpath,
               'XDG_DATA_DIRS': xdgdatadir,
               'XDG_CONFIG_DIRS': xdgconfigdir,
               'XCURSOR_PATH': xcursordir,
               'ACLOCAL_FLAGS': aclocalflags,
               'ACLOCAL': "aclocal",
               'PERL5LIB': perl5lib,
               'GST_PLUGIN_PATH': gstpluginpath,
               'GST_PLUGIN_PATH_1_0': gstpluginpath10,
               'GST_REGISTRY': gstregistry,
               'GST_REGISTRY_1_0': gstregistry10,
               'PYTHONPATH': pythonpath,
               'MONO_PATH': os.path.join(libdir, 'mono', '4.5'),
               'MONO_GAC_PREFIX': prefix,
               'GSTREAMER_ROOT': prefix,
               'CERBERO_PREFIX': self.prefix,
               'CERBERO_HOST_SOURCES': self.sources,
               'RUSTUP_HOME': self.rustup_home,
               'CARGO_HOME': self.cargo_home,
               }

        PkgConfig.set_executable(env, self)
        PkgConfig.set_default_search_dir(os.path.join(prefix, 'share', 'pkgconfig'), env, self)
        PkgConfig.add_search_dir(os.path.join(libdir, 'pkgconfig'), env, self)

        # Some autotools recipes will call the native (non-cross) compiler to
        # build generators, and we don't want it to use these. We will set the
        # include paths using CFLAGS, etc, when cross-compiling.
        if not self.cross_compiling():
            env['C_INCLUDE_PATH'] = includedir
            env['CPLUS_INCLUDE_PATH'] = includedir

        # merge the config env with this new env
        # LDFLAGS and PATH were already merged above
        new_env = self._merge_env(self.config_env, env, override_env=('LDFLAGS', 'PATH'))

        if self.target_platform == Platform.WINDOWS and self.platform != Platform.WINDOWS:
            new_env = self.get_wine_runtime_env(prefix, new_env)

        return new_env

    def load_defaults(self):
        self.set_property('cache_file', None)
        self.set_property('home_dir', self._default_home_dir())
        self.set_property('prefix', None)
        self.set_property('sources', None)
        self.set_property('local_sources', None)
        self.set_property('cached_sources', self._relative_path('sources'))
        self.set_property('git_root', DEFAULT_GIT_ROOT)
        self.set_property('allow_parallel_build', DEFAULT_ALLOW_PARALLEL_BUILD)
        self.set_property('host', None)
        self.set_property('build', None)
        self.set_property('target', None)
        platform, arch, distro, distro_version, num_of_cpus = system_info()
        target_distro = distro
        # In Windows we do not differenciate between MSYS and MSYS2 for the target_distro
        if platform == Platform.WINDOWS:
            target_distro = Distro.WINDOWS
        self.set_property('platform', platform)
        self.set_property('num_of_cpus', num_of_cpus)
        self.set_property('target_platform', platform)
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
        self.set_property('environ_dir', self._relative_path('config'))
        self.set_property('recipes_dir', self._relative_path('recipes'))
        self.set_property('packages_dir', self._relative_path('packages'))
        self.set_property('allow_system_libs', True)
        self.set_property('use_configure_cache', False)
        self.set_property('external_recipes', {})
        self.set_property('external_packages', {})
        self.set_property('universal_archs', None)
        self.set_property('variants', None)
        self.set_property('build_tools_prefix', None)
        self.set_property('build_tools_sources', None)
        self.set_property('build_tools_cache', None)
        # Build tools that are provided by the system (cmake, ninja, etc)
        self.set_property('system_build_tools', [])
        self.set_property('recipes_commits', {})
        self.set_property('recipes_remotes', {})
        self.set_property('extra_build_tools', [])
        self.set_property('distro_packages_install', True)
        self.set_property('interactive', m.console_is_interactive())
        self.set_property('meson_properties', {})
        self.set_property('manifest', None)
        self.set_property('extra_properties', {})
        self.set_property('extra_mirrors', [])
        self.set_property('extra_bootstrap_packages', {})
        self.set_property('bash_completions', set())
        # Increase open-files limits
        set_nofile_ulimit()

    def set_property(self, name, value, force=False):
        if name not in self._properties:
            raise ConfigurationError('Unknown key %s' % name)
        if force or getattr(self, name) is None:
            setattr(self, name, value)

    def get_recipes_repos(self):
        recipes_dir = {'default': (self.recipes_dir, 0)}
        for name, (path, priority) in self.external_recipes.items():
            path = os.path.abspath(os.path.expanduser(path))
            recipes_dir[name] = (path, priority)
        return recipes_dir

    def get_packages_repos(self):
        packages_dir = {'default': (self.packages_dir, 0)}
        for name, (path, priority) in self.external_packages.items():
            path = os.path.abspath(os.path.expanduser(path))
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
        # Building for UWP is always cross-compilation since we can't run the
        # binaries that we output
        if self.variants.uwp:
            return True
        # On Windows, building 32-bit on 64-bit is not cross-compilation since
        # 32-bit Windows binaries run on 64-bit Windows via WOW64.
        if self.platform == Platform.WINDOWS:
            if self.arch == Architecture.X86_64 and \
               self.target_arch == Architecture.X86:
                return False
        return self.target_platform != self.platform or \
                self.target_arch != self.arch or \
                self.target_distro_version != self.distro_version

    def cross_universal_type(self):
        if not self.cross_compiling():
            return None
        # cross-ios-universal, each arch prefix is merged and flattened into one prefix
        if isinstance(self.universal_archs, list):
            return 'flat'
        # cross-android-universal, each arch prefix is separate
        if isinstance(self.universal_archs, dict):
            return 'normal'
        return None

    def prefix_is_executable(self):
        """Can the binaries from the target platform can be executed in the
        build env?"""
        if self.target_platform != self.platform:
            return False
        # Executables built for UWP cannot be run as-is
        if self.variants.uwp:
            return False
        if self.target_arch != self.arch:
            if self.target_arch == Architecture.X86 and \
                    self.arch == Architecture.X86_64:
                return True
            return False
        return True

    def prefix_is_build_tools(self):
        return self._is_build_tools_config

    def target_distro_version_gte(self, distro_version):
        assert distro_version.startswith(self.target_distro + "_")
        return self.target_distro_version >= distro_version

    def _create_paths(self):
        if self.toolchain_prefix:
            self._create_path(self.toolchain_prefix)
        self._create_path(self.prefix)
        self._create_path(self.sources)
        self._create_path(self.logs)
        # dict universal arches do not have an active prefix
        if not isinstance(self.universal_archs, dict):
            self._create_path(os.path.join(self.prefix, 'share', 'aclocal'))

        if self._is_build_tools_config:
            self._create_path(os.path.join(self.prefix, 'var', 'tmp'))


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
        self.build_tools_config.extra_mirrors = self.extra_mirrors
        self.build_tools_config.cached_sources = self.cached_sources
        self.build_tools_config.vs_install_path = self.vs_install_path
        self.build_tools_config.vs_install_version = self.vs_install_version

        self.build_tools_config.do_setup_env()

    def _parse(self, filename, reset=True):
        config = {'os': os, '__file__': filename, 'env': self.config_env,
                  'cross': self.cross_compiling()}
        if not reset:
            for prop in self._properties:
                if hasattr(self, prop):
                    config[prop] = getattr(self, prop)

        try:
            parse_file(filename, config)
        except:
            raise ConfigurationError(_('Could not include config file (%s)') %
                             filename)
        for key in self._properties:
            if key in config:
                self.set_property(key, config[key], True)

    def _validate_properties(self):
        if not validate_packager(self.packager):
            raise FatalError(_('packager "%s" must be in the format '
                               '"Name <email>"') % self.packager)

    def _check_windows_is_x86_64(self):
         if self.target_platform == Platform.WINDOWS and \
                self.arch == Architecture.X86:
            raise ConfigurationError('The GCC/MinGW toolchain requires an x86 64-bit OS.')

    def _check_uninstalled(self):
        self.uninstalled = int(os.environ.get(CERBERO_UNINSTALLED, 0)) == 1

    def _create_path(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
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
                # in the user config directory
                if not os.path.exists(f):
                    f = os.path.join(USER_CONFIG_DIR, f + "." + CONFIG_EXT)

                if os.path.exists(f):
                    self._parse(f, reset=False)
                else:
                    raise ConfigurationError(_("Configuration file %s doesn't "
                                               "exist") % f)

    def _load_platform_config(self):
        platform_config = os.path.join(self.environ_dir, '%s.config' %
                                       self.target_platform)
        arch_config = os.path.join(self.environ_dir, '%s_%s.config' %
                                   (self.target_platform, self.target_arch))

        for config_path in [platform_config, arch_config]:
            if os.path.exists(config_path):
                self._parse(config_path, reset=False)

    def _get_toolchain_target_platform_arch(self):
        platform_arch = '{}_' + self.target_arch
        if self.target_platform != Platform.WINDOWS or self._is_build_tools_config:
            return (self.target_platform, self.target_arch)
        if not self.variants.visualstudio:
            return ('mingw', self.target_arch)
        # When building with Visual Studio, we can target (MSVC, UWP) x (debug, release)
        if self.variants.uwp:
            target_platform = 'uwp'
        else:
            target_platform = 'msvc'
        # Debug CRT needs a separate prefix
        if self.variants.vscrt == 'mdd':
            target_platform += '-debug'
        # Check for invalid configuration of a custom Visual Studio path
        if self.vs_install_path and not self.vs_install_version:
            raise ConfigurationError('vs_install_path was set, but vs_install_version was not')
        return (target_platform, self.target_arch)

    def _load_last_defaults(self):
        # Set build tools defaults
        self.set_property('build_tools_prefix',
                os.path.join(self.home_dir, 'build-tools'))
        self.set_property('build_tools_sources',
                os.path.join(self.home_dir, 'sources', 'build-tools'))
        self.set_property('build_tools_logs',
                os.path.join(self.home_dir, 'logs', 'build-tools'))
        self.set_property('build_tools_cache', 'build-tools.cache')
        # Set target platform defaults
        platform_arch = '_'.join(self._get_toolchain_target_platform_arch())
        self.set_property('prefix', os.path.join(self.home_dir, "dist", platform_arch))
        self.set_property('sources', os.path.join(self.home_dir, "sources", platform_arch))
        self.set_property('logs', os.path.join(self.home_dir, "logs", platform_arch))
        self.set_property('cache_file', platform_arch + ".cache")
        self.set_property('install_dir', self.prefix)
        self.set_property('local_sources', self._default_local_sources_dir())
        self.set_property('rust_prefix', os.path.join(self.home_dir, 'rust'))
        self.set_property('rustup_home', os.path.join(self.rust_prefix, 'rustup'))
        self.set_property('cargo_home', os.path.join(self.rust_prefix, 'cargo'))
        self.set_property('tomllib_path', os.path.join(self.rust_prefix, 'tomllib'))
        if sys.version_info >= (3, 11, 0):
            self.python_exe = Path(self.build_tools_prefix, 'bin', 'python').as_posix()
        else:
            self.python_exe = Path(sys.executable).as_posix()

    def _get_exe_suffix(self):
        if self.platform != Platform.WINDOWS:
            return ''
        return '.exe'

    def _find_data_dir(self):
        if self.uninstalled:
            self.data_dir = os.path.join(os.path.dirname(__file__),
                                         '..', 'data')
            self.data_dir = os.path.abspath(self.data_dir)
            return
        curdir = os.path.dirname(__file__)
        while not os.path.exists(os.path.join(curdir, 'share', 'cerbero',
                'config')):
            curdir = os.path.abspath(os.path.join(curdir, '..'))
            if curdir == '/' or curdir[1:] == ':/':
                # We reached the root without finding the data dir, which
                # shouldn't happen
                raise FatalError("Data dir not found")
        self.data_dir = os.path.join(curdir, 'share', 'cerbero')

    def _relative_path(self, path):
        if not self.uninstalled:
            p = os.path.join(self.data_dir, path)
        else:
            p = os.path.join(os.path.dirname(__file__), '..', path)
        return os.path.abspath(p)

    def _default_home_dir(self):
        if self.uninstalled:
            p = os.path.join(os.path.dirname(__file__), '..', 'build')
        else:
            p = os.path.expanduser('~/cerbero')
        return os.path.abspath(p)

    def _default_local_sources_dir(self):
        # For backwards-compatibility, keep the old value for setups that
        # define their own home_dir inside which all cerbero work must be
        # contained; f.ex. ci.gstreamer.net
        if self.home_dir != self._default_home_dir():
            return os.path.join(self.home_dir, 'sources', 'local')
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
            version = shell.check_output("perl -e 'print \"$]\";'")
        except FatalError:
            m.warning(_("Perl not found, you may need to run bootstrap."))
            version = '0.000000'
        # FIXME: when perl's mayor is >= 10
        mayor = str(version[0])
        minor = str(int(version[2:5]))
        revision = str(int(version[5:8]))
        return '.'.join([mayor, minor, revision])

    @staticmethod
    def rust_triple(arch, platform, vs):
        if platform != Platform.WINDOWS:
            key = (platform, arch)
        elif vs:
            key = (Platform.WINDOWS, arch, 'msvc')
        else:
            key = (Platform.WINDOWS, arch, 'gnu')
        if key in RUST_TRIPLE_MAPPING:
            return RUST_TRIPLE_MAPPING[key]
        else:
            raise FatalError(f'Unsupported build platform/arch combination: {platform}/{arch}')

    @property
    def rust_build_triple(self):
        return self.rust_triple(self.arch, self.platform, self.variants.visualstudio)

    @property
    def rust_target_triples(self):
        if self.target_arch != Architecture.UNIVERSAL:
            targets = (self.target_arch,)
        else:
            targets = self.arch_config.keys()
        triples = []
        for target_arch in targets:
            triple = self.rust_triple(target_arch, self.target_platform, self.variants.visualstudio)
            triples.append(triple)
        return triples

    def find_toml_module(self, system_only=False):
        import importlib
        if sys.version_info >= (3, 11, 0):
            return importlib.import_module('tomllib')
        for m in ('tomli', 'toml', 'tomlkit'):
            try:
                return importlib.import_module(m)
            except ModuleNotFoundError:
                continue
        if not system_only and os.path.exists(self.tomllib_path):
            tomli_dir = os.path.join(self.tomllib_path, 'src')
            sys.path.insert(0, os.path.abspath(tomli_dir))
            return importlib.import_module('tomli')
        return None
