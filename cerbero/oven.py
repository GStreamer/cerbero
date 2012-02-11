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

import logging

from cerbero.errors import FatalError
from cerbero.utils import _


class Oven (object):
    '''
    This oven cooks recipes with all their ingredients

    @ivar recipe: A recipe to build
    @type: L{cerberos.recipe.recipe}
    @ivar cookbook: Cookbook with the recipes status
    @type: L{cerberos.cookbook.CookBook}
    '''

    STEP_TPL = '[(%s/%s) %s -> %s ]'

    def __init__(self, recipe, cookbook):
        self.recipe = recipe
        self.cookbook = cookbook

    def start_cooking (self):
        '''
        Cooks the recipe and all its dependencies
        '''
        ordered_recipes =  self._process_deps (self.recipe)

        logging.info(_("Building the following recipes %s: ") %
                     ' '.join([x.name for x in ordered_recipes]))

        i = 1
        for recipe in ordered_recipes:
            self._cook_recipe (recipe, i, len(ordered_recipes))
            i += 1

    def _cook_recipe (self, recipe, count, total):
        if not self.cookbook.recipe_needs_build(recipe.name):
            logging.info(_("%s already built") % recipe.name)
            return

        for desc, step in recipe._steps:
            logging.info(self.STEP_TPL % (count, total, recipe.name, step))
            # check if the current step needs to be done
            if self.cookbook.step_done (recipe.name, step):
                logging.info(_("Step done"))
                continue
            try:
                # call step function
                stepfunc = getattr(recipe, step)
                if not stepfunc:
                    raise FatalError (_('Step %s not found') % step)
                stepfunc()
                # update status successfully
                self.cookbook.update_step_status (recipe.name, step)
            except FatalError, e:
                raise e
            except Exception, ex:
                raise FatalError (_("Error performing step %s: %s") % (step,
                                  ex))
        self.cookbook.update_build_status (recipe.name, False)

    def _process_deps (self, recipe, state={}, ordered=[]):
        if state.get(recipe, 'clean') == 'processed':
            return
        if state.get(recipe, 'clean') == 'in-progress':
            raise FatalError(_("Dependency Cycle"))
        state[recipe] = 'in-progress'
        for recipe_name in recipe.deps:
            try:
                recipedep = self.cookbook.get_recipe(recipe_name)
                if recipedep == None:
                    raise FatalError (_("Recipe %s has a uknown dependency %s"
                                      % (recipe.name , recipe_name)))
                self._process_deps(recipedep, state, ordered)
            except KeyError:
                pass # user already notified via logging.info above
        state[recipe] = 'processed'
        ordered.append(recipe)
        return ordered
