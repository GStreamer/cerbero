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
import venv
import glob
import sysconfig
import shutil

from cerbero.config import Config
from cerbero.bootstrap import BootstrapperBase
from cerbero.build.oven import Oven
from cerbero.build.cookbook import CookBook
from cerbero.commands.fetch import Fetch
from cerbero.utils import _, shell
from cerbero.utils import messages as m
from cerbero.errors import FatalError, ConfigurationError
from cerbero.enums import Platform, Distro

from pathlib import PurePath

class BuildTools (BootstrapperBase, Fetch):

    BUILD_TOOLS = ['automake', 'autoconf', 'libtool', 'pkg-config',
                   'orc', 'gettext-m4', 'meson']
    PLAT_BUILD_TOOLS = {
        Platform.DARWIN: ['intltool', 'sed', 'gperf', 'bison', 'flex',
                          'moltenvk-tools'],
        Platform.WINDOWS: ['nasm'],
        Platform.LINUX: ['intltool-m4'],
    }

    def __init__(self, config, offline):
        BootstrapperBase.__init__(self, config, offline)

        if self.config.variants.rust:
            self.BUILD_TOOLS.append('cargo-c')

        if self.config.target_platform in (Platform.IOS, Platform.WINDOWS):
            # Used by ffmpeg and x264 on iOS, and by openh264 on Windows-ARM64
            self.BUILD_TOOLS.append('gas-preprocessor')

        if self.config.platform == Platform.WINDOWS:
            # We must not run automake/autoconf/libtoolize when building on
            # windows because they hang on the Windows CI runner
            self.BUILD_TOOLS.remove('gettext-m4')
            self.BUILD_TOOLS.remove('automake')
            self.BUILD_TOOLS.remove('autoconf')
            self.BUILD_TOOLS.remove('libtool')

            if self.config.distro == Distro.MSYS:
                self.PLAT_BUILD_TOOLS[Platform.WINDOWS].append('gperf')
                # UWP config does not build any autotools recipes
                if not self.config.variants.uwp:
                    self.PLAT_BUILD_TOOLS[Platform.WINDOWS].append('intltool')

        if self.config.target_platform != Platform.LINUX and not \
           self.config.prefix_is_executable():
            # For glib-mkenums and glib-genmarshal
            self.BUILD_TOOLS.append('glib-tools')
        if self.config.target_platform == Platform.WINDOWS and \
           self.config.platform == Platform.LINUX:
                self.BUILD_TOOLS.append('wix')

        self.BUILD_TOOLS += self.config.extra_build_tools
        self._setup_env()

    def check_build_tools(self):
        '''
        Check whether the build tools we have are new enough, and if not, build
        them ourselves. On Windows, we always build nasm ourselves, and we tell
        the user to install CMake using the installer.
        '''
        ret = []
        tools = {
            # meson requires ninja >=1.8.2
            'ninja': ('1.8.2', None),
        }
        if self.config.platform in (Platform.LINUX, Platform.DARWIN):
            tools.update({
                # need cmake > 3.10.2 for out-of-source-tree builds.
                'cmake': ('3.10.2', None),
                # dav1d requires nasm >=2.13.02
                'nasm': ('2.13.02', '-v'),
            })
        for tool, (version, arg) in tools.items():
            _, _, newer = shell.check_tool_version(tool, version, env=None, version_arg=arg)
            if newer:
                self.config.system_build_tools.append(tool)
            else:
                ret.append(tool)
        return ret

    def _setup_env(self):
        self.cookbook = CookBook(self.config.build_tools_config, offline=self.offline)
        self.recipes = self.BUILD_TOOLS
        self.recipes += self.PLAT_BUILD_TOOLS.get(self.config.platform, [])

    def setup_venv(self):
        # Python relies on symlinks to work on macOS.
        # See e.g.
        # https://github.com/python-poetry/install.python-poetry.org/issues/24#issuecomment-1226504499
        venv.create(self.config.build_tools_prefix, symlinks=self.config.platform != Platform.WINDOWS, with_pip=True)
        if self.config.platform == Platform.WINDOWS:
            # Python insists on using Scripts instead of bin on Windows for
            # scripts. Insist back, and use bin again.
            scriptsdir = os.path.join(self.config.build_tools_prefix, 'Scripts')
            bindir = os.path.join(self.config.build_tools_prefix, 'bin')
            os.makedirs(bindir, exist_ok=True)
            for f in glob.glob('*', root_dir=scriptsdir):
                tof = os.path.join(bindir, f)
                if os.path.isfile(tof):
                    os.remove(tof)
                shutil.move(os.path.join(scriptsdir, f), tof)
            os.rmdir(scriptsdir)
        python = os.path.join(self.config.build_tools_prefix, 'bin', 'python')
        shell.new_call([python, '-m', 'pip', 'install', 'setuptools'])

    async def start(self, jobs=0):
        python = os.path.join(self.config.build_tools_prefix, 'bin', 'python')
        if self.config.platform == Platform.WINDOWS:
            python += '.exe'
        if not os.path.exists(python):
            self.setup_venv()
        # Check and these at the last minute because we may have installed them
        # in system bootstrap
        self.recipes += self.check_build_tools()
        oven = Oven(self.recipes, self.cookbook, jobs=jobs)
        await oven.start_cooking()

    async def fetch_recipes(self, jobs):
        self.recipes += self.check_build_tools()
        await Fetch.fetch(self.cookbook, self.recipes, False, False, False, False, jobs)
