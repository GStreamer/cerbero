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
import shutil

from cerbero.utils import git, shell, _
from cerbero.errors import FatalError


def get_handler (recipe, config):
    '''
    Returns a L{cerbero.source.Source} for a L{cerbero.recipe.Recipe}

    @param config: cerbero's configuration
    @type: L{cerbero.config.Config}
    @param recipe: the recipe to fetch
    @type: L{cerbero.recipe.Recipe}
    '''
    try:
        source = recipe.stype(recipe, config)
    except Exception:
        import traceback; traceback.print_exc()
        raise FatalError(_("Could not find a source handler for %s") %
                         recipe.stype)
    return source


class Source (object):
    '''
    Base class for sources handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    _properties_keys = []

    def __init__(self, recipe, config):
        self.recipe = recipe
        self.config = config
        for conf in self._properties_keys:
            if hasattr(recipe, conf):
                setattr(self, conf, getattr(recipe, conf))

    def fetch (self):
        '''
        Fetch the sources
        '''
        raise NotImplemented ("'fetch' must be implemented by subclasses")

    def extract (self):
        '''
        Extracts the sources
        '''
        raise NotImplemented ("'extrat' must be implemented by subclasses")


class GitCache (Source):
    '''
    Base class for source handlers using a Git repository
    '''

    remotes = None
    commit =  None

    _properties_keys = ['commit', 'remotes']

    def __init__ (self, recipe, config):
        Source.__init__ (self, recipe, config)
        if self.remotes is None:
            self.remotes = {'origin': '%s/%s' % (config.git_root, recipe.name)}
        self.repo_dir = os.path.join(config.local_sources, recipe.name)
        self.build_dir = os.path.join(config.sources, recipe.package_name)

    def fetch (self):
        if not os.path.exists (self.repo_dir):
            git.init(self.repo_dir)
        for remote, url in self.remotes.iteritems():
            git.add_remote (self.repo_dir, remote, url)
        # fetch remote branches
        git.fetch (self.repo_dir, fail=False)


class LocalTarball (GitCache):
    '''
    Source handler for cerbero's local sources, a local git repository with
    the release tarball and a set of patches
    '''

    BRANCH_PREFIX = 'sdk'

    def __init__(self, recipe, config):
        GitCache.__init__(self, recipe, config)
        self.commit = "%s/%s-%s" % ('origin', self.BRANCH_PREFIX, recipe.version)
        self.platform_patches_dir = os.path.join(self.repo_dir, config.platform)
        self.package_name = recipe.package_name
        self.unpack_dir = config.sources

    def extract (self):
        if not os.path.exists (self.build_dir):
            os.mkdir (self.build_dir)
        self._find_tarball ()
        shell.unpack (self.tarball_path, self.unpack_dir)
        # apply common patches
        self._apply_patches(self.repo_dir)
        # apply platform patches
        self._apply_patches(self.platform_patches_dir)

    def _find_tarball (self):
        tarball = [x for x in os.listdir(self.repo_dir) if
                   x.startswith(self.package_name)]
        if len(tarball) != 1:
            raise FatalError (_("The local repository %s do not have a "
                                "valid tarball") % self.repo_dir)
        self.tarball_path = os.path.join(self.repo_dir, tarball[0])

    def _apply_patches (self, patches_dir):
        if not os.path.isdir (patches_dir):
            # FIXME: Add logs
            return

        # list patches in this directory
        patches = [os.path.join(patches_dir, x) for x in
                   os.listdir(patches_dir) if x.endswith('.patch')]
        # apply patches
        for patch in patches:
            shell.apply_patch(self.build_dir, patch)


class Git (GitCache):
    '''
    Source handler for git repositories
    '''

    def __init__ (self, recipe, config):
        GitCache.__init__ (self, recipe, config)
        if self.commit is None:
            self.commit = 'origin/sdk-%s' % self.recipe.version

    def extract (self):
        if os.path.exists (self.build_dir):
            shutil.rmtree(self.build_dir)
        if not os.path.exists (self.build_dir):
            os.mkdir(self.build_dir)
        # checkout the current version
        git.local_checkout (self.build_dir, self.repo_dir, self.commit)


class SourceType (object):
    LOCAL_TARBALL = LocalTarball
    GIT = Git
