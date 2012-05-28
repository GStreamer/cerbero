# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Collabora Ltd.
#     Author: Nicolas Dufresne <nicolas.dufresne@collabora.co.uk>
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
from cerbero.errors import CommandError
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m
from cerbero.packages.packagesstore import PackagesStore


class CheckPackage(Command):
    doc = N_('Run checks on a given package')
    name = 'checkpackage'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('package', nargs=1,
                              help=_('name of the package to run checks on')),
            ])

    def run(self, config, args):
        cookbook = CookBook(config)
        failed = []
        p_name = args.package[0]

        store = PackagesStore(config)
        p = store.get_package(p_name)
        ordered_recipes = map(lambda x: cookbook.get_recipe(x),
                    p.recipes_dependencies())

        for recipe in ordered_recipes:
            if cookbook.recipe_needs_build(recipe.name):
                raise CommandError(_("Recipe %s is not built yet" % recipe.name))

        for recipe in ordered_recipes:
            # call step function
            stepfunc = None
            try:
                stepfunc = getattr(recipe, 'check')
            except:
                m.message('%s has no check step, skipped' % recipe.name)

            if stepfunc:
                try:
                    m.message('Running checks for recipe %s' % recipe.name)
                    stepfunc()
                except Exception, ex:
                    failed.append(recipe.name)
                    m.warning(_("%s checks failed: %s") % (recipe.name, ex))
        if failed:
            raise CommandError(_("Error running %s checks on:\n    " +
                        "\n    ".join(failed)) % p_name)

register_command(CheckPackage)
