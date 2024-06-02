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
import tempfile
import unittest

from cerbero import config as cconfig
from cerbero.errors import FatalError, ConfigurationError

Config = cconfig.Config

CONFIG = """
variants.override(['alsa', 'x11'])
"""


class ConfigTest(unittest.TestCase):
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
        for p in config._properties:
            self.assertTrue(hasattr(config, p))

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

    def testParseBadConfigFile(self):
        config = Config()
        tmpfile = tempfile.NamedTemporaryFile()
        with open(tmpfile.name, 'wt') as f:
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
        self.assertRaises(ConfigurationError, config._load_cmd_config, ['/foo/bar'])

    def testLoadCommandConfigOverrideVariants(self):
        config = Config()
        self.assertFalse(config.variants.alsa)
        tmpconfig = tempfile.NamedTemporaryFile(mode='w+t')
        tmpconfig.write(CONFIG)
        tmpconfig.flush()
        config._load_cmd_config([tmpconfig.name])
        # config.load([tmpconfig.name])
        self.assertTrue(config.variants.alsa)

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
