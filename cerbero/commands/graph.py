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


import shutil
import argparse
import tempfile

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import _, N_, ArgparseArgument, shell
from cerbero.utils import messages as m


class GraphType:
    RECIPE = ('recipe',)
    PACKAGE = ('package',)
    PACKAGE_RECIPES = 'package_recipes'


class Graph(Command):
    doc = N_('Create a graph of dependencies using dot from graphviz')
    name = 'graph'

    def __init__(self):
        Command.__init__(
            self,
            [
                ArgparseArgument('name', nargs=1, help=_('name of the recipe or package to generate deps from')),
                ArgparseArgument('-r', '--recipe', action='store_true', help=_('generate deps for the given recipe')),
                ArgparseArgument('-p', '--package', action='store_true', help=_('generate deps for the given package')),
                ArgparseArgument(
                    '-pr',
                    '--package-recipes',
                    action='store_true',
                    help=_('generate recipe deps for the given package'),
                ),
                ArgparseArgument('-o', '--output', nargs=1, help=_('output file for the SVG graph')),
            ],
        )

    def run(self, config, args):
        if args.recipe + args.package + args.package_recipes == 0:
            m.error(
                'Error: You need to specify either recipe, package or package-recipes '
                'mode to generate the dependency graph'
            )
            return

        if args.recipe + args.package + args.package_recipes > 1:
            m.error('Error: You can only specify recipe, package or package-recipes but not more than one')
            return

        if not shutil.which('dot'):
            m.error(
                'Error: dot command not found. Please install graphviz it using '
                'your package manager. e.g. apt/dnf/brew install graphviz'
            )
            return

        label = ''
        if args.recipe:
            self.graph_type = GraphType.RECIPE
            label = 'recipe'
        elif args.package:
            self.graph_type = GraphType.PACKAGE
            label = 'package'
        elif args.package_recipes:
            self.graph_type = GraphType.PACKAGE_RECIPES
            label = "package's recipes"

        if self.graph_type == GraphType.RECIPE or self.graph_type == GraphType.PACKAGE_RECIPES:
            self.cookbook = CookBook(config)
        if self.graph_type == GraphType.PACKAGE or self.graph_type == GraphType.PACKAGE_RECIPES:
            self.package_store = PackagesStore(config)

        name = args.name[0]
        output = args.output[0] if args.output else name + '.svg'

        tmp = tempfile.NamedTemporaryFile()
        dot = 'digraph {{\n\tlabel="{} {}";\n{}}}\n'.format(name, label, self._dot_gen(name, self.graph_type))
        with open(tmp.name, 'w') as f:
            f.write(dot)

        shell.new_call(['dot', '-Tsvg', tmp.name, '-o', output])
        m.message('Dependency graph for %s generated at %s' % (name, output))

    def _dot_gen(self, name, graph_type, already_parsed=[]):
        already_parsed.append(name)
        if graph_type == GraphType.RECIPE:
            deps = self.cookbook.get_recipe(name).list_deps()
        elif graph_type == GraphType.PACKAGE:
            deps = [p.name for p in self.package_store.get_package_deps(name)]
        elif graph_type == GraphType.PACKAGE_RECIPES:
            deps = self.package_store.get_package(name).recipes_dependencies()
            graph_type = GraphType.RECIPE
        line = ''
        for dep in deps:
            line += '\t"{}" -> "{}";\n'.format(name, dep)
            if dep not in already_parsed:
                line += self._dot_gen(dep, graph_type, already_parsed)
        return line


register_command(Graph)
