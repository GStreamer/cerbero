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
from cerbero.enums import Platform, Architecture, DistroVersion

from pathlib import PurePath

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
            tool, found, newer = shell.check_tool_version('nasm', '2.13.02', env=None, version_arg='-v')
            if not newer:
                ret.append('nasm')
        return ret

    def _setup_env(self):
        self.cookbook = CookBook(self.config.build_tools_config, offline=self.offline)
        self.recipes = self.BUILD_TOOLS
        self.recipes += self.PLAT_BUILD_TOOLS.get(self.config.platform, [])

    def insert_python_site(self):
        try:
            import setuptools.version as stv
        except ImportError:
            return

        version = stv.__version__.split('.', 1)
        if len(version) < 1 or int(version[0]) < 49:
            return

        m.warning('detected setuptools >= 49.0.0, installing fallback site.py file. '
            'See https://github.com/pypa/setuptools/issues/2295')

        # Since python-setuptools 49.0.0, site.py is not installed by
        # easy_install/setup.py anymore which breaks python installs outside
        # the system prefix.
        # https://github.com/pypa/setuptools/issues/2295
        #
        # Install the previously installed site.py ourselves as a workaround
        config = self.cookbook.get_config()

        py_prefix = sysconfig.get_path('purelib', 'posix_prefix', vars={'base': ''})
        # Must strip \/ to ensure that the path is relative
        py_prefix = PurePath(config.prefix) / PurePath(py_prefix.strip('\\/'))
        src_file = os.path.join(os.path.dirname(__file__), 'site-patch.py')
        shutil.copy(src_file, py_prefix / 'site.py')

    def setup_venv(self):
        venv.create(self.config.build_tools_prefix, with_pip=True)
        if self.config.platform == Platform.WINDOWS:
            # Python insists on using Scripts instead of bin on Windows for
            # scripts. Insist back, and use bin again.
            scriptsdir = os.path.join(self.config.build_tools_prefix, 'Scripts')
            bindir = os.path.join(self.config.build_tools_prefix, 'bin')
            os.mkdir(bindir)
            for f in glob.glob('*', root_dir=scriptsdir):
                shutil.move(os.path.join(scriptsdir, f), bindir)
            os.rmdir(scriptsdir)

    def start(self, jobs=0):
        if sys.version_info >= (3, 11, 0):
            self.setup_venv()
        else:
            self.insert_python_site()
        # Check and these at the last minute because we may have installed them
        # in system bootstrap
        self.recipes += self.check_build_tools()
        oven = Oven(self.recipes, self.cookbook, jobs=jobs)
        oven.start_cooking()

    def fetch_recipes(self, jobs):
        self.recipes += self.check_build_tools()
        Fetch.fetch(self.cookbook, self.recipes, False, False, False, False, jobs)
