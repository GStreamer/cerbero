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
from cerbero.build.source import SourceType
from cerbero.packages.packagesstore import PackagesStore
from cerbero.bootstrap.build_tools import BuildTools
from cerbero.utils import _, N_, ArgparseArgument, remove_list_duplicates
from cerbero.utils import messages as m
from setuptools.sandbox import run_setup


class BundleSource(Command):
    doc = N_('Bundle Source code of recipes and Cerbero')
    name = 'bundle-source'

    def __init__(self, args=[]):
        args = [
            ArgparseArgument('bundlepackages', nargs='+', 
                             help=_('packages to bundle')),
            ArgparseArgument('--add-recipe', action='append',
                             default=[],
                             help=_('additional recipes to bundle')),
            ArgparseArgument('--no-bootstrap', action='store_true',
                             default=False,
                             help=_('Don\'t include bootstrep sources')),
            ArgparseArgument('--offline', action='store_true',
                default=False, help=_('Use only the source cache, no network')),
        ]
        Command.__init__(self, args)

    def run(self, config, args):
        packages = []
        recipes = []
        bundle_recipes = []
        bundle_dirs = []
        setup_args = ['sdist']

        if not config.uninstalled:
            m.error("Can only be run on cerbero-uninstalled")

        store = PackagesStore(config)
        cookbook = CookBook(config)

        packages = list(args.bundlepackages)

        for p in packages:
            package = store.get_package(p)
            if hasattr(package, 'list_packages'):
                packages += package.list_packages()
        packages = remove_list_duplicates(packages)

        for p in packages:
            package = store.get_package(p)
            if hasattr(package, 'deps'):
                packages += package.deps
        packages = remove_list_duplicates(packages)

        for p in packages:
            package = store.get_package(p)
            recipes += package.recipes_dependencies()
        recipes += args.add_recipe

        for r in recipes:
            bundle_recipes += cookbook.list_recipe_deps(r)
        bundle_recipes = remove_list_duplicates(bundle_recipes)

        for p in packages:
            setup_args.append('--package=' + p)

        for r in bundle_recipes:
            setup_args.append('--recipe=' + r.name)
            if r.stype != SourceType.CUSTOM:
                bundle_dirs.append(r.repo_dir)

        if not args.no_bootstrap:
            build_tools = BuildTools(config, args.offline)
            bs_recipes = build_tools.BUILD_TOOLS + \
                         build_tools.PLAT_BUILD_TOOLS.get(config.platform, [])
            b_recipes = []
            for r in bs_recipes:
                b_recipes += cookbook.list_recipe_deps(r)
            b_recipes = remove_list_duplicates(b_recipes)

            for r in b_recipes:
                if r.stype != SourceType.CUSTOM:
                    bundle_dirs.append(r.repo_dir)

        setup_args.append('--source-dirs=' + ','.join(bundle_dirs))

        command = str(config._relative_path('setup.py'))
        run_setup(command, setup_args)

register_command(BundleSource)
