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
import shutil

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Distro, DistroVersion
from cerbero.utils import shell


class OSXBootstraper (BootstraperBase):

    GCC_BASE_URL = 'https://github.com/downloads/kennethreitz/'\
                   'osx-gcc-installer/'
    GCC_TAR = {
        DistroVersion.OS_X_MOUNTAIN_LION: 'GCC-10.7-v2.pkg',
        DistroVersion.OS_X_LION: 'GCC-10.7-v2.pkg',
        DistroVersion.OS_X_SNOW_LEOPARD: 'GCC-10.6.pkg'}
    CPANM_URL = 'https://raw.github.com/miyagawa/cpanminus/master/cpanm'

    def start(self):
        self._install_perl_deps()
        # FIXME: enable it when buildbots are properly configured
        return
        tar = self.GCC_TAR[self.config.distro_version]
        url = os.path.join(self.GCC_BASE_URL, tar)
        pkg = os.path.join(self.config.local_sources, tar)
        shell.download(url, pkg, check_cert=False)
        shell.call('sudo installer -pkg %s -target /' % pkg)

    def _install_perl_deps(self):
        # Install cpan-minus, a zero-conf CPAN wrapper
        cpanm_installer = tempfile.NamedTemporaryFile().name
        shell.download(self.CPANM_URL, cpanm_installer)
        shell.call('chmod +x %s' % cpanm_installer)
        # Install XML::Parser, required for intltool
        shell.call("sudo %s XML::Parser" % cpanm_installer)



def register_all():
    register_bootstraper(Distro.OS_X, OSXBootstraper)
