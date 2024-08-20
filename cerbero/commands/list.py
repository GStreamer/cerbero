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
from cerbero.packages.packagesstore import PackagesStore


class List(Command):
    doc = N_('List all the available recipes')
    name = 'list'

    def run(self, config, args):
        cookbook = CookBook(config)
        recipes = cookbook.get_recipes_list()
        if len(recipes) == 0:
            m.message(_('No recipes found'))
        for recipe in recipes:
            try:
                current = recipe.built_version().split('\n')[0]
            except Exception:
                current = 'Not checked out'

            m.message('%s - %s (current checkout: %s) - %s' % (recipe.name, recipe.version, current, recipe.__file__))


class ListPackages(Command):
    doc = N_('List all the available packages')
    name = 'list-packages'

    def run(self, config, args):
        store = PackagesStore(config)
        packages = store.get_packages_list()
        if len(packages) == 0:
            m.message(_('No packages found'))
        for p in packages:
            m.message('%s - %s - %s' % (p.name, p.version, p.__file__))


class ShowConfig(Command):
    doc = N_('Show configuration settings')
    name = 'show-config'

    def __init__(self):
        arguments = [
            ArgparseArgument('--archs', action='store_true', default=False, help=_('Show also the arch config if any')),
            ArgparseArgument(
                '--build-tools', action='store_true', default=False, help=_('Show also the boot tools config if any')
            ),
        ]
        Command.__init__(self, arguments)

    def run(self, config, args):
        self._print_config(config)
        if args.archs and config.arch_config and len(config.arch_config) > 0 and tuple(config.arch_config) != (None,):
            archs = list(config.arch_config.keys())
            archs.sort()
            print('Arch configs:', ', '.join(archs))
            for a in archs:
                print(a, 'arch:')
                self._print_config(config.arch_config[a])
        if args.build_tools and config.build_tools_config:
            print('Build tools config:')
            self._print_config(config.build_tools_config)

    def _print_config(self, config):
        for n in config._properties:
            if n == 'variants':
                print('%25s :' % (n))
                variants = getattr(config, n).__dict__
                for v in variants:
                    if v.startswith('_'):
                        continue
                    print('%30s : %s' % (v, variants[v]))
            else:
                print('%25s : %s' % (n, getattr(config, n)))


register_command(List)
register_command(ListPackages)
register_command(ShowConfig)
