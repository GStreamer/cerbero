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

from cerbero.config import Platform
from cerbero.utils import git, svn, shell, _
from cerbero.errors import FatalError, InvalidRecipeError
import cerbero.utils.messages as m


class Source (object):
    '''
    Base class for sources handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    supports_non_src_build = False

    def fetch(self):
        '''
        Fetch the sources
        '''
        raise NotImplemented("'fetch' must be implemented by subclasses")

    def extract(self):
        '''
        Extracts the sources
        '''
        raise NotImplemented("'extract' must be implemented by subclasses")

    def replace_name_and_version(self, string):
        '''
        Replaces name and version in strings
        '''
        return string % {'name': self.name, 'version': self.version}


class CustomSource (Source):

    def fetch(self):
        pass

    def extract(self):
        pass


class Tarball (Source):
    '''
    Source handler for tarballs

    @cvar url: dowload URL for the tarball
    @type url: str
    @cvar patches: list of patches to apply
    @type patches: list
    @cvar strip: number passed to the --strip 'patch' option
    @type patches: int
    '''

    url = None
    patches = []
    strip = 1
    tarball_name = None
    tarball_dirname = None

    def __init__(self):
        Source.__init__(self)
        if not self.url:
            raise InvalidRecipeError(_("'url' attribute is missing in the recipe"))
        self.url = self.replace_name_and_version(self.url)
        if self.tarball_name is not None:
            self.tarball_name = self.replace_name_and_version(self.tarball_name)
        else:
            self.tarball_name = os.path.basename(self.url)
        self.download_path = os.path.join(self.repo_dir, self.tarball_name)

    def fetch(self):
        m.action(_('Fetching tarball %s to %s') %
                 (self.url, self.download_path))
        if not os.path.exists(self.repo_dir):
            os.makedirs(self.repo_dir)
        shell.download(self.url, self.download_path, check_cert=False)

    def extract(self):
        m.action(_('Extracting tarball to %s') % self.build_dir)
        shell.unpack(self.download_path, self.config.sources)
        if self.tarball_dirname is not None:
            if os.path.exists(self.build_dir):
                shutil.rmtree(self.build_dir)
            os.rename(os.path.join(self.config.sources, self.tarball_dirname),
                    self.build_dir)
        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)
            shell.apply_patch(patch, self.build_dir, self.strip)



class GitCache (Source):
    '''
    Base class for source handlers using a Git repository
    '''

    remotes = None
    commit = None

    def __init__(self):
        Source.__init__(self)
        if self.remotes is None:
            self.remotes = {}
        if not 'origin' in self.remotes:
            self.remotes['origin'] = '%s/%s.git' % \
                                     (self.config.git_root, self.name)
        self.repo_dir = os.path.join(self.config.local_sources, self.name)

    def fetch(self):
        if not os.path.exists(self.repo_dir):
            git.init(self.repo_dir)
        for remote, url in self.remotes.iteritems():
            git.add_remote(self.repo_dir, remote, url)
        # fetch remote branches
        git.fetch(self.repo_dir, fail=False)
        commit = self.config.force_git_commit or self.commit
        git.checkout(self.repo_dir, commit)


class LocalTarball (GitCache):
    '''
    Source handler for cerbero's local sources, a local git repository with
    the release tarball and a set of patches
    '''

    BRANCH_PREFIX = 'sdk'

    def __init__(self):
        GitCache.__init__(self)
        self.commit = "%s/%s-%s" % ('origin',
                                    self.BRANCH_PREFIX, self.version)
        self.platform_patches_dir = os.path.join(self.repo_dir,
                                                 self.config.platform)
        self.package_name = self.package_name
        self.unpack_dir = self.config.sources

    def extract(self):
        if not os.path.exists(self.build_dir):
            os.mkdir(self.build_dir)
        self._find_tarball()
        shell.unpack(self.tarball_path, self.unpack_dir)
        # apply common patches
        self._apply_patches(self.repo_dir)
        # apply platform patches
        self._apply_patches(self.platform_patches_dir)

    def _find_tarball(self):
        tarball = [x for x in os.listdir(self.repo_dir) if
                   x.startswith(self.package_name)]
        if len(tarball) != 1:
            raise FatalError(_("The local repository %s do not have a "
                                "valid tarball") % self.repo_dir)
        self.tarball_path = os.path.join(self.repo_dir, tarball[0])

    def _apply_patches(self, patches_dir):
        if not os.path.isdir(patches_dir):
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

    def __init__(self):
        GitCache.__init__(self)
        if self.commit is None:
            self.commit = 'origin/sdk-%s' % self.version

    def extract(self):
        if os.path.exists(self.build_dir):
            # fix read-only permissions
            if self.config.platform == Platform.WINDOWS:
                shell.call('chmod -R +w .git/', self.build_dir, fail=False)
            try:
                commit_hash = git.get_hash(self.repo_dir, self.commit)
                checkout_hash = git.get_hash(self.build_dir, 'HEAD')
                if commit_hash == checkout_hash:
                    return False
            except Exception:
                pass
            shutil.rmtree(self.build_dir)
        if not os.path.exists(self.build_dir):
            os.mkdir(self.build_dir)
        if self.supports_non_src_build:
            return

        # checkout the current version
        git.local_checkout(self.build_dir, self.repo_dir, self.commit)
        return True


class GitExtractedTarball(Git):
    '''
    Source handle for git repositories with an extracted tarball

    Git doesn't conserve timestamps, which are reset after clonning the repo.
    This can confuse the autotools build system, producing innecessary calls
    to autoconf, aclocal, autoheaders or automake.
    For instance after doing './configure && make', 'configure' is called
    again if 'configure.ac' is newer than 'configure'.
    '''

    matches = ['.m4', '.in', 'configure']
    _files = {}

    def extract(self):
        if not Git.extract(self):
            return False
        for match in self.matches:
            self._files[match] = []
        self._find_files(self.build_dir)
        self._fix_ts()

    def _fix_ts(self):
        for match in self.matches:
            for path in self._files[match]:
                shell.call('touch %s' % path)

    def _find_files(self, directory):
        for path in os.listdir(directory):
            full_path = os.path.join(directory, path)
            if os.path.isdir(full_path):
                self._find_files(full_path)
            if path == 'configure.in':
                continue
            for match in self.matches:
                if path.endswith(match):
                    self._files[match].append(full_path)

class Svn(Source):
    '''
    Source handler for svn repositories
    '''

    url = None
    revision = 'HEAD'

    def __init__(self):
        Source.__init__(self)

    def fetch(self):
        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)
        os.makedirs(self.repo_dir)
        svn.checkout(self.url, self.repo_dir)
        svn.update(self.repo_dir, self.revision)

    def extract(self):
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)

        if self.supports_non_src_build:
            return

        shutil.copytree(self.repo_dir, self.build_dir)


class SourceType (object):

    CUSTOM = CustomSource
    TARBALL = Tarball
    LOCAL_TARBALL = LocalTarball
    GIT = Git
    GIT_TARBALL = GitExtractedTarball
    SVN = Svn
