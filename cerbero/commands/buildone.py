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


#from cerbero.oven import Oven
from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.build.oven import Oven
from cerbero.utils import _, N_, ArgparseArgument


class BuildOne(Command):
    doc = N_('Build or rebuild a single recipe without its dependencies')
    name = 'buildone'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('recipe', nargs=1,
                             help=_('name of the recipe to build')),
            ])

    def run(self, config, args):
        cookbook = CookBook(config)
        recipe_name = args.recipe[0]

        recipe = cookbook.get_recipe(recipe_name)

        oven = Oven(recipe, cookbook, force=True, no_deps=True)
        oven.start_cooking()

register_command(BuildOne)
