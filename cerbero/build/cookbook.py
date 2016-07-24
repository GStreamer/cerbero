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
import imp

from cerbero.config import CONFIG_DIR, Platform, Architecture, Distro,\
    DistroVersion, License
from cerbero.build.build import BuildType
from cerbero.build.source import SourceType
from cerbero.errors import FatalError, RecipeNotFoundError, InvalidRecipeError
from cerbero.utils import _, shell, parse_file
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
    @ivar filepath: recipe's file path
    @type filepath: str
    @ivar built_version: string with the last version built
    @type built_version: str
    @ivar file_hash: hash of the file with the recipe description
    @type file_hash: int
    '''

    def __init__(self, filepath, steps=[], needs_build=True,
                 mtime=time.time(), built_version=None, file_hash=0):
        self.steps = steps
        self.needs_build = needs_build
        self.mtime = mtime
        self.filepath = filepath
        self.built_version = built_version
        self.file_hash = file_hash

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
        self._invalid_recipes = {} # recipe -> error
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
        Reloads the recipes list and updates the cookbook
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
        if name in self._invalid_recipes:
            raise self._invalid_recipes[name]
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

    def update_build_status(self, recipe_name, built_version):
        '''
        Updates the recipe's build status

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param built_version: built version ir None to reset it
        @type built_version: str
        '''
        status = self._recipe_status(recipe_name)
        status.needs_build = built_version == None
        status.built_version = built_version
        status.touch()
        self.status[recipe_name] = status
        self.save()

    def recipe_built_version (self, recipe_name):
        '''
        Get the las built version of a recipe from the build status

        @param recipe_name: name of the recipe
        @type recipe_name: str
        '''
        try:
            return self._recipe_status(recipe_name).built_version
        except:
            return None

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

    def list_recipe_reverse_deps(self, recipe_name):
        '''
        List the dependencies that depends on this recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: list of reverse dependencies L{cerbero.recipe.Recipe}
        @rtype: list
        '''
        recipe = self.get_recipe(recipe_name)
        return [r for r in self.recipes.values() if recipe.name in r.deps]

    def _runtime_deps (self):
        return [x.name for x in self.recipes.values() if x.runtime_dep]

    def _cache_file(self, config):
        if config.cache_file is not None:
            return os.path.join(config.home_dir, config.cache_file)
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
            m.warning(_("Could not cache the CookBook: %s") % ex)

    def _find_deps(self, recipe, state={}, ordered=[]):
        if state.get(recipe, 'clean') == 'processed':
            return
        if state.get(recipe, 'clean') == 'in-progress':
            raise FatalError(_("Dependency Cycle: {0}".format(recipe.name)))
        state[recipe] = 'in-progress'
        recipe_deps = recipe.list_deps()
        if not recipe.runtime_dep:
            recipe_deps = self._runtime_deps () + recipe_deps
        for recipe_name in recipe_deps:
            try:
                recipedep = self.get_recipe(recipe_name)
            except RecipeNotFoundError, e:
                raise FatalError(_("Recipe %s has a unknown dependency %s"
                                 % (recipe.name, recipe_name)))
            try:
                self._find_deps(recipedep, state, ordered)
            except FatalError:
                m.error('Error finding deps of "{0}"'.format(recipe.name))
                raise
        state[recipe] = 'processed'
        ordered.append(recipe)
        return ordered

    def _recipe_status(self, recipe_name):
        recipe = self.get_recipe(recipe_name)
        if recipe_name not in self.status:
            filepath = None
            if hasattr(recipe, '__file__'):
                filepath = recipe.__file__
            self.status[recipe_name] = RecipeStatus(filepath, steps=[],
                    file_hash=shell.file_hash(filepath))
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
                    # The mtime is different, check the file hash now
                    # Use getattr as file_hash we added later
                    saved_hash = getattr(st, 'file_hash', 0)
                    current_hash = shell.file_hash(st.filepath)
                    if saved_hash == current_hash:
                        # Update the status with the mtime
                        st.touch()
                    else:
                        self.reset_recipe_status(recipe.name)

    def _load_recipes_from_dir(self, repo):
        recipes = {}
        recipes_files = shell.find_files('*%s' % self.RECIPE_EXT, repo)
        recipes_files.extend(shell.find_files('*/*%s' % self.RECIPE_EXT, repo))
        try:
            custom = None
            m_path = os.path.join(repo, 'custom.py')
            if os.path.exists(m_path):
                custom = imp.load_source('custom', m_path)
        except Exception:
            custom = None
        for f in recipes_files:
            # Try to load the custom.py module located in the recipes dir
            # which can contain private classes to extend cerbero's recipes
            # and reuse them in our private repository
            try:
                recipe = self._load_recipe_from_file(f, custom)
            except RecipeNotFoundError:
                m.warning(_("Could not found a valid recipe in %s") % f)
            if recipe is None:
                continue
            recipes[recipe.name] = recipe
        return recipes

    def _load_recipe_from_file(self, filepath, custom=None):
        mod_name, file_ext = os.path.splitext(os.path.split(filepath)[-1])
        if self._config.target_arch == Architecture.UNIVERSAL:
            if self._config.target_platform in [Platform.IOS, Platform.DARWIN]:
                recipe = crecipe.UniversalFlatRecipe(self._config)
            else:
                recipe = crecipe.UniversalRecipe(self._config)
        for c in self._config.arch_config.keys():
            try:
                d = {'Platform': Platform, 'Architecture': Architecture,
                     'BuildType': BuildType, 'SourceType': SourceType,
                     'Distro': Distro, 'DistroVersion': DistroVersion,
                     'License': License, 'recipe': crecipe, 'os': os,
                     'BuildSteps': crecipe.BuildSteps,
                     'InvalidRecipeError': InvalidRecipeError,
                     'FatalError': FatalError,
                     'custom': custom, '_': _, 'shell': shell}
                parse_file(filepath, d)
                conf = self._config.arch_config[c]
                if self._config.target_arch == Architecture.UNIVERSAL:
                    if self._config.target_platform not in [Platform.IOS,
                            Platform.DARWIN]:
                        conf.prefix = os.path.join(self._config.prefix, c)
                r = d['Recipe'](conf)
                r.__file__ = os.path.abspath(filepath)
                self._config.arch_config[c].do_setup_env()
                r.prepare()
                if self._config.target_arch == Architecture.UNIVERSAL:
                    recipe.add_recipe(r)
                else:
                    return r
            except InvalidRecipeError, e:
                self._invalid_recipes[r.name] = e
            except Exception, ex:
                m.warning("Error loading recipe in file %s %s" %
                          (filepath, ex))
        if self._config.target_arch == Architecture.UNIVERSAL:
            if not recipe.is_empty():
                return recipe
        return None
