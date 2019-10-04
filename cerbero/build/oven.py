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

import sys
import tempfile
import shutil
import traceback
import asyncio
import collections
from subprocess import CalledProcessError

from cerbero.enums import Architecture, Platform, LibraryType
from cerbero.errors import BuildStepError, FatalError, AbortedError
from cerbero.build.recipe import Recipe, BuildSteps
from cerbero.utils import _, N_, shell, run_until_complete, run_tasks, determine_num_of_cpus
from cerbero.utils import messages as m
from cerbero.utils.shell import BuildStatusPrinter
from cerbero.build.recipe import BuildSteps

import inspect

class RecoveryActions(object):
    '''
    Enumeration factory for recovery actions after an error
    '''

    SHELL = N_("Enter the shell")
    RETRY_ALL = N_("Rebuild the recipe from scratch")
    RETRY_STEP = N_("Rebuild starting from the failed step")
    SKIP = N_("Skip recipe")
    ABORT = N_("Abort")

    def __new__(klass):
        return [RecoveryActions.SHELL, RecoveryActions.RETRY_ALL,
                RecoveryActions.RETRY_STEP, RecoveryActions.SKIP,
                RecoveryActions.ABORT]


class Oven (object):
    '''
    This oven cooks recipes with all their ingredients

    @ivar recipes: Recipes to build
    @type: L{cerberos.recipe.recipe}
    @ivar cookbook: Cookbook with the recipes status
    @type: L{cerberos.cookbook.CookBook}
    @ivar force: Force the build of the recipes
    @type: bool
    @ivar no_deps: Ignore dependencies
    @type: bool
    @ivar missing_files: check for files missing in the recipes
    @type missing_files: bool
    @ivar dry_run: don't actually exectute the commands
    @type dry_run: bool
    @ivar deps_only: only build depenencies and not the recipes
    @type deps_only: bool
    '''

    def __init__(self, recipes, cookbook, force=False, no_deps=False,
                 missing_files=False, dry_run=False, deps_only=False, jobs=None):
        if isinstance(recipes, Recipe):
            recipes = [recipes]
        self.recipes = recipes
        self.cookbook = cookbook
        self.force = force
        self.no_deps = no_deps
        self.missing_files = missing_files
        self.config = cookbook.get_config()
        self.interactive = self.config.interactive
        self.deps_only = deps_only
        shell.DRY_RUN = dry_run
        self._build_lock = asyncio.Semaphore(2)
        self._install_lock = asyncio.Lock()
        self.jobs = jobs
        if not self.jobs:
            self.jobs = determine_num_of_cpus()

    def start_cooking(self):
        '''
        Cooks the recipe and all its dependencies
        '''
        recipes = [self.cookbook.get_recipe(x) for x in self.recipes]

        if self.no_deps:
            ordered_recipes = recipes
        else:
            ordered_recipes = []
            for recipe in self.recipes:
                deps = self.cookbook.list_recipe_deps(recipe)
                # remove recipes already scheduled to be built
                deps = [x for x in deps if x not in ordered_recipes]
                ordered_recipes.extend(deps)

        if self.deps_only:
            ordered_recipes = [x for x in ordered_recipes if x not in recipes]

        m.message(_("Building the following recipes: %s") %
                  ' '.join([x.name for x in ordered_recipes]))

        steps = [step[1] for step in recipes[0].steps]
        self._build_status_printer = BuildStatusPrinter(steps, self.interactive)
        self._static_libraries_built = []
        run_until_complete(self._cook_recipes(ordered_recipes))

    async def _cook_recipes(self, recipes):
        recipes = set(recipes)
        built_recipes = set()       # recipes we have successfully built
        building_recipes = set()    # recipes that are queued or are in progress

        def all_deps_without_recipe(recipe_name):
            return set((dep.name for dep in self.cookbook.list_recipe_deps(recipe_name) if recipe_name != dep.name))

        all_deps = set()
        for recipe in recipes:
            [all_deps.add(dep) for dep in all_deps_without_recipe(recipe.name)]

        # handle the 'buildone' case by adding all the recipe deps to the built
        # list if they are not in the recipe list
        if self.no_deps:
            [built_recipes.add(dep) for dep in (all_deps - set((r.name for r in recipes)))]
        else:
            [recipes.add(self.cookbook.get_recipe(dep)) for dep in all_deps]
        self._build_status_printer.total = len(recipes)

        # final targets.  The set of recipes with no reverse dependencies
        recipe_targets = set((r.name for r in recipes)) - all_deps

        # precompute the deps for each recipe
        recipe_deps = {}
        for r in set(set((r.name for r in recipes)) | all_deps):
            deps = all_deps_without_recipe(r)
            recipe_deps[r] = deps

        # precompute the reverse deps for each recipe
        def rdeps(recipe):
            ret = []
            for r, deps in recipe_deps.items():
                if recipe in deps:
                    ret.append(r)
            return ret

        recipe_rdeps = {}
        for r in recipe_deps.keys():
            recipe_rdeps[r] = rdeps(r)

        def find_recipe_dep_path(from_name, to_name):
            # returns a list of recipe names in reverse order that describes
            # the path for building @from_name
            # None if there is no path
            if from_name == to_name:
                return [to_name]
            for dep in recipe_deps[from_name]:
                val = find_recipe_dep_path(dep, to_name)
                if val:
                    return [from_name] + val

        def find_longest_path(to_recipes):
            # return the longest path from the targets to one of @to_recipes
            def yield_path_lengths():
                for f in recipe_targets:
                    for t in to_recipes:
                        path = find_recipe_dep_path(f, t)
                        if path:
                            yield len(path)
            return max((l for l in yield_path_lengths()))

        def find_buildable_recipes():
            # This is a dumb algorithm that only looks for all available
            # recipes that can be built.  We use a priority queue for
            # the smarts.
            for recipe in recipes:
                if recipe.name in built_recipes:
                    continue
                if recipe.name in building_recipes:
                    continue

                if len(recipe_deps[recipe.name]) == 0:
                    yield recipe
                    continue

                built_deps = set((dep for dep in recipe_deps[recipe.name] if dep in built_recipes))
                if len(built_deps) > 0 and built_deps == set(recipe_deps[recipe.name]):
                    # we have a new dep buildable
                    yield recipe

        class MutableInt:
            def __init__(self):
                self.i = 0
        counter = MutableInt()

        class RecipeStepPriority:
            # can't use a tuple as Recipe doens't implement __lt__() as
            # required by PriorityQueue
            def __init__(self, recipe, count, step):
                self.recipe = recipe
                self.step = step
                self.inverse_priority = find_longest_path((recipe.name,))
                self.inverse_priority *= len(recipe_rdeps[recipe.name]) + 1
                self.count = count

                if step is not None:
                    # buf already started recipes
                    self.inverse_priority *= 4
                if step is BuildSteps.INSTALL[1]:
                    # buf installs
                    self.inverse_priority *= 8
                if hasattr(recipe, "allow_parallel_build") \
                       and not recipe.allow_parallel_build:
                    self.inverse_priority *= 2

            def __lt__(self, other):
                # return lower for larger path lengths
                return self.inverse_priority > other.inverse_priority

        def recipe_next_step (recipe, step):
            assert (step is not None)
            if step is "init":
                return recipe.steps[0][1]
            found_current = False
            for _, s in recipe.steps:
                if found_current:
                    return s
                elif s == step:
                    found_current = True

        def add_buildable_recipes(recipe):
            built_recipes.add(recipe.name)
            building_recipes.remove(recipe.name)
            for buildable in find_buildable_recipes ():
                building_recipes.add(buildable.name)
                default_queue.put_nowait(RecipeStepPriority(buildable, 0, "init"))

        async def cook_recipe_worker(q, steps):
            while True:
                recipe_d = await q.get()
                recipe = recipe_d.recipe
                step = recipe_d.step
                count = recipe_d.count

                if step is "init":
                    counter.i += 1
                    count = counter.i
                    if self._cook_start_recipe (recipe, count, len(recipes)):
                        add_buildable_recipes(recipe)
                        q.task_done()
                        continue
                    step = recipe_next_step (recipe, step)

                lock = locks[step]
                if step == BuildSteps.COMPILE[1]:
                    if not hasattr(recipe, "allow_parallel_build") \
                       or not recipe.allow_parallel_build:
                        # only allow a limited number of recipes that can fill all
                        # CPU cores to execute concurrently.  Any recipe that does
                        # not support parallel builds will always be executed
                        lock = None

                async def build_recipe_steps(step):
                    # run the steps
                    while step in steps:
                        await self._cook_recipe_step_with_prompt (recipe, step, count, len(recipes))
                        step = recipe_next_step (recipe, step)
                    return step

                if lock:
                    async with lock:
                        step = await build_recipe_steps(step)
                else:
                    step = await build_recipe_steps(step)

                if step is None:
                    self._cook_finish_recipe (recipe, counter.i, len(recipes))
                    add_buildable_recipes(recipe)
                    next_queue = None
                else:
                    next_queue = queues[step]

                q.task_done()
                if next_queue:
                    next_queue.put_nowait(RecipeStepPriority(recipe, count, step))

        # all the steps we are performing
        all_steps = ["init"] + [s[1] for s in next(iter(recipes)).steps]

        # async queues used for each step
        loop = asyncio.get_event_loop()
        default_queue = asyncio.PriorityQueue(loop=loop)
        queues = {step : default_queue for step in all_steps}

        # find the install steps for ensuring consistency between all of them
        install_steps = []
        step = BuildSteps.INSTALL[1]
        while step:
            install_steps.append(step)
            step = recipe_next_step(next(iter(recipes)), step)

        # allocate jobs
        job_allocation = collections.defaultdict(lambda : 0)
        if self.jobs > 4:
            queues[BuildSteps.COMPILE[1]] = asyncio.PriorityQueue(loop=loop)
            job_allocation[BuildSteps.COMPILE[1]] = min(2, self.jobs - 3)
        if self.jobs > 5:
            job_allocation[BuildSteps.COMPILE[1]] = 3
        if self.jobs > 7:
            install_queue = asyncio.PriorityQueue(loop=loop)
            for step in install_steps:
                queues[step] = install_queue
            job_allocation[BuildSteps.INSTALL[1]] = 1
        if self.jobs > 8:
            job_allocation[BuildSteps.EXTRACT[1]] = 1
            queues[BuildSteps.EXTRACT[1]] = asyncio.PriorityQueue(loop=loop)
        if self.jobs > 9:
            job_allocation[BuildSteps.FETCH[1]] = 1
            queues[BuildSteps.FETCH[1]] = asyncio.PriorityQueue(loop=loop)

        # async locks used to synchronize step execution
        locks = collections.defaultdict(lambda : None)

        # create the jobs
        tasks = []
        used_jobs = 0
        used_steps = []
        install_done = False
        for step, count in job_allocation.items():
            if count <= 0:
                continue
            if step in install_steps:
                # special case install as that also needs to be sequential
                # through all the steps after
                if install_done:
                    continue
                tasks.append(asyncio.create_task(cook_recipe_worker(queues[step], install_steps)))
                used_steps.extend(install_steps)
                install_done = True
            else:
                for i in range(count):
                    tasks.append(asyncio.create_task(cook_recipe_worker(queues[step], [step])))
                used_steps.append(step)
            used_jobs += count
        general_jobs = self.jobs - used_jobs
        assert (general_jobs > 0)

        if job_allocation[BuildSteps.INSTALL[1]] == 0 and general_jobs > 1:
            locks[BuildSteps.INSTALL[1]] = self._install_lock
        if job_allocation[BuildSteps.COMPILE[1]] > 2 or job_allocation[BuildSteps.COMPILE[1]] == 0 and general_jobs > 2:
            locks[BuildSteps.COMPILE[1]] = self._build_lock

        job_allocation_msg = ", ".join([str(step) + ": " + str(count) for step, count in job_allocation.items() if count > 0])
        if used_jobs > 0:
            job_allocation_msg += ", and "
        m.output ("Building using " + str(self.jobs) + " job(s) with the following job subdivisions: " + job_allocation_msg + str(self.jobs - used_jobs) + " general job(s)", sys.stdout)

        for i in range(self.jobs - used_jobs):
            tasks.append(asyncio.create_task(cook_recipe_worker(default_queue, set(all_steps) - set(used_steps))))

        async def recipes_done():
            while built_recipes & recipe_targets != recipe_targets:
                for q in queues.values():
                    await q.join()

        # push the initial set of recipes that have no dependencies to start
        # building
        for recipe in find_buildable_recipes ():
            building_recipes.add(recipe.name)
            default_queue.put_nowait(RecipeStepPriority(recipe, 0, "init"))

        try:
            await run_tasks(tasks, recipes_done())
            m.output(_("All done!"), sys.stdout)
        except Exception as e:
            raise e

    async def _cook_recipe_step_with_prompt (self, recipe, step, count, total):
        try:
            await self._cook_recipe_step(recipe, step, count, total)
        except BuildStepError as be:
            if not self.interactive:
                raise be
            print()
            msg = be.msg
            msg += _("Select an action to proceed:")
            action = shell.prompt_multiple(msg, RecoveryActions())
            if action == RecoveryActions.SHELL:
                shell.enter_build_environment(self.config.target_platform,
                        be.arch, recipe.get_for_arch (be.arch, 'build_dir'), env=recipe.config.env)
                raise be
            elif action == RecoveryActions.RETRY_ALL:
                shutil.rmtree(recipe.get_for_arch (be.arch, 'build_dir'))
                self.cookbook.reset_recipe_status(recipe.name)
                await self._cook_recipe_step(recipe, step, count, total)
            elif action == RecoveryActions.RETRY_STEP:
                await self._cook_recipe_step(recipe, step, count, total)
            elif action == RecoveryActions.SKIP:
                pass
            elif action == RecoveryActions.ABORT:
                raise AbortedError()

    async def _cook_recipe_step (self, recipe, step, count, total):
       # check if the current step needs to be done
        if self.cookbook.step_done(recipe.name, step) and not self.force:
            self._build_status_printer.update_recipe_step(count, total, recipe.name, step)
            return
        try:
            # call step function
            stepfunc = getattr(recipe, step)
            if not stepfunc:
                self._build_status_printer.update_recipe_step(count, total, recipe.name, step)
                raise FatalError(_('Step %s not found') % step)

            self._build_status_printer.update_recipe_step(count, total, recipe.name, step)
            ret = stepfunc()
            if asyncio.iscoroutine(ret):
                await ret
            self._build_status_printer.remove_recipe(recipe.name)
            # update status successfully
            self.cookbook.update_step_status(recipe.name, step)
        except asyncio.CancelledError:
            raise
        except FatalError as e:
            exc_traceback = sys.exc_info()[2]
            trace = ''
            # Don't print trace if the FatalError is merely that the
            # subprocess exited with a non-zero status. The traceback
            # is just confusing and useless in that case.
            if not isinstance(e.__context__, CalledProcessError):
                tb = traceback.extract_tb(exc_traceback)[-1]
                if tb.filename.endswith('.recipe'):
                    # Print the recipe and line number of the exception
                    # if it starts in a recipe
                    trace += 'Exception at {}:{}\n'.format(tb.filename, tb.lineno)
                trace += e.args[0] + '\n'
            self._handle_build_step_error(recipe, step, trace, e.arch)
        except Exception:
            raise BuildStepError(recipe, step, traceback.format_exc())

    def _cook_start_recipe(self, recipe, count, total):
        # A Recipe depending on a static library that has been rebuilt
        # also needs to be rebuilt to pick up the latest build.
        if recipe.library_type != LibraryType.STATIC:
            if len(set(self._static_libraries_built) & set(recipe.deps)) != 0:
                self.cookbook.reset_recipe_status(recipe.name)

        if not self.cookbook.recipe_needs_build(recipe.name) and \
                not self.force:
            self._build_status_printer.already_built(count, total, recipe.name)
            return True

        if self.missing_files:
            # create a temp file that will be used to find newer files
            recipe._oven_missing_files_tmp_file = tempfile.NamedTemporaryFile()

        recipe.force = self.force
        return False

    def _cook_finish_recipe(self, recipe, count, total):
        self._build_status_printer.built(count, total, recipe.name)
        self.cookbook.update_build_status(recipe.name, recipe.built_version())
        if recipe.library_type == LibraryType.STATIC:
            self._static_libraries_built.append(recipe.name)

        if self.missing_files:
            self._print_missing_files(recipe, recipe._oven_missing_files_tmp_file)
            recipe._oven_missing_files_tmp_file.close()

    def _handle_build_step_error(self, recipe, step, trace, arch):
        if step in [BuildSteps.FETCH, BuildSteps.EXTRACT]:
            # if any of the source steps failed, wipe the directory and reset
            # the recipe status to start from scratch next time
            shutil.rmtree(recipe.build_dir)
            self.cookbook.reset_recipe_status(recipe.name)
        raise BuildStepError(recipe, step, trace=trace, arch=arch)

    def _print_missing_files(self, recipe, tmp):
        recipe_files = set(recipe.files_list())
        installed_files = set(shell.find_newer_files(recipe.config.prefix,
                                                     tmp.name))
        not_in_recipe = list(installed_files - recipe_files)
        not_installed = list(recipe_files - installed_files)

        if len(not_in_recipe) != 0:
            m.message(_("The following files were installed, but are not "
                        "listed in the recipe:"))
            m.message('\n'.join(sorted(not_in_recipe)))

        if len(not_installed) != 0:
            m.message(_("The following files are listed in the recipe, but "
                        "were not installed:"))
            m.message('\n'.join(sorted(not_installed)))
