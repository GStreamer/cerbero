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
import logging
import pickle
import time

from cerbero.config import CONFIG_DIR
from cerbero.errors import FatalError
from cerbero.utils import _


COOKBOOK_NAME = 'cookbook'
COOKBOOK_FILE = os.path.join(CONFIG_DIR, COOKBOOK_NAME)



class RecipeStatus (object):

    def __init__ (self, steps=[], needs_build=True, mtime=time.time()):
        self.steps = steps
        self.needs_build = needs_build
        self.mtime = mtime

    def touch (self):
        self.mtime = time.time()

    def __repr__ (self):
        return "Steps: %r Needs Build: %r" % (self.steps, self.needs_build)


class CookBook (object):

    recipes = {} # recipe_name -> recipe
    status = {}   # recipe_name -> RecipeStatus

    _mtimes = {}

    def __init__ (self, config):
        self.set_config(config)
        if not os.path.exists(config.recipes_dir):
            raise FatalError(_("Recipes dir %s not found") %
                             config.recipes_dir)

    def set_config (self, config):
        self._config = config

    def get_config (self):
        return self._config

    def set_status (self, status):
        self.status = status

    def update (self):
        self._load_recipes ()
        self.save()

    def get_recipes_list (self):
        recipes = self.recipes.values()
        recipes.sort(key=lambda x: x.name)
        return recipes

    def get_recipe (self, name):
        if name not in self.recipes:
            return None
        return self.recipes[name]

    def update_step_status (self, recipe_name, step):
        status = self._recipe_status(recipe_name)
        status.steps.append(step)
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def update_build_status (self, recipe_name, needs_build):
        status = self._recipe_status(recipe_name)
        status.needs_build = needs_build
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def step_done (self, recipe_name, step):
        return step in self._recipe_status(recipe_name).steps

    def recipe_needs_build (self, recipe_name):
        return self._recipe_status(recipe_name).needs_build

    @staticmethod
    def load (config):
        status = {}
        try:
            with open(COOKBOOK_FILE, 'rb') as f:
                status = pickle.load(f)
        except Exception:
            logging.warning(_("Could not recover status"))
        c = CookBook(config)
        c.set_status (status)
        c.update()
        return c

    def save (self):
        try:
            if not os.path.exists (CONFIG_DIR):
                os.mkdir (CONFIG_DIR)
            with open(COOKBOOK_FILE, 'wb') as f:
                pickle.dump(self.status, f)
        except IOError, ex:
            logging.warning (_("Could not cache the CookBook: %s"), ex)

    def _recipe_status (self, recipe_name):
        if recipe_name not in self.status:
            self.status[recipe_name] = RecipeStatus(steps=[])
        return self.status[recipe_name]

    def _load_recipes (self):
        self.recipes = {}
        for f in os.listdir(self._config.recipes_dir):
            filepath = os.path.join(self._config.recipes_dir, f)
            recipe = self._load_recipe_from_file (filepath)
            if recipe is None:
                logging.warning(_("Could not found a valid recipe in %s") %
                                f)
                continue
            elif recipe.name is None:
                logging.warning(_("The recipe in file %s doesn't contain a "
                                  "name") % f)
                continue
            self.recipes[recipe.name] = recipe

            # Check for updates in the recipe file to reset the status
            rmtime = os.path.getmtime(filepath)
            if recipe.name in self.status:
                if rmtime > self.status[recipe.name].mtime:
                    self.status[recipe.name].touch()
                    self.status[recipe.name] = RecipeStatus()


    def _load_recipe_from_file (self, filepath):
        mod_name, file_ext = os.path.splitext(os.path.split(filepath)[-1])
        try:
            execfile(filepath, locals(), globals())
            r = Recipe(self._config)
            r.prepare()
            return r
        except Exception, ex:
            import traceback; traceback.print_exc()
            logging.warning("Error loading recipe %s" % ex)
        return None
