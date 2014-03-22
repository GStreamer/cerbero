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

    def __init__(self, force=None, no_deps=None, wanted_steps=[]):
            args = [
                ArgparseArgument('recipe', nargs='*',
                    help=_('name of the recipe to build')),
                ArgparseArgument('--missing-files', action='store_true',
                    default=False,
                    help=_('prints a list of files installed that are '
                           'listed in the recipe')),
                ArgparseArgument('--dry-run', action='store_true',
                    default=False,
                    help=_('only print commands instead of running them '))]
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

            if not wanted_steps:
                args.append(
                    ArgparseArgument('--wanted-steps', default='',
                        help=_('Steps to force execution when building even if stated as'
                               'done in the current cached state. Its is a list'
                               'of step name separated by ;')))

            self.force = force
            self.wanted_steps = wanted_steps
            self.no_deps = no_deps
            Command.__init__(self, args)

    def run(self, config, args):
        if self.force is None:
            self.force = args.force
        if self.no_deps is None:
            self.no_deps = args.no_deps
        if not self.wanted_steps:
            self.wanted_steps = args.wanted_steps.split(':')
        self.runargs(config, args.recipe, args.missing_files, self.force,
                     self.no_deps, dry_run=args.dry_run, wanted_steps=self.wanted_steps)

    def runargs(self, config, recipes, missing_files=False, force=False,
                no_deps=False, cookbook=None, dry_run=False, wanted_steps=[]):
        if cookbook is None:
            cookbook = CookBook(config)

        oven = Oven(recipes, cookbook, force=self.force,
                    no_deps=self.no_deps, missing_files=missing_files,
                    dry_run=dry_run, wanted_steps=wanted_steps)
        oven.start_cooking()


class BuildOne(Build):
    doc = N_('Build or rebuild a single recipe without its dependencies')
    name = 'buildone'

    def __init__(self):
        Build.__init__(self, True, True)


register_command(BuildOne)
register_command(Build)
