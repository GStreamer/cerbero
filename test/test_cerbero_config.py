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
import tempfile
import unittest

from cerbero import config as cconfig
from cerbero.errors import FatalError, ConfigurationError
from cerbero.utils import system_info

Config = cconfig.Config


class LinuxPackagesTest(unittest.TestCase):
    def setUp(self):
        os.environ[cconfig.CERBERO_UNINSTALLED] = '1'

    def _checkLoadConfig(self, config, func, filename, properties):
        with open(filename, 'w+') as f:
            for p in properties:
                f.write('%s="test"\n' % p)
        func()
        for p in properties:
            self.assertEqual(getattr(config, p), 'test')

    def testAllPropsInitializedNone(self):
        config = Config()
        for p in config._properties:
            self.assertIsNone(getattr(config, p))

    def testLoadDefaults(self):
        config = Config()
        config.load_defaults()
        platform, arch, distro, distro_version, num_of_cpus = system_info()
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        data_dir = os.path.abspath(data_dir)
        props = {
            'platform': platform,
            'target_platform': platform,
            'distro': distro,
            'distro_version': distro_version,
            'target_distro': distro,
            'target_distro_version': distro_version,
            'arch': arch,
            'target_arch': arch,
            'num_of_cpus': num_of_cpus,
            'host': None,
            'build': None,
            'target': None,
            'prefix': None,
            'sources': None,
            'local_sources': None,
            'min_osx_sdk_version': None,
            'lib_suffix': '',
            'cache_file': None,
            'toolchain_prefix': None,
            'install_dir': None,
            'packages_prefix': None,
            'data_dir': data_dir,
            'environ_dir': config._relative_path('config'),
            'recipes_dir': config._relative_path('recipes'),
            'packages_dir': config._relative_path('packages'),
            'git_root': cconfig.DEFAULT_GIT_ROOT,
            'wix_prefix': cconfig.DEFAULT_WIX_PREFIX,
            'packager': cconfig.DEFAULT_PACKAGER,
            'py_prefix': 'lib/python%s.%s' % (sys.version_info[0], sys.version_info[1]),
            'allow_parallel_build': cconfig.DEFAULT_ALLOW_PARALLEL_BUILD,
            'use_configure_cache': False,
            'allow_system_libs': True,
            'external_packages': {},
            'external_recipes': {},
            'use_ccache': None,
            'force_git_commit': None,
            'universal_archs': [cconfig.Architecture.X86, cconfig.Architecture.X86_64],
        }
        self.assertEqual(sorted(config._properties), sorted(props.keys()))
        for p, v in props.items():
            self.assertEqual(getattr(config, p), v)

    def testLoadMainConfig(self):
        config = Config()

        tmpconfig = tempfile.NamedTemporaryFile()
        cconfig.DEFAULT_CONFIG_FILE = tmpconfig.name

        config._load_main_config()
        for p in config._properties:
            self.assertIsNone(getattr(config, p))

        config.load_defaults()
        self._checkLoadConfig(config, config._load_main_config, tmpconfig.name, config._properties)

    def testLoadPlatformConfig(self):
        config = Config()
        tmpdir = tempfile.mkdtemp()
        config.environ_dir = tmpdir
        config.load_defaults()
        config._load_platform_config()
        platform_config = os.path.join(tmpdir, '%s.config' % config.target_platform)
        config.load_defaults()
        self._checkLoadConfig(config, config._load_platform_config, platform_config, config._properties)

    def testFindDataDir(self):
        config = Config()
        del os.environ[cconfig.CERBERO_UNINSTALLED]
        config._check_uninstalled()
        self.assertRaises(FatalError, config.load_defaults)

    def testCheckUninstalled(self):
        config = Config()
        del os.environ[cconfig.CERBERO_UNINSTALLED]
        config._check_uninstalled()
        self.assertFalse(config.uninstalled)
        os.environ[cconfig.CERBERO_UNINSTALLED] = '1'
        config._check_uninstalled()
        self.assertTrue(config.uninstalled)

    def testSetupEnv(self):
        config = Config()
        tmpdir = tempfile.mkdtemp()
        config.prefix = tmpdir
        config.load_defaults()
        config.do_setup_env()
        env = config.get_env(tmpdir, os.path.join(tmpdir, 'lib'), config.py_prefix)
        for k, v in env.items():
            self.assertEqual(os.environ[k], v)

    def testParseBadConfigFile(self):
        config = Config()
        tmpfile = tempfile.NamedTemporaryFile()
        with open(tmpfile.name, 'w') as f:
            f.write('nonsense line')
        self.assertRaises(ConfigurationError, config._parse, tmpfile.name)

    def testJoinPath(self):
        config = Config()
        self.assertEqual(config._join_path('/test1', '/test2'), '/test1:/test2')

    def testLoadCommandConfig(self):
        config = Config()
        config.filename = None
        config._load_cmd_config(None)
        self.assertIsNone(config.filename)
        self.assertRaises(ConfigurationError, config._load_cmd_config, '/foo/bar')
        tmpfile = tempfile.NamedTemporaryFile()
        config._load_cmd_config(tmpfile.name)
        self.assertEqual(config.filename, cconfig.DEFAULT_CONFIG_FILE)

    def testLastDefaults(self):
        config = Config()
        config._load_last_defaults()
        cerbero_home = os.path.expanduser('~/cerbero')
        self.assertEqual(config.prefix, os.path.join(cerbero_home, 'dist'))
        self.assertEqual(config.install_dir, config.prefix)
        self.assertEqual(config.sources, os.path.join(cerbero_home, 'sources'))
        self.assertEqual(config.local_sources, os.path.join(cerbero_home, 'sources', 'local'))

    def testRecipesExternalRepositories(self):
        config = Config()
        config.recipes_dir = 'test'
        config.external_recipes = {'test1': ('/path/to/repo', 1), 'test2': ('/path/to/other/repo', 2)}
        expected = {'default': ('test', 0), 'test1': ('/path/to/repo', 1), 'test2': ('/path/to/other/repo', 2)}
        self.assertEqual(config.get_recipes_repos(), expected)

    def testPakcagesExternalRepositories(self):
        config = Config()
        config.packages_dir = 'test'
        config.external_packages = {'test1': ('/path/to/repo', 1), 'test2': ('/path/to/other/repo', 2)}
        expected = {'default': ('test', 0), 'test1': ('/path/to/repo', 1), 'test2': ('/path/to/other/repo', 2)}
        self.assertEqual(config.get_packages_repos(), expected)
