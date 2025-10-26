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


from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.utils import N_, shell


class Shell(Command):
    doc = N_('Starts a shell with the build environment')
    name = 'shell'

    def run(self, config, args):
        # Load the cookbook which will parse all recipes and update config.bash_completions
        # We don't care about errors while loading recipes, which can happen
        # just because of the current configuration not matching what the
        # recipe supports
        CookBook(config, skip_errors=True)
        env = config.env.copy()
        shell.enter_build_environment(
            config.target_platform,
            config.target_arch,
            config.distro,
            sourcedir=None,
            env=env,
            bash_completions=config.bash_completions,
        )


register_command(Shell)
