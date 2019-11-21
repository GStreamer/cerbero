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

import os, sys
import urllib
import json
import asyncio
import tempfile
import shutil

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.errors import FatalError
from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import _, N_, ArgparseArgument, remove_list_duplicates, git, shell
from cerbero.utils import messages as m
from cerbero.build.source import Tarball
from cerbero.config import Distro


class Fetch(Command):

    def __init__(self, args=[]):
        args.append(ArgparseArgument('--reset-rdeps', action='store_true',
                    default=False, help=_('reset the status of reverse '
                    'dependencies too')))
        args.append(ArgparseArgument('--print-only', action='store_true',
                    default=False, help=_('print all source URLs to stdout')))
        args.append(ArgparseArgument('--full-reset', action='store_true',
                    default=False, help=_('reset to extract step if rebuild is needed')))
        Command.__init__(self, args)

    @staticmethod
    def fetch(cookbook, recipes, no_deps, reset_rdeps, full_reset, print_only):
        fetch_recipes = []
        if not recipes:
            fetch_recipes = cookbook.get_recipes_list()
        elif no_deps:
            fetch_recipes = [cookbook.get_recipe(x) for x in recipes]
        else:
            for recipe in recipes:
                fetch_recipes += cookbook.list_recipe_deps(recipe)
            fetch_recipes = remove_list_duplicates (fetch_recipes)
        m.message(_("Fetching the following recipes: %s") %
                  ' '.join([x.name for x in fetch_recipes]))
        to_rebuild = []
        for i in range(len(fetch_recipes)):
            recipe = fetch_recipes[i]
            if print_only:
                # For now just print tarball URLs
                if isinstance(recipe, Tarball):
                    m.message("TARBALL: {} {}".format(recipe.url, recipe.tarball_name))
                continue
            m.build_step(i + 1, len(fetch_recipes), recipe, 'Fetch')
            stepfunc = getattr(recipe, 'fetch')
            if asyncio.iscoroutinefunction(stepfunc):
                loop = asyncio.get_event_loop()
                loop.run_until_complete(stepfunc(recipe))
            else:
                stepfunc()
            bv = cookbook.recipe_built_version(recipe.name)
            cv = recipe.built_version()
            if bv != cv:
                # On different versions, only reset recipe if:
                #  * forced
                #  * OR it was fully built already
                if full_reset or not cookbook.recipe_needs_build(recipe.name):
                    to_rebuild.append(recipe)
                    cookbook.reset_recipe_status(recipe.name)
                    if reset_rdeps:
                        for r in cookbook.list_recipe_reverse_deps(recipe.name):
                            to_rebuild.append(r)
                            cookbook.reset_recipe_status(r.name)

        if to_rebuild:
            to_rebuild = sorted(list(set(to_rebuild)), key=lambda r:r.name)
            m.message(_("These recipes have been updated and will "
                        "be rebuilt:\n%s") %
                        '\n'.join([x.name for x in to_rebuild]))


class FetchRecipes(Fetch):
    doc = N_('Fetch the recipes sources')
    name = 'fetch'

    def __init__(self):
        args = [
                ArgparseArgument('recipes', nargs='*',
                    help=_('list of the recipes to fetch (fetch all if none '
                           'is passed)')),
                ArgparseArgument('--no-deps', action='store_true',
                    default=False, help=_('do not fetch dependencies')),
                ]
        Fetch.__init__(self, args)

    def run(self, config, args):
        cookbook = CookBook(config)
        return self.fetch(cookbook, args.recipes, args.no_deps,
                          args.reset_rdeps, args.full_reset, args.print_only)


class FetchPackage(Fetch):
    doc = N_('Fetch the recipes sources from a package')
    name = 'fetch-package'

    def __init__(self):
        args = [
                ArgparseArgument('package', nargs=1,
                    help=_('package to fetch')),
                ArgparseArgument('--deps', action='store_false',
                    default=True, help=_('also fetch dependencies')),
                ]
        Fetch.__init__(self, args)

    def run(self, config, args):
        store = PackagesStore(config)
        package = store.get_package(args.package[0])
        return self.fetch(store.cookbook, package.recipes_dependencies(),
                          args.deps, args.reset_rdeps, args.full_reset,
                          args.print_only)

