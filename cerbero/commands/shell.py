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

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.utils import _, N_, shell, ArgparseArgument, add_system_libs

class Shell(Command):
    doc = N_('Starts a shell with the build environment')
    name = 'shell'

    def __init__(self):
        args = [
            ArgparseArgument('--use-system-libs', action='store_true',
                    default=False,
                    help=_('add system paths to PKG_CONFIG_PATH')),
        ]

        Command.__init__(self, args)

    def run(self, config, args):
        # Load the cookbook which will parse all recipes and update config.bash_completions
        cookbook = CookBook(config)
        env = config.env.copy()
        if args.use_system_libs:
            add_system_libs(config, env)

        shell.enter_build_environment(config.target_platform,
                config.target_arch, sourcedir=None, env=env,
                bash_completions=config.bash_completions)


register_command(Shell)
