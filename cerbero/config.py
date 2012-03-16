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

from cerbero import enums
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import _, system_info
from cerbero.utils import messages as m


CONFIG_DIR = os.path.expanduser('~/.cerbero')
CONFIG_EXT = 'cbc'
DEFAULT_CONFIG_FILENAME = 'cerbero.%s' % CONFIG_EXT
DEFAULT_CONFIG_FILE = os.path.join(CONFIG_DIR, DEFAULT_CONFIG_FILENAME)
DEFAULT_GIT_ROOT = 'git+ssh://git.keema.collabora.co.uk/git/gst-sdk/'
DEFAULT_WIX_PREFIX = 'C:\\\\Program Files\\Windows Installer XML v3.5\\bin\\'
CERBERO_UNINSTALLED = 'CERBERO_UNINSTALLED'


Platform = enums.Platform
Architecture = enums.Architecture
Distro = enums.Distro
DistroVersion = enums.DistroVersion


class Config (object):

    _properties = ['platform', 'target_platform', 'arch', 'target_arch',
                   'prefix', 'recipes_dir', 'host', 'build', 'target',
                   'sources', 'local_sources', 'lib_suffix', 'git_root',
                   'distro', 'target_distro', 'environ_dir', 'cache_file',
                   'toolchain_prefix', 'distro_version',
                   'target_distro_version', 'allow_system_libs',
                   'packages_dir', 'wix_prefix'
                   ]

    def __init__(self, filename=None):
        self._check_uninstalled()

        for a in self._properties:
            setattr(self, a, None)

        # First load the default configuration
        self.load_defaults()

        # Next parse the main configuration file
        if os.path.exists(DEFAULT_CONFIG_FILE):
            self.parse(DEFAULT_CONFIG_FILE)
        else:
            msg = _('Using default configuration because %s is missing') % \
                    DEFAULT_CONFIG_FILE
            m.warning(msg)

        # Next, if a config file is provided use it to override the settings
        # from the main configuration file
        if filename is not None:
            if os.path.exists(filename):
                self.parse(filename)
                self.filename = DEFAULT_CONFIG_FILE
            else:
                raise ConfigurationError(_("Configuration file %s doesn't exsits"))

        # Next, load the platform configuration
        self._load_platform_config()

        # Finally fill the missing gaps in the config
        self._load_last_defaults()

        self.setup_env()
        self._create_path(self.local_sources)
        self._create_path(self.sources)

    def parse(self, filename, reset=True):
        if reset:
            config = {}
        else:
            config = {}
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

        os.environ['CERBERO_PREFIX'] = self.prefix

        libdir = os.path.join(self.prefix, 'lib%s' % self.lib_suffix)
        self.libdir = libdir

        # Get paths for environment variables
        includedir = os.path.join(self.prefix, 'include')
        bindir = os.path.join(self.prefix, 'bin')
        manpathdir = os.path.join(self.prefix, 'share', 'man')
        infopathdir = os.path.join(self.prefix, 'share', 'info')
        pkgconfigdatadir = os.path.join(self.prefix, 'share', 'pkgconfig')
        pkgconfigdir = os.path.join(libdir, 'pkgconfig')
        typelibpath = os.path.join(self.libdir, 'girepository-1.0')
        xdgdatadir = os.path.join(self.prefix, 'share')
        xdgconfigdir = os.path.join(self.prefix, 'etc', 'xdg')
        xcursordir = os.path.join(self.prefix, 'share', 'icons')
        aclocaldir = os.path.join(self.prefix, 'share', 'aclocal')
        perl5lib = os.path.join(self.prefix, 'lib', 'perl5')

        self._create_path(aclocaldir)

        # Most of these variables are extracted from jhbuild
        # FIXME: add python when needed
        env = {'LD_LIBRARY_PATH': libdir,
               'LDFLAGS': '-L%s %s' % (libdir,  os.environ.get('LDFLAGS', '')),
               'C_INCLUDE_PATH': includedir,
               'CPLUS_INCLUDE_PATH': includedir,
               'DYLD_FALLBACK_LIBRARY_PATH': libdir,
               'PATH': self._join_path('PATH', bindir),
               'MANPATH': manpathdir,
               'INFOPATH': infopathdir,
               'PKG_CONFIG_PATH': '%s' % pkgconfigdatadir,
               'PKG_CONFIG_LIBDIR': '%s' % pkgconfigdir,
               'GI_TYPELIB_PATH': typelibpath,
               'XDG_DATA_DIRS': xdgdatadir,
               'XDG_CONFIG_DIRS': xdgconfigdir,
               'XCURSOR_PATH': xcursordir,
               #'ACLOCAL': aclocaldir,
               'PERL5LIB': perl5lib,
               'MONO_PREFIX': self.prefix,
               'MONO_GAC_PREFIX': self.prefix,
               }

        # set all the variables
        self.env = env
        for e, v in env.iteritems():
            os.environ[e] = v

    def _check_uninstalled(self):
        self.uninstalled = int(os.environ.get(CERBERO_UNINSTALLED, 0)) == 1

    def _create_path(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except:
                raise FatalError(_('directory (%s) can not be created') % path)

    def _join_path(self, env, path):
        if env not in os.environ:
            return path
        else:
            if self.platform == Platform.WINDOWS:
                separator = ';'
            else:
                separator = ':'
            return "%s%s%s" % (path, separator, os.environ['PATH'])

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
        self.set_property('sources', os.path.join(cerbero_home, 'sources'))
        self.set_property('local_sources', os.path.join(cerbero_home, 'sources', 'local'))

    def load_defaults(self):
        cerbero_home = os.path.expanduser('~/cerbero')
        self.set_property('cache_file', None)
        self.set_property('prefix', None)
        self.set_property('sources', None)
        self.set_property('local_sources', None)
        if not self.uninstalled:
            self.set_property('recipes_dir',
                              os.path.join(cerbero_home, 'recipes'))
            self.set_property('packages_dir',
                              os.path.join(cerbero_home, 'packages'))
        else:
            self.set_property('recipes_dir',
                os.path.join(os.path.dirname(__file__), '..', 'recipes'))
            self.set_property('packages_dir',
                os.path.join(os.path.dirname(__file__), '..', 'packages'))
        self.set_property('git_root', DEFAULT_GIT_ROOT)
        self.set_property('wix_prefix', DEFAULT_WIX_PREFIX)
        self.set_property('host', None)
        self.set_property('build', None)
        self.set_property('target', None)
        platform, arch, distro, distro_version = system_info()
        self.set_property('platform', platform)
        self.set_property('target_platform', platform)
        self.set_property('arch', arch)
        self.set_property('target_arch', arch)
        self.set_property('distro', distro)
        self.set_property('target_distro', distro)
        self.set_property('distro_version', distro_version)
        self.set_property('target_distro_version', distro_version)
        self.set_property('lib_suffix', '')
        if not self.uninstalled:
            self.set_property('environ_dir', os.path.join(CONFIG_DIR))
        else:
            self.set_property('environ_dir',
                os.path.join(os.path.dirname(__file__), '..', 'config'))
        self.set_property('allow_system_libs', True)

    def set_property(self, name, value, force=False):
        if name not in self._properties:
            raise ConfigurationError('Unkown key %s' % name)
        if force or getattr(self, name) is None:
            setattr(self, name, value)
