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

from cerbero.config import Variants
from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.utils import _, N_
from cerbero.utils import messages as m
from cerbero.packages.packagesstore import PackagesStore


class List(Command):
    doc = N_('List all the available recipes')
    name = 'list'

    def __init__(self):
        Command.__init__(self, [])

    def run(self, config, args):
        cookbook = CookBook(config)
        recipes = cookbook.get_recipes_list()
        if len(recipes) == 0:
            m.message(_("No recipes found"))
        for recipe in recipes:
            m.message("%s - %s" % (recipe.name, recipe.version))


class ListPackages(Command):
    doc = N_('List all the available packages')
    name = 'list-packages'

    def __init__(self):
        Command.__init__(self, [])

    def run(self, config, args):
        store = PackagesStore(config)
        packages = store.get_packages_list()
        if len(packages) == 0:
            m.message(_("No packages found"))
        for p in packages:
            m.message("%s - %s" % (p.name, p.version))

class ShowConfig(Command):
    doc = N_('Show configuration settings')
    name = 'show-config'

    def __init__(self):
        Command.__init__(self, [])

    def run(self, config, args):
        for n in config._properties:
            if n == "variants":
                print("%25s :" % (n))
                variants = getattr(config, n).__dict__
                for v in variants:
                    print("%30s : %s" % (v, variants[v]))
            else:
                print("%25s : %s" % (n, getattr(config, n)))


register_command(List)
register_command(ListPackages)
register_command(ShowConfig)
