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

class OSXBootstrapper (BootstrapperBase):


    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline)

    async def start(self, jobs=0):
        # skip system package install if not needed
        if not self.config.distro_packages_install:
            return


def register_all():
    register_system_bootstrapper(Distro.OS_X, OSXBootstrapper)
