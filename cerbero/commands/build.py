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


class Build(Command):
    doc = N_('Build a recipe')
    name = 'build'

    def __init__(self, force=None, no_deps=None, deps_only=False):
            args = [
                ArgparseArgument('recipe', nargs='*',
                    help=_('name of the recipe to build')),
                ArgparseArgument('--missing-files', action='store_true',
                    default=False,
                    help=_('prints a list of files installed that are '
                           'listed in the recipe')),
                ArgparseArgument('--dry-run', action='store_true',
                    default=False,
                    help=_('only print commands instead of running them ')),
                ArgparseArgument('--offline', action='store_true',
                    default=False, help=_('Use only the source cache, no network')),
                ArgparseArgument('--jobs', '-j', action='store', type=int,
                    default=0, help=_('How many recipes to build concurrently. '
                        '0 = number of CPUs.')),
                ArgparseArgument('--build-tools', '-b', action='store_true',
                    default=False, help=_('Runs the build command for the build tools of this config.')),
                ]
            if force is None:
                args.append(
                    ArgparseArgument('--force', action='store_true',
                        default=False,
                        help=_('force the build of the recipe ingoring '
                                    'its cached state')))
            if no_deps is None:
                args.append(
                    ArgparseArgument('--no-deps', action='store_true',
                        default=False,
                        help=_('do not build dependencies')))

            self.force = force
            self.no_deps = no_deps
            self.deps_only = deps_only
            Command.__init__(self, args)

    def run(self, config, args):
        if self.force is None:
            self.force = args.force
        if self.no_deps is None:
            self.no_deps = args.no_deps
        if args.build_tools:
            config = config.build_tools_config
        self.runargs(config, args.recipe, args.missing_files, self.force,
                     self.no_deps, dry_run=args.dry_run, offline=args.offline,
                     deps_only=self.deps_only, jobs=args.jobs)

    def runargs(self, config, fuzzy_recipes, missing_files=False, force=False,
                no_deps=False, cookbook=None, dry_run=False, offline=False,
                deps_only=False, jobs=None):
        if cookbook is None:
            cookbook = CookBook(config, offline=offline)

        recipes = []
        for recipe in fuzzy_recipes:
          found = cookbook.get_closest_recipe(recipe)
          if found:
            recipes.append(found)
          else:
            recipes.append(recipe)

        oven = Oven(recipes, cookbook, force=self.force,
                    no_deps=self.no_deps, missing_files=missing_files,
                    dry_run=dry_run, deps_only=deps_only, jobs=jobs)
        oven.start_cooking()


class BuildOne(Build):
    doc = N_('Build or rebuild a single recipe without its dependencies')
    name = 'buildone'

    def __init__(self):
        Build.__init__(self, True, True)

class BuildDeps(Build):
    doc = N_('Build only the dependencies of the specified recipes')
    name = 'build-deps'

    def __init__(self):
        Build.__init__(self, no_deps=False, deps_only=True)

register_command(BuildOne)
register_command(BuildDeps)
register_command(Build)
