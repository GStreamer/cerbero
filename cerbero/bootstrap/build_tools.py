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

from cerbero.config import Config, Platform, DistroVersion
from cerbero.bootstrap import BootstrapperBase
from cerbero.build.oven import Oven
from cerbero.build.cookbook import CookBook
from cerbero.commands.fetch import Fetch
from cerbero.utils import _
from cerbero.errors import FatalError, ConfigurationError


class BuildTools (BootstrapperBase, Fetch):

    # XXX: Remove vala-m4 and introspection-m4 once all GNOME recipes are
    # ported to Meson, and revisit gtk-doc-lite too.
    BUILD_TOOLS = ['automake', 'autoconf', 'm4', 'libtool', 'gettext-tools',
                   'pkg-config', 'orc-tool', 'gettext-m4', 'vala-m4',
                   'gobject-introspection-m4', 'gtk-doc-lite', 'meson']
    PLAT_BUILD_TOOLS = {
        Platform.DARWIN: ['intltool', 'nasm', 'bison', 'flex', 'moltenvk-tools'],
        Platform.WINDOWS: ['intltool', 'nasm'],
        Platform.LINUX: ['intltool-m4'],
    }

    def __init__(self, config, offline):
        BootstrapperBase.__init__(self, config, offline)

        if self.config.platform == Platform.WINDOWS:
            self.BUILD_TOOLS.remove('m4')
            self.BUILD_TOOLS.append('gperf')
        if self.config.platform == Platform.DARWIN:
            self.BUILD_TOOLS.append('gperf')
            self.BUILD_TOOLS.append('cmake')
        if self.config.platform == Platform.LINUX:
            if self.config.distro_version in [DistroVersion.REDHAT_6,
                                              DistroVersion.AMAZON_LINUX]:
                self.BUILD_TOOLS.append('cmake')
            # dav1d requires nasm >=2.13.02
            if self.config.distro_version.startswith('ubuntu') and self.config.distro_version < DistroVersion.UBUNTU_BIONIC:
                self.BUILD_TOOLS.append('nasm')
            elif self.config.distro_version.startswith('debian') and self.config.distro_version < DistroVersion.DEBIAN_BUSTER:
                self.BUILD_TOOLS.append('nasm')
            elif self.config.distro_version in [DistroVersion.REDHAT_6,
                                                DistroVersion.REDHAT_7,
                                                DistroVersion.AMAZON_LINUX]:
                self.BUILD_TOOLS.append('nasm')
        if self.config.target_platform == Platform.IOS:
            self.BUILD_TOOLS.append('gas-preprocessor')
        if self.config.target_platform != Platform.LINUX and not \
           self.config.prefix_is_executable():
            # For glib-mkenums and glib-genmarshal
            self.BUILD_TOOLS.append('glib-tools')
        self.BUILD_TOOLS += self.config.extra_build_tools

        self._setup_env()

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
        config.cache_file = self.config.build_tools_cache
        config.build_tools_cache = self.config.build_tools_cache
        config.external_recipes = self.config.external_recipes
        config.extra_mirrors = self.config.extra_mirrors
        config.cached_sources = self.config.cached_sources

        if config.toolchain_prefix and not os.path.exists(config.toolchain_prefix):
            os.makedirs(config.toolchain_prefix)
        if not os.path.exists(config.prefix):
            os.makedirs(config.prefix)
        if not os.path.exists(config.sources):
            os.makedirs(config.sources)

        config.do_setup_env()
        self.cookbook = CookBook(config, offline=self.offline)
        self.recipes = self.BUILD_TOOLS
        self.recipes += self.PLAT_BUILD_TOOLS.get(self.config.platform, [])

    def start(self, jobs=0):
        oven = Oven(self.recipes, self.cookbook, jobs=jobs)
        oven.start_cooking()

    def fetch_recipes(self, jobs):
        Fetch.fetch(self.cookbook, self.recipes, False, False, False, False, jobs)
