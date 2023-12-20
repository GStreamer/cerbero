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


class Deps(Command):
    doc = N_('List the dependencies of a recipe')
    name = 'deps'

    def __init__(self):
        Command.__init__(
            self,
            [
                ArgparseArgument('recipe', nargs=1, help=_('name of the recipe')),
                ArgparseArgument(
                    '--all',
                    action='store_true',
                    default=False,
                    help=_('list all dependencies, including the ' 'build ones'),
                ),
                ArgparseArgument(
                    '--graph', action='store_true', default=False, help=_('show the depencies as a graph')
                ),
            ],
        )

    def run(self, config, args):
        cookbook = CookBook(config)
        recipe_name = args.recipe[0]
        all_deps = args.all
        graph = args.graph

        if all_deps:
            recipes = cookbook.list_recipe_deps(recipe_name)
        else:
            recipes = [cookbook.get_recipe(x) for x in cookbook.get_recipe(recipe_name).list_deps()]

        if len(recipes) == 0:
            m.message(_('%s has 0 dependencies') % recipe_name)
            return
        if not graph:
            for recipe in recipes:
                # Don't print the recipe we asked for
                if recipe.name == recipe_name:
                    continue
                m.message(recipe.name)
        else:

            def print_dep(cookbook, recipe, level=0, already_shown=[]):
                m.message('%s%s' % (' ' * 3 * level, recipe.name))
                already_shown.append(recipe)
                for r in [cookbook.get_recipe(x) for x in recipe.list_deps()]:
                    if r not in already_shown:
                        print_dep(cookbook, r, level + 1, already_shown)
                    elif not r.name == recipe.name:
                        m.message('%s(%s)' % (' ' * 3 * (level + 1), r.name))

            print_dep(cookbook, cookbook.get_recipe(recipe_name))


register_command(Deps)
