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
from pathlib import PurePath

from cerbero import enums
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import _, system_info, validate_packager, to_unixpath,\
    shell, parse_file
from cerbero.utils import messages as m


CONFIG_DIR = os.path.expanduser('~/.cerbero')
CONFIG_EXT = 'cbc'
DEFAULT_CONFIG_FILENAME = 'cerbero.%s' % CONFIG_EXT
DEFAULT_CONFIG_FILE = os.path.join(CONFIG_DIR, DEFAULT_CONFIG_FILENAME)
DEFAULT_GIT_ROOT = 'https://anongit.freedesktop.org/git/gstreamer'
DEFAULT_ALLOW_PARALLEL_BUILD = True
DEFAULT_PACKAGER = "Default <default@change.me>"
CERBERO_UNINSTALLED = 'CERBERO_UNINSTALLED'
CERBERO_PREFIX = 'CERBERO_PREFIX'


Platform = enums.Platform
Architecture = enums.Architecture
Distro = enums.Distro
DistroVersion = enums.DistroVersion
License = enums.License


class Variants(object):

    __disabled_variants = ['x11', 'alsa', 'pulse', 'cdparanoia', 'v4l2', 'sdl',
                           'gi', 'unwind', 'rpi', 'visualstudio']
    __enabled_variants = ['debug', 'python', 'testspackage']

    def __init__(self, variants):
        for v in self.__enabled_variants:
            setattr(self, v, True)
        for v in self.__disabled_variants:
            setattr(self, v, False)
        for v in variants:
            if v.startswith('no'):
                setattr(self, v[2:], False)
            else:
                setattr(self, v, True)

    def __getattr__(self, name):
        try:
            if name.startswith('no'):
                return not object.__getattribute__(self, name[2:])
            else:
                return object.__getattribute__(self, name)
        except Exception:
            raise AttributeError("%s is not a known variant" % name)


