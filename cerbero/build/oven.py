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

import tempfile

from cerbero.errors import BuildStepError, FatalError
from cerbero.utils import _, shell
from cerbero.utils import messages as m


class Oven (object):
    '''
    This oven cooks recipes with all their ingredients

    @ivar recipe: A recipe to build
    @type: L{cerberos.recipe.recipe}
    @ivar cookbook: Cookbook with the recipes status
    @type: L{cerberos.cookbook.CookBook}
    @ivar force: Force the build of the recipe
    @type: bool
    @ivar no_deps: Ignore dependencies
    @type: bool
    @ivar missing_files: check for files missing in the recipe
    @type missing_files: bool
    '''

    STEP_TPL = '[(%s/%s) %s -> %s ]'

    def __init__(self, recipe, cookbook, force=False, no_deps=False,
                 missing_files=False):
        self.recipe = recipe
        self.cookbook = cookbook
        self.force = force
        self.no_deps = no_deps
        self.missing_files = missing_files

    def start_cooking(self):
        '''
        Cooks the recipe and all its dependencies
        '''
        if self.no_deps:
            ordered_recipes = [self.recipe]
        else:
            ordered_recipes = \
                self.cookbook.list_recipe_deps(self.recipe.name)

        m.message(_("Building the following recipes: %s") %
                  ' '.join([x.name for x in ordered_recipes]))

        i = 1
        for recipe in ordered_recipes:
            self._cook_recipe(recipe, i, len(ordered_recipes))
            i += 1

    def _cook_recipe(self, recipe, count, total):
        if not self.cookbook.recipe_needs_build(recipe.name) and \
                not self.force:
            m.build_step(count, total, recipe.name, _("already built"))
            return

        if self.missing_files:
            # create a temp file that will be used to find newer files
            tmp = tempfile.NamedTemporaryFile()

        recipe.force = self.force
        for desc, step in recipe._steps:
            m.build_step(count, total, recipe.name, step)
            # check if the current step needs to be done
            if self.cookbook.step_done(recipe.name, step) and not self.force:
                m.action(_("Step done"))
                continue
            try:
                # call step function
                stepfunc = getattr(recipe, step)
                if not stepfunc:
                    raise FatalError(_('Step %s not found') % step)
                stepfunc()
                # update status successfully
                self.cookbook.update_step_status(recipe.name, step)
            except FatalError, e:
                raise BuildStepError(e.msg)
            except Exception, ex:
                raise FatalError(_("Error performing step %s: %s") % (step,
                                  ex))
        self.cookbook.update_build_status(recipe.name, False)

        if self.missing_files:
            self._print_missing_files(recipe, tmp)

    def _print_missing_files(self, recipe, tmp):
        recipe_files = set(recipe.files_list())
        installed_files = set(shell.find_newer_files(recipe.config.prefix,
                                                     tmp.name))
        not_in_recipe = list(installed_files - recipe_files)
        not_installed = list(recipe_files - installed_files)

        if len(not_in_recipe) != 0:
            m.message(_("The following files where installed, but are not "
                        "listed in the recipe:"))
            m.message('\n'.join(sorted(not_in_recipe)))

        if len(not_installed) != 0:
            m.message(_("The following files are listed in the recipe, but "
                        "where not installed:"))
            m.message('\n'.join(sorted(not_installed)))
