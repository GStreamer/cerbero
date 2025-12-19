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
from unittest.mock import patch

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
        config.config_dir = tmpdir
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
        config.load_defaults()
        config.filename = None
        config._load_cmd_config(None)
        self.assertIsNone(config.filename)
        self.assertRaises(ConfigurationError, config._load_cmd_config, ['/foo/bar'])

    def testLoadCommandConfigOverrideVariants(self):
        config = Config()
        config.load_defaults()
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

    def testEnvironDirDeprecation(self):
        """Test that environ_dir is deprecated and properly mapped to config_dir"""
        config = Config()
        config.load_defaults()

        # Test 1: environ_dir attribute should not exist
        with self.assertRaises(AttributeError):
            _ = config.environ_dir

        # Test 2: Setting environ_dir in config file should emit warning and set config_dir
        tmpconfig = tempfile.NamedTemporaryFile(mode='w+t', suffix='.cbc', delete=False)
        try:
            tmpconfig.write('environ_dir = "/custom/config/path"\n')
            tmpconfig.flush()
            tmpconfig.close()

            # Mock the deprecation function to capture the call
            with patch('cerbero.utils.messages.deprecation') as mock_deprecation:
                config._parse(tmpconfig.name, reset=False)

                # Verify deprecation warning was called
                mock_deprecation.assert_called_once()
                call_args = mock_deprecation.call_args[0][0]
                self.assertIn('environ_dir', call_args)
                self.assertIn('deprecated', call_args)
                self.assertIn('config_dir', call_args)

            # Verify config_dir was set from environ_dir
            self.assertEqual(config.config_dir, '/custom/config/path')

            # Verify environ_dir attribute still doesn't exist
            with self.assertRaises(AttributeError):
                _ = config.environ_dir

        finally:
            os.unlink(tmpconfig.name)

    def testConfigDirAccessible(self):
        """Test that config_dir is accessible and works normally"""
        config = Config()
        config.load_defaults()

        # config_dir should be accessible
        self.assertIsNotNone(config.config_dir)
        self.assertTrue(os.path.exists(config.config_dir))

        # Should be able to set it directly
        old_config_dir = config.config_dir
        config.config_dir = '/tmp/test'
        self.assertEqual(config.config_dir, '/tmp/test')
        config.config_dir = old_config_dir
