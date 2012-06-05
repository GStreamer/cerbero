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

from collections import defaultdict
import os
import pickle
import time

from cerbero.config import CONFIG_DIR, Platform, Architecture, Distro,\
        DistroVersion, License
from cerbero.build.build import BuildType
from cerbero.build.source import SourceType
from cerbero.errors import FatalError, RecipeNotFoundError, InvalidRecipeError
from cerbero.utils import _
from cerbero.utils import messages as m
from cerbero.build import recipe as crecipe


COOKBOOK_NAME = 'cookbook'
COOKBOOK_FILE = os.path.join(CONFIG_DIR, COOKBOOK_NAME)


class RecipeStatus (object):
    '''
    Stores the current build status of a L{cerbero.recipe.Recipe}

    @ivar steps: list of steps currently done
    @type steps: list
    @ivar needs_build: whether the recipe needs to be build or not
                       True when all steps where successful
    @type needs_build: bool
    @ivar mtime: modification time of the recipe file, used to reset the
                 state when the recipe was modified
    @type mtime: float
    @iver filepath: recipe's file path
    @type filepath: str
    '''

    def __init__(self, filepath, steps=[], needs_build=True, mtime=time.time()):
        self.steps = steps
        self.needs_build = needs_build
        self.mtime = mtime
        self.filepath = filepath

    def touch(self):
        ''' Touches the recipe updating its modification time '''
        self.mtime = time.time()

    def __repr__(self):
        return "Steps: %r Needs Build: %r" % (self.steps, self.needs_build)


