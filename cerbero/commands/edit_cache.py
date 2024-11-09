# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2019, Fluendo, S.A.
#  Author: Pablo Marcos Oltra <pmarcos@fluendo.com>, Fluendo, S.A.
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
from cerbero.build.cookbook import CookBook, RecipeStatus
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m


class EditCache(Command):
    # The edit-cache command takes the `RecipeStatus` class and analyzes its
    # attributes using introspection to expose its members and allow modifying
    # them trough the command line. The type of the arguments is the same as the
    # ones in `RecipeStatus` except for the boolean values, that are passed
    # using a string containing either "True" or "False". This is done for
    # consistency and to avoid having two different arguments such as --feature
    # and --no-feature
    doc = N_('View and edit the local cache')
    name = 'edit-cache'

    def __init__(self):
        self.recipe_status = RecipeStatus('filepath')
        self.recipe_attributes = list(set(dir(self.recipe_status)) - set(dir(RecipeStatus)))
        arguments = [
            ArgparseArgument('recipe', nargs='*', help=_('Recipe to work with')),
            ArgparseArgument('--bootstrap', action='store_true', default=False, help=_("Use bootstrap's cache file")),
            ArgparseArgument('--touch', action='store_true', default=False, help=_('Touch recipe modifying its mtime')),
            ArgparseArgument(
                '--reset', action='store_true', default=False, help=_('Clean entirely the cache for the recipe')
            ),
        ]

        for attr in self.recipe_attributes:
            attr_nargs = '*' if isinstance(getattr(self.recipe_status, attr), list) else None
            attr_type = type(getattr(self.recipe_status, attr))
            arg_type = str if attr_type is bool or attr_type is list else attr_type
            arguments.append(ArgparseArgument('--' + attr, nargs=attr_nargs, type=arg_type, help=N_('Modify ' + attr)))
        Command.__init__(self, arguments)

    def run(self, config, args):
        if args.bootstrap:
            config.cache_file = config.build_tools_cache
        cookbook = CookBook(config, reset_status=False)

        is_modifying = args.touch or args.reset
        if not is_modifying:
            for attr in self.recipe_attributes:
                if getattr(args, attr) is not None:
                    is_modifying = True
                    break

        global_status = cookbook.status
        recipes = args.recipe or list(global_status.keys())

        m.message(
            '{} cache values for recipes: {}'.format('Showing' if not is_modifying else 'Modifying', ', '.join(recipes))
        )

        for recipe in recipes:
            if recipe not in global_status.keys():
                m.error('Recipe {} not in cookbook'.format(recipe))
                continue
            status = global_status[recipe]
            print('[{}]'.format(recipe))
            text = ''
            if is_modifying:
                text = 'Before\n'
            print('{}{}\n'.format(text, status))
            if is_modifying:
                if args.reset:
                    cookbook.reset_recipe_status(recipe)
                    m.message('Recipe {} reset'.format(recipe))
                else:
                    if args.touch:
                        status.touch()

                    for attr in self.recipe_attributes:
                        var = getattr(args, attr)
                        if var is not None:
                            if isinstance(getattr(self.recipe_status, attr), bool):
                                if var.lower() == 'true':
                                    var = True
                                elif var.lower() == 'false':
                                    var = False
                                else:
                                    m.error('Error: Attribute "{}" needs to be either "True" or "False"'.format(attr))
                                    return
                            setattr(status, attr, var)

                    cookbook.save()
                    print('After\n{}\n'.format(status))


register_command(EditCache)
