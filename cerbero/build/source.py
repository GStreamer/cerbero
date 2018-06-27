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
import tarfile
import urllib.request, urllib.parse, urllib.error

from cerbero.config import Platform
from cerbero.utils import git, svn, shell, _
from cerbero.errors import FatalError, InvalidRecipeError
import cerbero.utils.messages as m

# Must end in a / for urlparse.urljoin to work correctly
TARBALL_MIRROR = 'https://gstreamer.freedesktop.org/src/mirror/'

class Source (object):
    '''
    Base class for sources handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    @cvar patches: list of patches to apply
    @type patches: list
    @cvar strip: number passed to the --strip 'patch' option
    @type patches: int
    '''

    patches = []
    strip = 1
    offline = False

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
    '''

    url = None
    tarball_name = None
    tarball_dirname = None
    mirror_url = None

    def __init__(self):
        Source.__init__(self)
        if not self.url:
            raise InvalidRecipeError(
                _("'url' attribute is missing in the recipe"))
        self.url = self.replace_name_and_version(self.url)
        if self.tarball_name is not None:
            self.tarball_name = \
                self.replace_name_and_version(self.tarball_name)
        else:
            self.tarball_name = os.path.basename(self.url)
        if self.tarball_dirname is not None:
            self.tarball_dirname = \
                self.replace_name_and_version(self.tarball_dirname)
        self.download_path = os.path.join(self.repo_dir, self.tarball_name)
        # URL-encode spaces and other special characters in the URL's path
        split = list(urllib.parse.urlsplit(self.url))
        split[2] = urllib.parse.quote(split[2])
        self.url = urllib.parse.urlunsplit(split)
        self.mirror_url = urllib.parse.urljoin(TARBALL_MIRROR, self.tarball_name)
        o = urllib.parse.urlparse(self.url)
        if o.scheme in ('http', 'ftp'):
            raise FatalError('Download URL {!r} must use HTTPS'.format(self.url))

    def fetch(self, redownload=False):
        if not os.path.exists(self.repo_dir):
            os.makedirs(self.repo_dir)

        cached_file = os.path.join(self.config.cached_sources,
                                   self.package_name, self.tarball_name)
        if not redownload and os.path.isfile(cached_file):
            m.action(_('Copying cached tarball from %s to %s instead of %s') %
                     (cached_file, self.download_path, self.url))
            shutil.copy(cached_file, self.download_path)
            return
        if self.offline:
            if not os.path.isfile(self.download_path):
                msg = 'Offline mode: tarball {!r} not found in cached sources ({}) or local sources ({})'
                raise FatalError(msg.format(self.tarball_name, self.config.cached_sources, self.repo_dir))
            m.action(_('Found tarball for %s at %s') % (self.url, self.download_path))
            return
        m.action(_('Fetching tarball %s to %s') %
                 (self.url, self.download_path))
        # Enable certificate checking only on Linux for now
        # FIXME: Add more platforms here after testing
        cc = self.config.platform == Platform.LINUX
        try:
            shell.download(self.url, self.download_path, check_cert=cc,
                           overwrite=redownload)
        except (FatalError, urllib.error.URLError):
            # Try our mirror
            shell.download(self.mirror_url, self.download_path, check_cert=cc,
                           overwrite=redownload)

    def extract(self):
        m.action(_('Extracting tarball to %s') % self.build_dir)
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
        try:
            shell.unpack(self.download_path, self.config.sources)
        except (IOError, EOFError, tarfile.ReadError):
            m.action(_('Corrupted or partial tarball, redownloading...'))
            self.fetch(redownload=True)
            shell.unpack(self.download_path, self.config.sources)
        if self.tarball_dirname is not None:
            os.rename(os.path.join(self.config.sources, self.tarball_dirname),
                    self.build_dir)
        git.init_directory(self.build_dir)
        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)
            if self.strip == 1:
                git.apply_patch(patch, self.build_dir)
            else:
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
        self._previous_env = None

    def _git_env_setup(self):
        # When running git commands, which is the host git, we need to make
        # sure it is run in an environment which doesn't pick up the libraries
        # we build in cerbero
        env = os.environ.copy()
        self._previous_env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = self.config._pre_environ.get("LD_LIBRARY_PATH", "")
        os.environ = env

    def _git_env_restore(self):
        if self._previous_env is not None:
            os.environ = self._previous_env
            self._previous_env = None

    def fetch(self, checkout=True):
        self._git_env_setup()
        # First try to get the sources from the cached dir if there is one
        cached_dir = os.path.join(self.config.cached_sources,  self.name)

        if not os.path.exists(self.repo_dir):
            if not cached_dir and offline:
                msg = 'Offline mode: git repo for {!r} not found in cached sources ({}) or local sources ({})'
                raise FatalError(msg.format(self.name, self.config.cached_sources, self.repo_dir))
            git.init(self.repo_dir)

        if os.path.isdir(os.path.join(cached_dir, ".git")):
            for remote, url in self.remotes.items():
                git.add_remote(self.repo_dir, remote, "file://" + cached_dir)
            for remote, url in self.config.recipe_remotes(self.name).items():
                git.add_remote(self.repo_dir, remote, "file://" + cached_dir)
            git.fetch(self.repo_dir, fail=False)
        else:
            cached_dir = None
            # add remotes from both upstream and config so user can easily
            # cherry-pick patches between branches
            for remote, url in self.remotes.items():
                git.add_remote(self.repo_dir, remote, url)
            for remote, url in self.config.recipe_remotes(self.name).items():
                git.add_remote(self.repo_dir, remote, url)
            # fetch remote branches
            if not self.offline:
                git.fetch(self.repo_dir, fail=False)
        if checkout:
            commit = self.config.recipe_commit(self.name) or self.commit
            git.checkout(self.repo_dir, commit)
            git.submodules_update(self.repo_dir, cached_dir, fail=False, offline=self.offline)
        self._git_env_restore()


    def built_version(self):
        return '%s+git~%s' % (self.version, git.get_hash(self.repo_dir, self.commit))


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
            # Used by recipes in recipes/toolchain/
            self.commit = 'origin/sdk-%s' % self.version
        # For forced commits in the config
        self.commit = self.config.recipe_commit(self.name) or self.commit

    def extract(self):
        if os.path.exists(self.build_dir):
            try:
                commit_hash = git.get_hash(self.repo_dir, self.commit)
                checkout_hash = git.get_hash(self.build_dir, 'HEAD')
                if commit_hash == checkout_hash and not self.patches:
                    return False
            except Exception:
                pass
            shutil.rmtree(self.build_dir)
        if not os.path.exists(self.build_dir):
            os.mkdir(self.build_dir)

        # checkout the current version
        git.local_checkout(self.build_dir, self.repo_dir, self.commit)

        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)

            if self.strip == 1:
                git.apply_patch(patch, self.build_dir)
            else:
                shell.apply_patch(patch, self.build_dir, self.strip)

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
        self._files['.in'] = [x for x in self._files['.in'] if
                os.path.join(self.build_dir, 'm4') not in x]
        self._fix_ts()

    def _fix_ts(self):
        for match in self.matches:
            for path in self._files[match]:
                shell.touch(path)

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
        # For forced revision in the config
        self.revision = self.config.recipe_commit(self.name) or self.revision

    def fetch(self):
        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)

        cached_dir = os.path.join(self.config.cached_sources, self.package_name)
        if os.path.isdir(os.path.join(cached_dir, ".svn")):
            m.action(_('Copying cached repo from %s to %s instead of %s') %
                     (cached_dir, self.repo_dir, self.url))
            shell.copy_dir(cached_dir, self.repo_dir)
            return

        os.makedirs(self.repo_dir)
        if self.offline:
            raise FatalError('Offline mode: no cached svn repos found for {} at {!r}'
                             ''.format(self.package_name, self.config.cached_sources))
        svn.checkout(self.url, self.repo_dir)
        svn.update(self.repo_dir, self.revision)

    def extract(self):
        if os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)

        shutil.copytree(self.repo_dir, self.build_dir)

        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)
            shell.apply_patch(patch, self.build_dir, self.strip)

    def built_version(self):
        return '%s+svn~%s' % (self.version, svn.revision(self.repo_dir))


class SourceType (object):

    CUSTOM = CustomSource
    TARBALL = Tarball
    LOCAL_TARBALL = LocalTarball
    GIT = Git
    GIT_TARBALL = GitExtractedTarball
    SVN = Svn