class CookBook (object):
    '''
    Stores a list of recipes and their build status saving it's state to a
    cache file

    @ivar recipes: dictionary with L{cerbero.recipe.Recipe} availables
    @type recipes: dict
    @ivar status: dictionary with the L{cerbero.cookbook.RecipeStatus}
    @type status: dict
    '''

    RECIPE_EXT = '.recipe'

    def __init__(self, config, load=True):
        self.set_config(config)
        self.recipes = {}  # recipe_name -> recipe
        self._mtimes = {}

        if not load:
            return

        self._restore_cache()

        if not os.path.exists(config.recipes_dir):
            raise FatalError(_("Recipes dir %s not found") %
                             config.recipes_dir)
        self.update()

    def set_config(self, config):
        '''
        Set the configuration used

        @param config: configuration used
        @type config: L{cerbero.config.Config}
        '''
        self._config = config

    def get_config(self):
        '''
        Gets the configuration used

        @return: current configuration
        @rtype: L{cerbero.config.Config}
        '''
        return self._config

    def set_status(self, status):
        '''
        Sets the recipes status

        @param status: the recipes status
        @rtype: dict
        '''
        self.status = status

    def update(self):
        '''
        Reloads the recipes list adn updates the cookbook
        '''
        self._load_recipes()
        self.save()

    def get_recipes_list(self):
        '''
        Gets the list of recipes

        @return: list of recipes
        @rtype: list
        '''
        recipes = self.recipes.values()
        recipes.sort(key=lambda x: x.name)
        return recipes

    def add_recipe(self, recipe):
        '''
        Adds a new recipe to the cookbook

        @param recipe: the recipe to add
        @type  recipe: L{cerbero.build.cookbook.Recipe}
        '''
        self.recipes[recipe.name] = recipe

    def get_recipe(self, name):
        '''
        Gets a recipe from its name

        @param name: name of the recipe
        @type name: str
        '''
        if name not in self.recipes:
            raise RecipeNotFoundError(name)
        return self.recipes[name]

    def update_step_status(self, recipe_name, step):
        '''
        Updates the status of a recipe's step

        @param recipe_name: name of the recipe
        @type recipe: str
        @param step: name of the step
        @type step: str
        '''
        status = self._recipe_status(recipe_name)
        status.steps.append(step)
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def update_build_status(self, recipe_name, needs_build):
        '''
        Updates the recipe's build status

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param needs_build: wheter it's already built or not
        @type needs_build: str
        '''
        status = self._recipe_status(recipe_name)
        status.needs_build = needs_build
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def step_done(self, recipe_name, step):
        '''
        Whether is step is done or not

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param step: name of the step
        @type step: bool
        '''
        return step in self._recipe_status(recipe_name).steps

    def reset_recipe_status(self, recipe_name):
        '''
        Resets the build status of a recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        '''
        if recipe_name in self.status:
            del self.status[recipe_name]
            self.save()

    def recipe_needs_build(self, recipe_name):
        '''
        Whether a recipe needs to be build or not

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: True if the recipe needs to be build
        @rtype: bool
        '''
        return self._recipe_status(recipe_name).needs_build

    def list_recipe_deps(self, recipe_name):
        '''
        List the dependencies that needs to be built in the correct build
        order for a recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: list of L{cerbero.recipe.Recipe}
        @rtype: list
        '''
        recipe = self.get_recipe(recipe_name)
        return self._find_deps(recipe, {}, [])

    def _cache_file(self, config):
        if config.cache_file is not None:
            return os.path.join(CONFIG_DIR, config.cache_file)
        else:
            return COOKBOOK_FILE

    def _restore_cache(self):
        try:
            with open(self._cache_file(self.get_config()), 'rb') as f:
                self.status = pickle.load(f)
        except Exception:
            self.status = {}
            m.warning(_("Could not recover status"))

    def save(self):
        try:
            cache_file = self._cache_file(self.get_config())
            if not os.path.exists(os.path.dirname(cache_file)):
                os.makedirs(os.path.dirname(cache_file))
            with open(cache_file, 'wb') as f:
                pickle.dump(self.status, f)
        except IOError, ex:
            m.warning(_("Could not cache the CookBook: %s"), ex)

    def _find_deps(self, recipe, state={}, ordered=[]):
        if state.get(recipe, 'clean') == 'processed':
            return
        if state.get(recipe, 'clean') == 'in-progress':
            raise FatalError(_("Dependency Cycle"))
        state[recipe] = 'in-progress'
        for recipe_name in recipe.list_deps():
            try:
                recipedep = self.get_recipe(recipe_name)
            except RecipeNotFoundError, e:
                raise FatalError(_("Recipe %s has a unknown dependency %s"
                                 % (recipe.name, recipe_name)))
            self._find_deps(recipedep, state, ordered)
        state[recipe] = 'processed'
        ordered.append(recipe)
        return ordered

    def _recipe_status(self, recipe_name):
        recipe = self.get_recipe(recipe_name)
        if recipe_name not in self.status:
            filepath = None
            if hasattr(recipe, '__file__'):
                filepath = recipe.__file__
            self.status[recipe_name] = RecipeStatus(filepath, steps=[])
        return self.status[recipe_name]

    def _load_recipes(self):
        self.recipes = {}
        recipes = defaultdict(dict)
        recipes_repos = self._config.get_recipes_repos()
        for reponame, (repodir, priority) in recipes_repos.iteritems():
            recipes[int(priority)].update(self._load_recipes_from_dir(repodir))
        # Add recipes by asceding pripority
        for key in sorted(recipes.keys()):
            self.recipes.update(recipes[key])

        # Check for updates in the recipe file to reset the status
        for recipe in self.recipes.values():
            if recipe.name not in self.status:
                continue
            st = self.status[recipe.name]
            # filepath attribute was added afterwards
            if not hasattr(st, 'filepath') or not getattr(st, 'filepath'):
                st.filepath = recipe.__file__
            if recipe.__file__ != st.filepath:
                self.reset_recipe_status(recipe.name)
            else:
                rmtime = os.path.getmtime(recipe.__file__)
                if rmtime > st.mtime:
                    self.reset_recipe_status(recipe.name)

    def _load_recipes_from_dir(self, repo):
        recipes = {}
        for f in os.listdir(repo):
            if not f.endswith(self.RECIPE_EXT):
                continue
            filepath = os.path.join(repo, f)
            try:
                recipe = self._load_recipe_from_file(filepath)
            except RecipeNotFoundError:
                m.warning(_("Could not found a valid recipe in %s") %
                                f)
            if recipe is None:
                continue
            recipes[recipe.name] = recipe
        return recipes

    def _load_recipe_from_file(self, filepath):
        mod_name, file_ext = os.path.splitext(os.path.split(filepath)[-1])
        try:
            d = {'Platform': Platform, 'Architecture': Architecture,
                 'BuildType': BuildType, 'SourceType': SourceType,
                 'Distro': Distro, 'DistroVersion': DistroVersion,
                 'License': License,
                 'recipe': crecipe, 'os': os, 'BuildSteps': crecipe.BuildSteps,
                 'InvalidRecipeError': InvalidRecipeError}
            execfile(filepath, d)
            r = d['Recipe'](self._config)
            r.__file__ = os.path.abspath(filepath)
            r.prepare()
            return r
        except InvalidRecipeError:
            pass
        except Exception, ex:
            import traceback
            traceback.print_exc()
            m.warning("Error loading recipe %s" % ex)
        return None
