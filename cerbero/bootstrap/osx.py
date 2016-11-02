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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_bootstrapper
from cerbero.config import Distro, DistroVersion
from cerbero.utils import shell


class OSXBootstrapper (BootstrapperBase):

    CPANM_URL = 'https://raw.github.com/miyagawa/cpanminus/master/cpanm'

    def start(self):
        # skip system package install if not needed
        if not self.config.distro_packages_install:
            return
        self._install_perl_deps()

    def _install_perl_deps(self):
        # Install cpan-minus, a zero-conf CPAN wrapper
        cpanm_installer = tempfile.NamedTemporaryFile()
        shell.download(self.CPANM_URL, cpanm_installer.name, overwrite=True)
        shell.call('chmod +x %s' % cpanm_installer.name)
        # Install XML::Parser, required for intltool
        shell.call("sudo %s XML::Parser" % cpanm_installer.name)
        cpanm_installer.close()



def register_all():
    register_bootstrapper(Distro.OS_X, OSXBootstrapper)
