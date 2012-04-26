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
import subprocess

from cerbero.config import Platform
from cerbero.commands import Command, register_command
from cerbero.utils import N_


class Shell(Command):
    doc = N_('Starts a shell with the build environment')
    name = 'shell'

    def __init__(self):
        Command.__init__(self, [])

    def run(self, config, args):
        if config.platform == Platform.WINDOWS:
            # $MINGW_PREFIX/home/username
            msys = os.path.join(os.path.expanduser('~'),
                                '..', '..', 'msys.bat')
            subprocess.check_call('%s -noxvrt' % msys)
        else:
            shell = os.environ.get('SHELL', '/bin/bash')
            os.execlp(shell, shell)

register_command(Shell)
