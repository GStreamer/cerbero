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

from cerbero.config import Config
from cerbero.bootstrap import BootstrapperBase
from cerbero.build.oven import Oven
from cerbero.build.cookbook import CookBook
from cerbero.commands.fetch import Fetch
from cerbero.utils import _, shell
from cerbero.errors import FatalError, ConfigurationError
from cerbero.enums import Platform, Architecture, DistroVersion


class BuildTools (BootstrapperBase, Fetch):

    BUILD_TOOLS = ['automake', 'autoconf', 'libtool', 'pkg-config',
                   'orc-tool', 'gettext-m4', 'meson']
    PLAT_BUILD_TOOLS = {
        Platform.DARWIN: ['intltool', 'sed', 'gperf', 'bison', 'flex',
                          'moltenvk-tools'],
        # MSYS already ships with bison, flex, m4 on Windows
        Platform.WINDOWS: ['intltool', 'gperf', 'nasm'],
        Platform.LINUX: ['intltool-m4'],
    }

    def __init__(self, config, offline):
        BootstrapperBase.__init__(self, config, offline)

        if self.config.target_platform in (Platform.IOS, Platform.WINDOWS):
            # Used by ffmpeg and x264 on iOS, and by openn264 on Windows-ARM64
            self.BUILD_TOOLS.append('gas-preprocessor')

        if self.config.platform == Platform.WINDOWS:
            # We must not run automake/autoconf/libtoolize when building on
            # windows because they hang on the Windows CI runner
            self.BUILD_TOOLS.remove('gettext-m4')
            self.BUILD_TOOLS.remove('automake')
            self.BUILD_TOOLS.remove('autoconf')
            self.BUILD_TOOLS.remove('libtool')

        if self.config.variants.uwp:
            # UWP config does not build any autotools recipes
            self.PLAT_BUILD_TOOLS[Platform.WINDOWS].remove('intltool')
            self.PLAT_BUILD_TOOLS[Platform.WINDOWS].remove('gperf')

        if self.config.target_platform != Platform.LINUX and not \
           self.config.prefix_is_executable():
            # For glib-mkenums and glib-genmarshal
            self.BUILD_TOOLS.append('glib-tools')
        self.BUILD_TOOLS += self.config.extra_build_tools
        self._setup_env()

    def check_build_tools(self):
        '''
        Check whether the build tools we have are new enough, and if not, build
        them ourselves. On Windows, we always build nasm ourselves, and we tell
        the user to install CMake using the installer.
        '''
        ret = []
        if self.config.platform in (Platform.LINUX, Platform.DARWIN):
            # need cmake > 3.10.2 for out-of-source-tree builds.
            tool, found, newer = shell.check_tool_version('cmake' ,'3.10.2', env=None)
            if not newer:
                ret.append('cmake')
            # dav1d requires nasm >=2.13.02
            tool, found, newer = shell.check_tool_version('nasm', '2.13.02', env=None)
            if not newer:
                ret.append('nasm')
        return ret

    def _setup_env(self):
        # Use a common prefix for the build tools for all the configurations
        # so that it can be reused
        config = Config()
        config.prefix = self.config.build_tools_prefix
        config.home_dir = self.config.home_dir
        config.local_sources = self.config.local_sources
        config.load()

        config.prefix = self.config.build_tools_prefix
        config.build_tools_prefix = self.config.build_tools_prefix
        config.sources = self.config.build_tools_sources
        config.build_tools_sources = self.config.build_tools_sources
        config.logs = self.config.build_tools_logs
        config.build_tools_logs = self.config.build_tools_logs
        config.cache_file = self.config.build_tools_cache
        config.build_tools_cache = self.config.build_tools_cache
        config.external_recipes = self.config.external_recipes
        config.extra_mirrors = self.config.extra_mirrors
        config.cached_sources = self.config.cached_sources
        config.vs_install_path = self.config.vs_install_path
        config.vs_install_version = self.config.vs_install_version

        if config.toolchain_prefix and not os.path.exists(config.toolchain_prefix):
            os.makedirs(config.toolchain_prefix)
        if not os.path.exists(config.prefix):
            os.makedirs(config.prefix)
        if not os.path.exists(config.sources):
            os.makedirs(config.sources)
        if not os.path.exists(config.logs):
            os.makedirs(config.logs)

        config.do_setup_env()
        self.cookbook = CookBook(config, offline=self.offline)
        self.recipes = self.BUILD_TOOLS
        self.recipes += self.PLAT_BUILD_TOOLS.get(self.config.platform, [])

    def start(self, jobs=0):
        # Check and these at the last minute because we may have installed them
        # in system bootstrap
        self.recipes += self.check_build_tools()
        oven = Oven(self.recipes, self.cookbook, jobs=jobs)
        oven.start_cooking()

    def fetch_recipes(self, jobs):
        Fetch.fetch(self.cookbook, self.recipes, False, False, False, False, jobs)
