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

from cerbero import enums
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import _, system_info, validate_packager, to_unixpath,\
        shell
from cerbero.utils import messages as m


CONFIG_DIR = os.path.expanduser('~/.cerbero')
CONFIG_EXT = 'cbc'
DEFAULT_CONFIG_FILENAME = 'cerbero.%s' % CONFIG_EXT
DEFAULT_CONFIG_FILE = os.path.join(CONFIG_DIR, DEFAULT_CONFIG_FILENAME)
DEFAULT_GIT_ROOT = 'git://anongit.freedesktop.org/gstreamer-sdk'
DEFAULT_WIX_PREFIX = 'C:/Program\ Files\ \(x86\)/Windows\ Installer\ XML\ v3.5/bin'
DEFAULT_ALLOW_PARALLEL_BUILD = False
DEFAULT_PACKAGER = "Default <default@change.me>"
CERBERO_UNINSTALLED = 'CERBERO_UNINSTALLED'


Platform = enums.Platform
Architecture = enums.Architecture
Distro = enums.Distro
DistroVersion = enums.DistroVersion
License = enums.License


class Config (object):

    _properties = ['platform', 'target_platform', 'arch', 'target_arch',
                   'prefix', 'recipes_dir', 'host', 'build', 'target',
                   'sources', 'local_sources', 'lib_suffix', 'git_root',
                   'distro', 'target_distro', 'environ_dir', 'cache_file',
                   'toolchain_prefix', 'distro_version',
                   'target_distro_version', 'allow_system_libs',
                   'packages_dir', 'wix_prefix', 'py_prefix',
                   'install_dir', 'allow_parallel_build', 'num_of_cpus',
                   'use_configure_cache', 'packages_prefix', 'packager',
                   'data_dir', 'min_osx_sdk_version', 'external_recipes',
                   'external_packages', 'use_ccache']

    def __init__(self, filename=None, load=True):
        self._check_uninstalled()

        for a in self._properties:
            setattr(self, a, None)

        if not load:
            return

        # First load the default configuration
        self.load_defaults()

        # Next parse the main configuration file
        self._load_main_config()

        # Next, if a config file is provided use it to override the settings
        # from the main configuration file
        self._load_cmd_config(filename)

        # Next, load the platform configuration
        self._load_platform_config()

        # Finally fill the missing gaps in the config
        self._load_last_defaults()

        # And validate properties
        self.validate_properties()

        self.setup_env()
        self._create_path(self.local_sources)
        self._create_path(self.sources)

    def parse(self, filename, reset=True):
        config = {'os': os}
        if not reset:
            for prop in self._properties:
                if hasattr(self, prop):
                    config[prop] = getattr(self, prop)

        try:
            execfile(filename, config)
        except:
            raise ConfigurationError(_('Could not include config file (%s)') %
                             filename)
        for key in self._properties:
            if key in config:
                self.set_property(key, config[key], True)

    def setup_env(self):
        self._create_path(self.prefix)
        self._create_path(os.path.join(self.prefix, 'share', 'aclocal'))

        libdir = os.path.join(self.prefix, 'lib%s' % self.lib_suffix)
        self.libdir = libdir
        os.environ['CERBERO_PREFIX'] = self.prefix

        self.env = self.get_env(self.prefix, libdir, self.py_prefix)
        # set all the variables
        for e, v in self.env.iteritems():
            os.environ[e] = v

    def get_env(self, prefix, libdir, py_prefix):
        # Get paths for environment variables
        includedir = os.path.join(prefix, 'include')
        bindir = os.path.join(prefix, 'bin')
        manpathdir = os.path.join(prefix, 'share', 'man')
        infopathdir = os.path.join(prefix, 'share', 'info')
        pkgconfigdatadir = os.path.join(prefix, 'share', 'pkgconfig')
        pkgconfigdir = os.path.join(libdir, 'pkgconfig')
        typelibpath = os.path.join(libdir, 'girepository-1.0')
        xdgdatadir = os.path.join(prefix, 'share')
        xdgconfigdir = os.path.join(prefix, 'etc', 'xdg')
        xcursordir = os.path.join(prefix, 'share', 'icons')
        aclocal = os.environ.get('ACLOCAL', 'aclocal')
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
        gstregistry = os.path.join('~', '.gstreamer-0.10',
                                    '.cerbero-registry-%s' % self.target_arch)
        pythonpath = os.path.join(prefix, py_prefix, 'site-packages')

        if self.platform == Platform.LINUX:
            xdgdatadir += ":/usr/share:/usr/local/share"

        ldflags = '-L%s ' % libdir
        if ldflags not in os.environ.get('LDFLAGS', ''):
            ldflags += os.environ.get('LDFLAGS', '')

        path = os.environ.get('PATH', '')
        if bindir not in path:
            path = self._join_path(bindir, path)

        # Most of these variables are extracted from jhbuild
        env = {'LD_LIBRARY_PATH': libdir,
               'LDFLAGS': ldflags,
               'C_INCLUDE_PATH': includedir,
               'CPLUS_INCLUDE_PATH': includedir,
               'DYLD_FALLBACK_LIBRARY_PATH': libdir,
               'PATH': path,
               'MANPATH': manpathdir,
               'INFOPATH': infopathdir,
               'PKG_CONFIG_PATH': '%s' % pkgconfigdatadir,
               'PKG_CONFIG_LIBDIR': '%s' % pkgconfigdir,
               'GI_TYPELIB_PATH': typelibpath,
               'XDG_DATA_DIRS': xdgdatadir,
               'XDG_CONFIG_DIRS': xdgconfigdir,
               'XCURSOR_PATH': xcursordir,
               'ACLOCAL_FLAGS': '-I %s' % aclocaldir,
               'ACLOCAL': aclocal,
               'PERL5LIB': perl5lib,
               'MONO_PREFIX': prefix,
               'MONO_GAC_PREFIX': prefix,
               'GST_PLUGIN_PATH': gstpluginpath,
               'GST_REGISTRY': gstregistry,
               'PYTHONPATH': pythonpath
               }

        if self.platform == Platform.WINDOWS:
            # for pkg-config installed with the toolchain
            env['ACLOCAL_FLAGS'] += ' -I %s/share/aclocal' % \
                    self.toolchain_prefix
            env['ACLOCAL'] = '%s %s' % (aclocal, env['ACLOCAL_FLAGS'])

        return env

    def _check_uninstalled(self):
        self.uninstalled = int(os.environ.get(CERBERO_UNINSTALLED, 0)) == 1

    def _create_path(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
                raise FatalError(_('directory (%s) can not be created') % path)

    def _join_path(self, path1, path2):
        if self.platform == Platform.WINDOWS:
            separator = ';'
        else:
            separator = ':'
        return "%s%s%s" % (path1, separator, path2)

    def _load_main_config(self):
        if os.path.exists(DEFAULT_CONFIG_FILE):
            self.parse(DEFAULT_CONFIG_FILE)
        else:
            msg = _('Using default configuration because %s is missing') % \
                    DEFAULT_CONFIG_FILE
            m.warning(msg)

    def _load_cmd_config(self, filename):
        if filename is not None:
            if os.path.exists(filename):
                self.parse(filename, reset=False)
                self.filename = DEFAULT_CONFIG_FILE
            else:
                raise ConfigurationError(_("Configuration file %s doesn't "
                                           "exists") % filename)
    def _load_platform_config(self):
        platform_config = os.path.join(self.environ_dir, '%s.config' %
                                       self.target_platform)
        arch_config = os.path.join(self.environ_dir, '%s_%s.config' %
                                   (self.target_platform, self.target_arch))

        for config in [platform_config, arch_config]:
            if os.path.exists(config):
                self.parse(config, reset=False)

    def _load_last_defaults(self):
        cerbero_home = os.path.expanduser('~/cerbero')
        self.set_property('prefix', os.path.join(cerbero_home, 'dist'))
        self.set_property('install_dir', self.prefix)
        self.set_property('sources', os.path.join(cerbero_home, 'sources'))
        self.set_property('local_sources',
                os.path.join(cerbero_home, 'sources', 'local'))

    def load_defaults(self):
        self.set_property('cache_file', None)
        self.set_property('prefix', None)
        self.set_property('sources', None)
        self.set_property('local_sources', None)
        self.set_property('git_root', DEFAULT_GIT_ROOT)
        self.set_property('allow_parallel_build', DEFAULT_ALLOW_PARALLEL_BUILD)
        self.set_property('wix_prefix', DEFAULT_WIX_PREFIX)
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
        self.set_property('py_prefix', 'lib/python%s.%s' %
                (sys.version_info[0], sys.version_info[1]))
        self.set_property('lib_suffix', '')
        self.set_property('data_dir', self._find_data_dir())
        self.set_property('environ_dir', self._relative_path('config'))
        self.set_property('recipes_dir', self._relative_path('recipes'))
        self.set_property('packages_dir', self._relative_path('packages'))
        self.set_property('allow_system_libs', True)
        self.set_property('use_configure_cache', False)
        self.set_property('external_recipes', {})
        self.set_property('external_packages', {})

    def validate_properties(self):
        if not validate_packager(self.packager):
            raise FatalError(_('packager "%s" must be in the format '
                               '"Name <email>"') % self.packager)

    def set_property(self, name, value, force=False):
        if name not in self._properties:
            raise ConfigurationError('Unkown key %s' % name)
        if force or getattr(self, name) is None:
            setattr(self, name, value)

    def get_recipes_repos(self):
        recipes_dir = {'default': (self.recipes_dir, 0)}
        for name, (path, priority) in self.external_recipes.iteritems():
            path = os.path.abspath(os.path.expanduser(path))
            recipes_dir[name] = (path, priority)
        return recipes_dir

    def get_packages_repos(self):
        packages_dir = {'default': (self.packages_dir, 0)}
        for name, (path, priority) in self.external_packages.iteritems():
            path = os.path.abspath(os.path.expanduser(path))
            packages_dir[name] = (path, priority)
        return packages_dir

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

    def _perl_version(self):
        version = shell.check_call("perl -e 'print \"$]\";'");
        # FIXME: when perl's mayor is >= 10
        mayor = version[0]
        minor = str(int(version[2:5]))
        revision = str(int(version[5:8]))
        return '.'.join([mayor, minor, revision])
