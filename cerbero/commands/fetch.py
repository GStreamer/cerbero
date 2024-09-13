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

import asyncio

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.enums import LibraryType
from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import (
    _,
    N_,
    ArgparseArgument,
    remove_list_duplicates,
    shell,
    determine_num_of_cpus,
    run_until_complete,
)
from cerbero.utils import messages as m
from cerbero.utils.shell import BuildStatusPrinter
from cerbero.build.source import Tarball

NUMBER_OF_JOBS_IF_UNUSED = 2
NUMBER_OF_JOBS_IF_USED = 2 * determine_num_of_cpus()


class Fetch(Command):
    def __init__(self, args=None):
        if args is None:
            args = []
        args.append(
            ArgparseArgument(
                '--reset-rdeps',
                action='store_true',
                default=False,
                help=_('reset the status of reverse ' 'dependencies too'),
            )
        )
        args.append(
            ArgparseArgument(
                '--print-only', action='store_true', default=False, help=_('print all source URLs to stdout')
            )
        )
        args.append(
            ArgparseArgument(
                '--full-reset', action='store_true', default=False, help=_('reset to extract step if rebuild is needed')
            )
        )
        args.append(
            ArgparseArgument(
                '--jobs',
                '-j',
                action='store',
                nargs='?',
                type=int,
                const=NUMBER_OF_JOBS_IF_USED,
                default=NUMBER_OF_JOBS_IF_UNUSED,
                help=_('number of async jobs'),
            )
        )
        Command.__init__(self, args)

    @staticmethod
    async def fetch(cookbook, recipes, no_deps, reset_rdeps, full_reset, print_only, jobs):
        fetch_recipes = []
        if not recipes:
            fetch_recipes = cookbook.get_recipes_list()
        elif no_deps:
            fetch_recipes = [cookbook.get_recipe(x) for x in recipes]
        else:
            for recipe in recipes:
                fetch_recipes += cookbook.list_recipe_deps(recipe)
            fetch_recipes = remove_list_duplicates(fetch_recipes)
        m.message(
            _('Fetching the following recipes using %s async job(s): %s')
            % (jobs, ' '.join([x.name for x in fetch_recipes]))
        )
        shell.set_max_non_cpu_bound_calls(jobs)
        to_rebuild = []
        printer = BuildStatusPrinter(('fetch',), cookbook.get_config().interactive)
        printer.total = len(fetch_recipes)

        async def fetch_print_wrapper(recipe_name, stepfunc):
            printer.update_recipe_step(printer.count, recipe_name, 'fetch')
            await stepfunc()
            printer.count += 1
            printer.remove_recipe(recipe_name)

        for recipe in fetch_recipes:
            if print_only:
                # For now just print tarball URLs
                if isinstance(recipe, Tarball):
                    m.message('TARBALL: {} {}'.format(recipe.url, recipe.tarball_name))
                continue
            stepfunc = getattr(recipe, 'fetch')
            if asyncio.iscoroutinefunction(stepfunc):
                await fetch_print_wrapper(recipe.name, stepfunc)
            else:
                printer.update_recipe_step(printer.count, recipe.name, 'fetch')
                stepfunc()
                printer.count += 1
                printer.remove_recipe(recipe.name)

        m.message('All async fetch jobs finished')

        # Checking the current built version against the fetched one
        # needs to be done *after* actually fetching
        for recipe in fetch_recipes:
            bv = cookbook.recipe_built_version(recipe.name)
            cv = recipe.built_version()
            if bv != cv:
                # On different versions, only reset recipe if:
                #  * forced
                #  * OR it was fully built already
                if full_reset or not cookbook.recipe_needs_build(recipe.name):
                    to_rebuild.append(recipe)
                    cookbook.reset_recipe_status(recipe.name)
                    if recipe.library_type == LibraryType.STATIC or reset_rdeps:
                        for r in cookbook.list_recipe_reverse_deps(recipe.name):
                            to_rebuild.append(r)
                            cookbook.reset_recipe_status(r.name)

        if to_rebuild:
            to_rebuild = sorted(list(set(to_rebuild)), key=lambda r: r.name)
            m.message(
                _('These recipes have been updated and will ' 'be rebuilt:\n%s')
                % '\n'.join([x.name for x in to_rebuild])
            )


class FetchRecipes(Fetch):
    doc = N_('Fetch the recipes sources')
    name = 'fetch'

    def __init__(self):
        args = [
            ArgparseArgument(
                'recipes', nargs='*', help=_('list of the recipes to fetch (fetch all if none ' 'is passed)')
            ),
            ArgparseArgument('--no-deps', action='store_true', default=False, help=_('do not fetch dependencies')),
        ]
        Fetch.__init__(self, args)

    def run(self, config, args):
        cookbook = CookBook(config)
        recipes = []
        for recipe in args.recipes:
            found = cookbook.get_closest_recipe(recipe)
            if found:
                recipes.append(found)
            else:
                recipes.append(recipe)
        task = self.fetch(
            cookbook, recipes, args.no_deps, args.reset_rdeps, args.full_reset, args.print_only, args.jobs
        )
        return run_until_complete(task)


class FetchPackage(Fetch):
    doc = N_('Fetch the recipes sources from a package')
    name = 'fetch-package'

    def __init__(self):
        args = [
            ArgparseArgument('package', nargs=1, help=_('package to fetch')),
            ArgparseArgument('--deps', action='store_false', default=True, help=_('also fetch dependencies')),
        ]
        Fetch.__init__(self, args)

    def run(self, config, args):
        store = PackagesStore(config)
        package = store.get_package(args.package[0])
        task = self.fetch(
            store.cookbook,
            package.recipes_dependencies(),
            args.deps,
            args.reset_rdeps,
            args.full_reset,
            args.print_only,
            args.jobs,
        )
        return run_until_complete(task)


register_command(FetchRecipes)
register_command(FetchPackage)
