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

import os

from cerbero.commands import Command, register_command
from cerbero.errors import FatalError
from cerbero.utils import _, N_, ArgparseArgument


RECEIPT_TPL =\
'''# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python

class Recipe(recipe.Recipe):
    name = '%(name)s'
    version = '%(version)s'
'''


class AddRecipe(Command):
    doc = N_('Adds a new recipe')
    name = 'add-recipe'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('name', nargs=1,
                             help=_('name of the recipe to build')),
            ArgparseArgument('version', nargs=1,
                             help=_('version of the recipe to build')),
            ])

    def run(self, config, args):
        name = args.name[0]
        version = args.version[0]
        try:
            f = open(os.path.join(config.recipes_dir, '%s.recipe' % name), 'w')
            f.write(RECEIPT_TPL % {'name': name, 'version': version})
            f.close()
        except IOError, ex:
            raise FatalError(_("Error creating recipe: %s", ex))


register_command(AddRecipe)
