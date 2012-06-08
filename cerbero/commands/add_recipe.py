# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
# Copyright (C) 2012 Collabora Ltd. <http://www.collabora.co.uk/>
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

import os

from cerbero.build.cookbook import CookBook
from cerbero.commands import Command, register_command
from cerbero.enums import License, LicenseDescription
from cerbero.errors import FatalError, UsageError, RecipeNotFoundError
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m


RECEIPT_TPL =\
'''# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python


class Recipe(recipe.Recipe):

    name = '%(name)s'
    version = '%(version)s'
'''

LICENSES_TPL = \
'''    licenses = [%(licenses)s]
'''

COMMIT_TPL = \
'''    commit = '%(commit)s'
'''

ORIGIN_TPL = \
'''    remotes = {'origin': '%(origin)s'}
'''

DEPS_TPL = \
'''    deps = %(deps)s
'''


class AddRecipe(Command):
    doc = N_('Adds a new recipe')
    name = 'add-recipe'

    def __init__(self):
        self.supported_licenses = {}
        l = License
        for name in l.__dict__:
            attr = getattr(l, name)
            if not isinstance(attr, LicenseDescription):
                continue
            self.supported_licenses[attr.acronym] = name

        Command.__init__(self,
            [ArgparseArgument('name', nargs=1,
                             help=_('name of the recipe')),
            ArgparseArgument('version', nargs=1,
                             help=_('version of the recipe')),
            ArgparseArgument('-l', '--licenses', default='',
                             help=_('comma separated list of the recipe '
                                    'licenses. Supported licenses: %s') %
                                    ', '.join(self.supported_licenses.keys())),
            ArgparseArgument('-c', '--commit', default='',
                             help=_('commit to use '
                                    '(default to "sdk-$version")')),
            ArgparseArgument('-o', '--origin', default='',
                             help=_('the origin repository of the recipe')),
            ArgparseArgument('-d', '--deps', default='',
                             help=_('comma separated list of the recipe '
                                    'dependencies')),
            ArgparseArgument('-f', '--force', action='store_true',
                default=False, help=_('Replace recipe if existing'))])

    def run(self, config, args):
        name = args.name[0]
        version = args.version[0]
        filename = os.path.join(config.recipes_dir, '%s.recipe' % name)
        if not args.force and os.path.exists(filename):
            m.warning(_("Recipe '%s' (%s) already exists, "
                "use -f to replace" % (name, filename)))
            return

        template_args = {}

        template = RECEIPT_TPL
        template_args['name'] = name
        template_args['version'] = version

        if args.licenses:
            licenses = args.licenses.split(',')
            self.validate_licenses(licenses)
            template += LICENSES_TPL
            template_args['licenses'] = ', '.join(
                    ['License.' + self.supported_licenses[l] \
                        for l in licenses])

        if args.commit:
            template += COMMIT_TPL
            template_args['commit'] = args.commit

        if args.origin:
            template += ORIGIN_TPL
            template_args['origin'] = args.origin

        if args.deps:
            template += DEPS_TPL
            deps = args.deps.split(',')
            cookbook = CookBook(config)
            for dname in deps:
                try:
                    recipe = cookbook.get_recipe(dname)
                except RecipeNotFoundError, ex:
                    raise UsageError(_("Error creating recipe: "
                            "dependant recipe %s does not exist") % dname)
            template_args['deps'] = deps

        try:
            f = open(filename, 'w')
            f.write(template % template_args)
            f.close()

            m.action(_("Recipe '%s' successfully created in %s") %
                    (name, filename))
        except IOError, ex:
            raise FatalError(_("Error creating recipe: %s") % ex)

    def validate_licenses(self, licenses):
        for l in licenses:
            if l and not l in self.supported_licenses:
                raise UsageError(_("Error creating recipe: "
                    "invalid license '%s'") % l)


register_command(AddRecipe)
