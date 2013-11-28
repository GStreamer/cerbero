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
from cerbero.utils import _, N_, ArgparseArgument, remove_list_duplicates
from cerbero.utils import messages as m


class Fetch(Command):
    doc = N_('Fetch the recipes sources')
    name = 'fetch'

    def __init__(self):
            args = [
                ArgparseArgument('recipes', nargs='*',
                    help=_('list of the recipes to fetch (fetch all if none '
                           'is passed)')),
                ArgparseArgument('--no-deps', action='store_true',
                    default=False, help=_('do not fetch dependencies')),
                ArgparseArgument('--reset-rdeps', action='store_true',
                    default=False, help=_('reset the status of reverse '
                    'dependencies too')),
                ]
            Command.__init__(self, args)

    def run(self, config, args):
        cookbook = CookBook(config)
        fetch_recipes = []
        if not args.recipes:
            fetch_recipes = cookbook.get_recipes_list()
        elif args.no_deps:
            fetch_recipes = [cookbook.get_recipe(x) for x in args.recipes]
        else:
            for recipe in args.recipes:
                fetch_recipes += cookbook.list_recipe_deps(recipe)
            fetch_recipes = remove_list_duplicates (fetch_recipes)
        m.message(_("Fetching the following recipes: %s") %
                  ' '.join([x.name for x in fetch_recipes]))
        to_rebuild = []
        for i in range(len(fetch_recipes)):
            recipe = fetch_recipes[i]
            m.build_step(i + 1, len(fetch_recipes), recipe, 'Fetch')
            recipe.fetch()
            bv = cookbook.recipe_built_version(recipe.name)
            cv = recipe.built_version()
            print bv, cv
            if not cookbook.recipe_needs_build(recipe.name) and bv != cv:
                to_rebuild.append(recipe)
                cookbook.reset_recipe_status(recipe.name)
                if args.reset_rdeps:
                     for r in cookbook.list_recipe_reverse_deps(recipe.name):
                        to_rebuild.append(r)
                        cookbook.reset_recipe_status(r.name)

        if to_rebuild:
            m.message(_("These recipes have been updated and will "
                        "be rebuilt:\n%s") %
                        '\n'.join([x.name for x in to_rebuild]))


register_command(Fetch)
