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

import logging

from cerbero.commands import Command, register_command
from cerbero.cookbook import CookBook
from cerbero.utils import _, N_, ArgparseArgument


class Deps(Command):
    doc = N_('List the dependencies of a recipe')
    name = 'deps'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('recipe', nargs=1,
                             help=_('name of the recipe')),
            ])

    def run(self, config, args):
        cookbook = CookBook.load(config)
        recipe_name = args.recipe[0]

        for recipe in cookbook.list_recipe_deps(recipe_name):
            # Don't print the recipe we asked for
            if recipe.name == recipe_name:
                continue
            logging.info(recipe.name)

register_command(Deps)