class Config (object):

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
                   'build_tools_prefix', 'build_tools_sources',
                   'build_tools_cache', 'home_dir', 'recipes_commits',
                   'recipes_remotes', 'ios_platform', 'extra_build_tools',
                   'distro_packages_install', 'interactive',
                   'target_arch_flags', 'sysroot', 'isysroot',
                   'extra_lib_path', 'cached_sources', 'tools_prefix',
                   'ios_min_version', 'toolchain_path', 'mingw_perl_prefix',
                   'msvc_toolchain_env']

    def __init__(self):
        self._check_uninstalled()
        self.python_exe = sys.executable

        for a in self._properties:
            setattr(self, a, None)

        self.arch_config = {self.target_arch: self}
        # Store raw os.environ data
        self._raw_environ = os.environ.copy()
        self._pre_environ = os.environ.copy()

    def _copy(self, arch):
        c = copy.deepcopy(self)
        c.target_arch = arch
        c._raw_environ = os.environ.copy()
        return c

    def load(self, filename=None):

        # First load the default configuration
        self.load_defaults()

        # Next parse the main configuration file
        self._load_main_config()

        # Next, if a config file is provided use it to override the settings
        # from the main configuration file
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
                    # Allow the config to detect whether this config is
                    # running under a universal setup and some
                    # paths/configuration need to change
                    arch_config[arch].variants += ['universal']
                    if config_file is not None:
                        # This works because the override config files are
                        # fairly light. Things break if they are more complex
                        # as load config can have side effects in global state
                        d = os.path.dirname(filename[0])
                        arch_config[arch]._load_cmd_config([os.path.join(d, config_file)])
            else:
                raise ConfigurationError('universal_archs must be a list or a dict')

            self.arch_config = arch_config

        # Finally fill the missing gaps in the config
        self._load_last_defaults()

        self._load_platform_config()

        # And validate properties
        self._validate_properties()
        self._raw_environ = os.environ.copy()

        for config in list(self.arch_config.values()):
            config._restore_environment()
            if self.target_arch == Architecture.UNIVERSAL:
                config.sources = os.path.join(self.sources, config.target_arch)
                config.prefix = os.path.join(self.prefix)
            config._load_platform_config()
            config._load_last_defaults()
            config._validate_properties()
            config._raw_environ = os.environ.copy()

        # Build variants before copying any config
        self.variants = Variants(self.variants)
        if not self.prefix_is_executable() and self.variants.gi:
            m.warning(_("gobject introspection requires an executable "
                        "prefix, 'gi' variant will be removed"))
            self.variants.gi = False

        for c in list(self.arch_config.values()):
            c.variants = self.variants

        self.do_setup_env()

        # Store current os.environ data
        for c in list(self.arch_config.values()):
            self._create_path(c.local_sources)
            self._create_path(c.sources)
            self._create_path(c.logs)

    def do_setup_env(self):
        self._restore_environment()
        self._create_path(self.prefix)
        self._create_path(os.path.join(self.prefix, 'share', 'aclocal'))
        self._create_path(os.path.join(
            self.build_tools_prefix, 'share', 'aclocal'))

        libdir = os.path.join(self.prefix, 'lib%s' % self.lib_suffix)
        self.libdir = libdir
        os.environ[CERBERO_PREFIX] = self.prefix

        self.env = self.get_env(self.prefix, libdir, self.py_prefix)
        # set all the variables
        for e, v in self.env.items():
            os.environ[e] = v

    def get_env(self, prefix, libdir, py_prefix):
        # Get paths for environment variables
        includedir = os.path.join(prefix, 'include')
        bindir = os.path.join(prefix, 'bin')
        manpathdir = os.path.join(prefix, 'share', 'man')
        infopathdir = os.path.join(prefix, 'share', 'info')
        pkgconfigbin = os.path.join(self.build_tools_prefix, 'bin', 'pkg-config')
        pkgconfigdatadir = os.path.join(prefix, 'share', 'pkgconfig')
        pkgconfigdir = os.path.join(libdir, 'pkgconfig')
        typelibpath = os.path.join(libdir, 'girepository-1.0')
        xdgdatadir = os.path.join(prefix, 'share')
        xdgconfigdir = os.path.join(prefix, 'etc', 'xdg')
        xcursordir = os.path.join(prefix, 'share', 'icons')
        aclocaldir = os.path.join(prefix, 'share', 'aclocal')
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

        pypath = sysconfig.get_path('purelib', vars={'base': ''})
        # Ensure that / is the path separator and not \, then strip /
        pypath = PurePath(pypath).as_posix().strip('/')
        # Ensure python paths exists because setup.py won't create them
        pythonpath = [os.path.join(prefix, pypath),
                      os.path.join(self.build_tools_prefix, pypath)]
        for path in pythonpath:
            self._create_path(path)
        pythonpath = os.pathsep.join(pythonpath)

        if self.platform == Platform.LINUX:
            xdgdatadir += ":/usr/share:/usr/local/share"

        ldflags = '-L%s ' % libdir
        if ldflags not in os.environ.get('LDFLAGS', ''):
            ldflags += os.environ.get('LDFLAGS', '')

        path = os.environ.get('PATH', '')
        if bindir not in path and self.prefix_is_executable():
            path = self._join_path(bindir, path)
        path = self._join_path(
            os.path.join(self.build_tools_prefix, 'bin'), path)

        if not self.cross_compiling():
            ld_library_path = libdir
        else:
            ld_library_path = ""
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
               'C_INCLUDE_PATH': includedir,
               'CPLUS_INCLUDE_PATH': includedir,
               'PATH': path,
               'MANPATH': manpathdir,
               'INFOPATH': infopathdir,
               'PKG_CONFIG': pkgconfigbin,
               'PKG_CONFIG_PATH': '%s' % pkgconfigdatadir,
               'PKG_CONFIG_LIBDIR': '%s' % pkgconfigdir,
               'GI_TYPELIB_PATH': typelibpath,
               'XDG_DATA_DIRS': xdgdatadir,
               'XDG_CONFIG_DIRS': xdgconfigdir,
               'XCURSOR_PATH': xcursordir,
               'ACLOCAL_FLAGS': '-I%s' % aclocaldir,
               'ACLOCAL': "aclocal",
               'PERL5LIB': perl5lib,
               'GST_PLUGIN_PATH': gstpluginpath,
               'GST_PLUGIN_PATH_1_0': gstpluginpath10,
               'GST_REGISTRY': gstregistry,
               'GST_REGISTRY_1_0': gstregistry10,
               'PYTHONPATH': pythonpath,
               'MONO_PATH': os.path.join(libdir, 'mono', '4.5'),
               'MONO_GAC_PREFIX': prefix,
               'GSTREAMER_ROOT': prefix
               }

        return env

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
        self.set_property('platform', platform)
        self.set_property('num_of_cpus', num_of_cpus)
        self.set_property('target_platform', platform)
        self.set_property('arch', arch)
        self.set_property('target_arch', arch)
        self.set_property('distro', distro)
        self.set_property('target_distro', distro)
        self.set_property('distro_version', distro_version)
        self.set_property('target_distro_version', distro_version)
        self.set_property('packages_prefix', None)
        self.set_property('packager', DEFAULT_PACKAGER)
        stdlibpath = sysconfig.get_path('stdlib', vars={'installed_base': ''})
        # Ensure that the path uses / as path separator and not \
        self.set_property('py_prefix', PurePath(stdlibpath).as_posix())
        self.set_property('lib_suffix', '')
        self.set_property('data_dir', self._find_data_dir())
        self.set_property('environ_dir', self._relative_path('config'))
        self.set_property('recipes_dir', self._relative_path('recipes'))
        self.set_property('packages_dir', self._relative_path('packages'))
        self.set_property('allow_system_libs', True)
        self.set_property('use_configure_cache', False)
        self.set_property('external_recipes', {})
        self.set_property('external_packages', {})
        self.set_property('universal_archs',
                          [Architecture.X86, Architecture.X86_64])
        self.set_property('variants', [])
        self.set_property('build_tools_prefix', None)
        self.set_property('build_tools_sources', None)
        self.set_property('build_tools_cache', None)
        self.set_property('recipes_commits', {})
        self.set_property('recipes_remotes', {})
        self.set_property('extra_build_tools', {})
        self.set_property('distro_packages_install', True)
        self.set_property('interactive', True)

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

    def recipe_remotes(self, recipe_name):
        if recipe_name in self.recipes_remotes:
            rrs = self.recipes_remotes[recipe_name]
            if not isinstance(rrs, dict):
                raise ConfigurationError('recipes_remotes value for recipe %s '
                                         'must be a dict in the form '
                                         '{ \'remote-name\' : \'remote-url\' }'
                                         % recipe_name)
            return rrs
        return {}

    def cross_compiling(self):
        "Are we building for the host platform or not?"
        # On Windows, building 32-bit on 64-bit is not cross-compilation since
        # 32-bit Windows binaries run on 64-bit Windows via WOW64.
        if self.platform == Platform.WINDOWS:
            if self.arch == Architecture.X86_64 and \
               self.target_arch == Architecture.X86:
                return False
        return self.target_platform != self.platform or \
                self.target_arch != self.arch or \
                self.target_distro_version != self.distro_version

    def prefix_is_executable(self):
        """Can the binaries from the target platform can be executed in the
        build env?"""
        if self.target_platform != self.platform:
            return False
        if self.target_arch != self.arch:
            if self.target_arch == Architecture.X86 and \
                    self.arch == Architecture.X86_64:
                return True
            return False
        return True

    def target_distro_version_gte(self, distro_version):
        assert distro_version.startswith(self.target_distro + "_")
        return self.target_distro_version >= distro_version

    def _parse(self, filename, reset=True):
        config = {'os': os, '__file__': filename}
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

    def _restore_environment(self):
        os.environ.clear()
        os.environ.update(self._raw_environ)

    def _validate_properties(self):
        if not validate_packager(self.packager):
            raise FatalError(_('packager "%s" must be in the format '
                               '"Name <email>"') % self.packager)

    def _check_uninstalled(self):
        self.uninstalled = int(os.environ.get(CERBERO_UNINSTALLED, 0)) == 1

    def _create_path(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
                raise FatalError(_('directory (%s) can not be created') % path)

    def _join_path(self, path1, path2):
        if len(path1) == 0:
            return path2
        if len(path2) == 0:
            return path1
        if self.platform == Platform.WINDOWS:
            separator = ';'
        else:
            separator = ':'
        return "%s%s%s" % (path1, separator, path2)

    def _load_main_config(self):
        if os.path.exists(DEFAULT_CONFIG_FILE):
            self._parse(DEFAULT_CONFIG_FILE)
        else:
            msg = _('Using default configuration because %s is missing') % \
                DEFAULT_CONFIG_FILE
            m.warning(msg)

    def _load_cmd_config(self, filenames):
        if filenames is not None:
            for f in filenames:
                if not os.path.exists(f):
                    f = os.path.join(CONFIG_DIR, f + "." + CONFIG_EXT)

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

    def _load_last_defaults(self):
        self.set_property('prefix', os.path.join(self.home_dir, "dist",
            "%s_%s" % (self.target_platform, self.target_arch)))
        self.set_property('sources', os.path.join(self.home_dir, "sources",
            "%s_%s" % (self.target_platform, self.target_arch)))
        self.set_property('logs', os.path.join(self.home_dir, "logs",
            "%s_%s" % (self.target_platform, self.target_arch)))
        self.set_property('cache_file',
                "%s_%s.cache" % (self.target_platform, self.target_arch))
        self.set_property('install_dir', self.prefix)
        self.set_property('local_sources',
                os.path.join(self.home_dir, 'sources', 'local'))
        self.set_property('build_tools_prefix',
                os.path.join(self.home_dir, 'build-tools'))
        self.set_property('build_tools_sources',
                os.path.join(self.home_dir, 'sources', 'build-tools'))
        self.set_property('build_tools_cache', 'build-tools.cache')

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

    def _perl_version(self):
        version = shell.check_call("perl -e 'print \"$]\";'")
        # FIXME: when perl's mayor is >= 10
        mayor = str(version[0])
        minor = str(int(version[2:5]))
        revision = str(int(version[5:8]))
        return '.'.join([mayor, minor, revision])
