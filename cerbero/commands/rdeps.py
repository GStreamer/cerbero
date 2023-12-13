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
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m


class RDeps(Command):
    doc = N_('List the reverse dependencies of a recipe')
    name = 'rdeps'

    def __init__(self):
        Command.__init__(
            self,
            [
                ArgparseArgument('recipe', nargs=1, help=_('name of the recipe')),
            ],
        )

    def run(self, config, args):
        cookbook = CookBook(config)
        recipe_name = args.recipe[0]

        recipes = cookbook.list_recipe_reverse_deps(recipe_name)
        if len(recipes) == 0:
            m.error(_('%s has 0 reverse dependencies') % recipe_name)
            return
        for recipe in recipes:
            m.message(recipe.name)


register_command(RDeps)
