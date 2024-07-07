#!/usr/bin/env python3
#
#       ios.py
#
# Copyright (C) 2013 Thibault Saunier <thibaul.saunier@collabora.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.

import os
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_toolchain_bootstrapper
from cerbero.enums import Distro, Architecture


class IOSBootstrapper(BootstrapperBase):
    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline)

    async def start(self, jobs=0):
        if self.config.arch == Architecture.ARM64 and not os.path.exists('/Library/Apple/usr/lib/libRosettaAot.dylib'):
            m.message('Installing rosetta needed for some package installation scripts')
            shell.new_call(['/usr/sbin/softwareupdate', '--install-rosetta', '--agree-to-license'])


def register_all():
    register_toolchain_bootstrapper(Distro.IOS, IOSBootstrapper)