class FetchCache(Command):
    doc = N_('Fetch a cached build from GitLab CI based on cerbero git '
            'revision.')
    name = 'fetch-cache'

    base_url = 'https://gitlab.freedesktop.org/%s/cerbero/-/jobs'
    build_dir = '/builds/%s/cerbero/cerbero-build'
    log_size = 50

    def __init__(self, args=[]):
        args.append(ArgparseArgument('--commit', action='store', type=str,
                    default='HEAD', help=_('the commit to pick artifact from')))
        args.append(ArgparseArgument('--namespace', action='store', type=str,
                    default='gstreamer', help=_('GitLab namespace to search from')))
        args.append(ArgparseArgument('--branch', action='store', type=str,
                    default='master', help=_('Git branch to search from')))
        args.append(ArgparseArgument('--job-id', action='store', type=str,
                    default='master', help=_('Artifact job id, this will skip'
                        ' commit matching')))
        args.append(ArgparseArgument('--skip-fetch', action='store_true',
                    default=False, help=_('Skip fetching cached build, the '
                        'commit/url log will be updated if --job-id is present')))
        Command.__init__(self, args)

    def request(self, url, values, token=None):
        headers = {}
        if token:
            headers = {"Private-Token": token}

        data = urllib.parse.urlencode(values)
        url = "%s?%s" % (url, data)

        m.message("GET %s" % url)

        tmpdir = tempfile.mkdtemp()
        tmpfile = os.path.join(tmpdir, 'deps.json')

        try:
            shell.download(url, destination=tmpfile)
        except urllib.error.URLError as e:
            raise FatalError(_(e.reason))

        with open(tmpfile, 'r') as f:
            resp = f.read()
        shutil.rmtree(tmpdir)

        return json.loads(resp)

    def get_deps(self, config, args):
        namespace = args.namespace
        branch = args.branch
        distro = config.target_distro
        arch = config.target_arch
        if distro == Distro.REDHAT:
            distro = 'fedora'
        if distro == Distro.OS_X:
            distro = 'macos'

        base_url = self.base_url % namespace
        url = "%s/artifacts/%s/raw/cerbero-build/cerbero-deps.log" % (base_url, branch)

        deps = []
        try:
            deps = self.request(url, values = {
                    'job': "cerbero deps %s %s" % (distro, arch)
                    })
        except FatalError as e:
            m.warning("Could not get cache list: %s" % e.msg)

        return deps

    def find_dep(self, deps, sha):
        for dep in deps:
            if dep['commit'] == sha:
                return dep

        m.warning("Did not find cache for commit %s" % sha)
        return None

    def fetch_dep(self, config, dep, namespace):
        try:
            artifacts_path = "%s/cerbero-deps.tar.gz" % config.home_dir
            shell.download(dep['url'], artifacts_path, check_cert=True, overwrite=True)
            shell.unpack(artifacts_path, config.home_dir)
            os.remove(artifacts_path)
            origin = self.build_dir % namespace
            m.message("Relocating from %s to %s" % (origin, config.home_dir))
            # FIXME: Just a quick hack for now
            shell.call(("grep -lnrIU %(origin)s | xargs "
                        "sed \"s#%(origin)s#%(dest)s#g\" -i") % {
                            'origin': origin, 'dest': config.home_dir},
                        config.home_dir)
        except FatalError as e:
            m.warning(("Could not retrieve artifact for commit %s (the artifact "
                    "may have expired): %s") % (dep['commit'], e.msg))

    def update_log(self, config, args, deps, sha):
        base_url = self.base_url % args.namespace
        url = "%s/%s/artifacts/raw/cerbero-deps.tar.gz" % (base_url, args.job_id)
        deps.insert(0, {'commit': sha, 'url': url})
        deps = deps[0:self.log_size]
        with open("%s/cerbero-deps.log" % config.home_dir, 'w') as outfile:
                json.dump(deps, outfile, indent=1)

    def run(self, config, args):
        if not config.uninstalled:
            raise FatalError(_("fetch-cache is only available with "
                        "cerbero-uninstalled"))

        git_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        sha = git.get_hash(git_dir, args.commit)
        deps = self.get_deps(config, args)
        if not args.skip_fetch:
            dep = self.find_dep(deps, sha)
            if dep:
                self.fetch_dep(config, dep, args.namespace)
        if args.job_id:
            self.update_log(config, args, deps, sha)

register_command(FetchRecipes)
register_command(FetchPackage)
register_command(FetchCache)
