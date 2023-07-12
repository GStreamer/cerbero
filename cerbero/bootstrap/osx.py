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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_system_bootstrapper
from cerbero.config import Distro
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.enums import Architecture

CPANM_VERSION = '1.7044'
CPANM_URL_TPL = 'https://raw.githubusercontent.com/miyagawa/cpanminus/{}/cpanm'
CPANM_CHECKSUM = '22b92506243649a73cfb55c5990cedd24cdbb20b15b4530064d2496d94d1642b'

class OSXBootstrapper (BootstrapperBase):


    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline)
        url = CPANM_URL_TPL.format(CPANM_VERSION)
        self.fetch_urls.append((url, None, CPANM_CHECKSUM))

    async def start(self, jobs=0):
        # skip system package install if not needed
        if not self.config.distro_packages_install:
            return
        self._install_perl_deps()
        if self.config.arch == Architecture.ARM64:
            m.message("Installing rosetta needed for some package installation scripts")
            shell.new_call(['/usr/sbin/softwareupdate', '--install-rosetta', '--agree-to-license'])

    def _install_perl_deps(self):
        cpanm_installer = os.path.join(self.config.local_sources, 'cpanm')
        shell.new_call(['chmod', '+x', cpanm_installer])
        # Install XML::Parser, required for intltool
        cmd = ['sudo', cpanm_installer, 'XML::Parser']
        m.message("Installing XML::Parser, may require a password for running \'" + " ".join(cmd) + "\'")
        shell.new_call(cmd, interactive=True)


def register_all():
    register_system_bootstrapper(Distro.OS_X, OSXBootstrapper)
