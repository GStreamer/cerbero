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
from cerbero.utils import _
from cerbero.errors import FatalError, ConfigurationError


class BuildTools (BootstrapperBase):

    BUILD_TOOLS = ['automake', 'autoconf', 'm4', 'libtool', 'pkg-config',
                   'orc-tool', 'gettext-m4', 'gettext-tools']
    PLAT_BUILD_TOOLS = {
        Platform.DARWIN: ['intltool', 'yasm', 'bison', 'flex'],
        Platform.WINDOWS: ['intltool', 'yasm'],
        Platform.LINUX: ['intltool-m4'],
    }

    def __init__(self, config):
        BootstrapperBase.__init__(self, config)

        # if cross-compiling or not on linux, make sure we have gtk-doc
        if self.config.target_platform != Platform.LINUX or\
           self.config.cross_compiling():
            self.BUILD_TOOLS.append('gtk-doc-lite')

        if self.config.platform == Platform.WINDOWS:
            self.BUILD_TOOLS.remove('m4')
            self.BUILD_TOOLS.append('gperf')
        if self.config.platform == Platform.DARWIN:
            self.BUILD_TOOLS.append('gperf')
            self.BUILD_TOOLS.append('cmake')
            self.BUILD_TOOLS.insert(0, 'xz')
        if self.config.platform == Platform.LINUX:
            if self.config.distro_version == DistroVersion.UBUNTU_LUCID or \
                self.config.distro_version == DistroVersion.DEBIAN_SQUEEZE or \
                self.config.distro_version == DistroVersion.DEBIAN_WHEEZY:
                # x264 requires yasm >= 1.2
                self.BUILD_TOOLS.append('yasm')
            if self.config.distro_version in [DistroVersion.REDHAT_6,
                                              DistroVersion.AMAZON_LINUX]:
                self.BUILD_TOOLS.append('cmake')
        if self.config.target_platform == Platform.IOS:
            self.BUILD_TOOLS.append('gas-preprocessor')
        if self.config.distro_version in [DistroVersion.UBUNTU_LUCID,
                                          DistroVersion.UBUNTU_NATTY]:
            self.BUILD_TOOLS.append('glib-tools')
        if self.config.platform != Platform.LINUX and not \
           self.config.prefix_is_executable():
            # For glib-mkenums and glib-genmarshal
            self.BUILD_TOOLS.append('glib-tools')
        self.BUILD_TOOLS += self.config.extra_build_tools

    def start(self):
        # Use a common prefix for the build tools for all the configurations
        # so that it can be reused
        config = Config()
        os.environ.clear()
        os.environ.update(self.config._pre_environ)
        config.prefix = self.config.build_tools_prefix
        config.home_dir = self.config.home_dir
        config.load()

        config.prefix = self.config.build_tools_prefix
        config.build_tools_prefix = self.config.build_tools_prefix
        config.sources = self.config.build_tools_sources
        config.build_tools_sources = self.config.build_tools_sources
        config.cache_file = self.config.build_tools_cache
        config.build_tools_cache = self.config.build_tools_cache
        config.external_recipes = self.config.external_recipes

        if config.toolchain_prefix and not os.path.exists(config.toolchain_prefix):
            raise ConfigurationError(_("Please run bootstrap without any '-c' arguments first to setup build-tools for this machine"))
        if not os.path.exists(config.prefix):
            os.makedirs(config.prefix)
        if not os.path.exists(config.sources):
            os.makedirs(config.sources)

        config.do_setup_env()
        cookbook = CookBook(config)
        recipes = self.BUILD_TOOLS
        recipes += self.PLAT_BUILD_TOOLS.get(self.config.platform, [])
        oven = Oven(recipes, cookbook)
        oven.start_cooking()
        self.config.do_setup_env()
