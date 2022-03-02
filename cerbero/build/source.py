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
import zipfile
import tarfile
import urllib.request, urllib.parse, urllib.error
import collections
import asyncio
from hashlib import sha256

from cerbero.config import Distro, DistroVersion, Platform, DEFAULT_MIRRORS
from cerbero.utils import git, svn, shell, _, run_until_complete
from cerbero.errors import FatalError, CommandError, InvalidRecipeError
import cerbero.utils.messages as m

URL_TEMPLATES = {
    'gnome': ('https://download.gnome.org/sources/', '%(name)s/%(maj_ver)s/%(name)s-%(version)s', '.tar.xz'),
    'gnu': ('https://ftp.gnu.org/gnu/', '%(name)s/%(name)s-%(version)s', '.tar.xz'),
    'savannah': ('https://download.savannah.gnu.org/releases/', '%(name)s/%(name)s-%(version)s', '.tar.xz'),
    'sf': ('https://download.sourceforge.net/', '%(name)s/%(name)s-%(version)s', '.tar.xz'),
    'xiph': ('https://downloads.xiph.org/releases/', '%(name)s/%(name)s-%(version)s', '.tar.xz'),
}

def get_logfile(instance):
    # only Recipe has the logfile attr.  Bootstraping doesn't
    return getattr(instance, 'logfile') if hasattr(instance, 'logfile') else None

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

    patches = None
    strip = 1
    offline = False

    def __init__(self):
        if self.patches is None:
            self.patches = []

        if not self.version:
            raise InvalidRecipeError(
                self, _("'version' attribute is missing in the recipe"))

    async def fetch(self, **kwargs):
        self.fetch_impl(**kwargs)

    def fetch_impl(self):
        '''
        Fetch the sources
        '''
        raise NotImplemented("'fetch' must be implemented by subclasses")

    async def extract(self):
        '''
        Extracts the sources
        '''
        raise NotImplemented("'extract' must be implemented by subclasses")

    def expand_url_template(self, s):
        '''
        Expand a standard URL template (GNOME, SourceForge, GNU, etc)
        and get a URL that just needs the name and version substituted.
        '''
        schemes = tuple(s + '://' for s in URL_TEMPLATES.keys())
        if s.startswith(schemes):
            scheme, url = s.split('://', 1)
            parts = URL_TEMPLATES[scheme]
            if url == '':
                return ''.join(parts)
            if url.startswith('.'):
                return parts[0] + parts[1] + url
            return parts[0] + url
        return s

    def replace_name_and_version(self, string):
        '''
        Replaces name and version in strings
        '''
        name = self.name
        if name.startswith('gst') and name.endswith('-1.0'):
            # gst-libav-1.0, etc is useless for substitution, convert to 'gst-libav'
            name = name[:-4]
        maj_ver = '.'.join(self.version.split('.')[0:2])
        return string % {'name': name, 'version': self.version, 'maj_ver': maj_ver}

    def _get_files_dependencies(self):
        '''
        Subclasses should override this funtion to provide any file that
        this recipe depends on, including the recipe's file

        @return: the recipe file and other files this recipes depends on
                 like patches
        @rtype: list
        '''
        files = list(map(self.relative_path, self.patches))
        if hasattr(self, '__file__'):
            files.append(self.__file__)
        return files


class CustomSource (Source):

    async def fetch(self):
        pass

    async def extract(self):
        pass


class BaseTarball(object):
    '''
    Source handler for tarballs

    @cvar url: download URL for the tarball
    @type url: str

    @cvar tarball_checksum: sha256 checksum for the tarball
    @type tarball_checksum: str

    @cvar tarball_name: the name to save the url as
    @type tarball_name: str

    @cvar tarball_dirname: the directory that the tarball contents will extract to
    @type tarball_dirname: str

    @cvar tarball_is_bomb: the tarball is a tarbomb and will extract contents into the current directory
    @type tarball_is_bomb: bool
    '''

    url = None
    tarball_name = None
    tarball_dirname = None
    tarball_is_bomb = False
    tarball_checksum = None

    def __init__(self):
        if not self.tarball_name:
            self.tarball_name = os.path.basename(self.url)
        # URL-encode spaces and other special characters in the URL's path
        split = list(urllib.parse.urlsplit(self.url))
        split[2] = urllib.parse.quote(split[2])
        self.url = urllib.parse.urlunsplit(split)
        o = urllib.parse.urlparse(self.url)
        if o.scheme in ('http', 'ftp'):
            raise FatalError('Download URL {!r} must use HTTPS'.format(self.url))

    def _get_download_path(self):
        '''
        Fetch download path dynamically because self.tarball_name may be
        reset in prepare()
        '''
        return os.path.join(self.download_dir, self.tarball_name)

    async def fetch(self, redownload=False):
        fname = self._get_download_path()
        if self.offline:
            if not os.path.isfile(fname):
                msg = 'Offline mode: tarball {!r} not found in local sources ({})'
                raise FatalError(msg.format(self.tarball_name, self.download_dir))
            self.verify(fname)
            m.action(_('Found %s at %s') % (self.url, fname), logfile=get_logfile(self))
            return
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
        # Enable certificate checking only on Linux for now
        # FIXME: Add more platforms here after testing
        cc = False
        if self.config.platform == Platform.LINUX:
            if self.config.distro != Distro.REDHAT or \
               self.config.distro_version > DistroVersion.REDHAT_7:
                cc = True
        await shell.download(self.url, fname, check_cert=cc,
            overwrite=redownload, logfile=get_logfile(self),
            mirrors= self.config.extra_mirrors + DEFAULT_MIRRORS)
        self.verify(fname)

    @staticmethod
    def _checksum(fname):
        h = sha256()
        with open(fname, 'rb') as f:
            # Read in chunks of 512k till f.read() returns b'' instead of reading
            # the whole file at once which will fail on systems with low memory
            for block in iter(lambda: f.read(512 * 1024), b''):
                h.update(block)
        return h.hexdigest()

    def verify(self, fname, fatal=True):
        checksum = self._checksum(fname)
        if self.tarball_checksum is None:
            raise FatalError('tarball_checksum is missing in {}.recipe for tarball {}\n'
                             'The SHA256 of the current file is {}\nPlease verify and '
                             'add it to the recipe'.format(self.name, self.url, checksum))
        if checksum != self.tarball_checksum:
            movedto = fname + '.failed-checksum'
            os.replace(fname, movedto)
            m.action(_('Checksum failed, tarball %s moved to %s') % (fname, movedto), logfile=get_logfile(self))
            if not fatal:
                return False
            raise FatalError('Checksum for {} is {!r} instead of {!r}'
                             .format(fname, checksum, self.tarball_checksum))
        return True

    async def extract_tarball(self, unpack_dir):
        fname = self._get_download_path()
        logfile = get_logfile(self)
        try:
            await shell.unpack(fname, unpack_dir, logfile=logfile)
        except (CommandError, tarfile.ReadError, zipfile.BadZipFile):
            movedto = fname + '.failed-extract'
            os.replace(fname, movedto)
            m.action('Corrupted or partial tarball {} moved to {}, redownloading...'.format(fname, movedto),
                     logfile=logfile)
            if self.offline:
                # Can't fetch in offline mode
                raise
            await self.fetch(redownload=True)
            await shell.unpack(fname, unpack_dir, logfile=logfile)


class Tarball(BaseTarball, Source):

    def __init__(self):
        Source.__init__(self)
        if not self.url:
            raise InvalidRecipeError(
                self, _("'url' attribute is missing in the recipe"))
        self.url = self.expand_url_template(self.url)
        self.url = self.replace_name_and_version(self.url)
        if self.tarball_name is not None:
            self.tarball_name = \
                self.replace_name_and_version(self.tarball_name)
        if self.tarball_dirname is not None:
            self.tarball_dirname = \
                self.replace_name_and_version(self.tarball_dirname)
        self.download_dir = self.repo_dir
        BaseTarball.__init__(self)

    async def fetch(self, redownload=False):
        fname = self._get_download_path()
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

        cached_file = os.path.join(self.config.cached_sources,
                                   self.package_name, self.tarball_name)
        if not redownload and os.path.isfile(cached_file) and self.verify(cached_file, fatal=False):
            m.action(_('Copying cached tarball from %s to %s instead of %s') %
                     (cached_file, fname, self.url), logfile=get_logfile(self))
            shutil.copy(cached_file, fname)
            return
        await super().fetch(redownload=redownload)

    async def extract(self):
        m.action(_('Extracting tarball to %s') % self.config_src_dir, logfile=get_logfile(self))
        if os.path.exists(self.config_src_dir):
            shutil.rmtree(self.config_src_dir)

        unpack_dir = self.config.sources
        if self.tarball_is_bomb:
            unpack_dir = self.config_src_dir
        await self.extract_tarball(unpack_dir)

        if self.tarball_dirname is not None:
            extracted = os.path.join(unpack_dir, self.tarball_dirname)
            # Since we just extracted this, a Windows anti-virus might still
            # have a lock on files inside it.
            shell.windows_proof_rename(extracted, self.config_src_dir)
        git.init_directory(self.config_src_dir, logfile=get_logfile(self))
        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)
            if self.strip == 1:
                git.apply_patch(patch, self.config_src_dir, logfile=get_logfile(self))
            else:
                shell.apply_patch(patch, self.config_src_dir, self.strip, logfile=get_logfile(self))


class GitCache (Source):
    '''
    Base class for source handlers using a Git repository
    '''

    remotes = None
    commit = None
    use_submodules = True

    _fetch_locks = collections.defaultdict(asyncio.Lock)
    _fetch_done = set()

    def __init__(self):
        Source.__init__(self)
        self.remotes = {} if self.remotes is None else self.remotes.copy()
        if 'origin' in self.remotes:
            url = self.replace_name_and_version(self.remotes['origin'])
            o = urllib.parse.urlparse(url)
            if o.scheme in ('http', 'git'):
                raise FatalError('git remote origin URL {!r} must use HTTPS not {!r}'
                                 ''.format(url, o.scheme))
            if o.scheme in ('file', 'ssh'):
                m.warning('git remote origin URL {!r} uses {!r}, please only use this '
                          'for testing'.format(url, o.scheme))
            self.remotes['origin'] = url
        else:
            # XXX: When is this used?
            self.remotes['origin'] = '%s/%s.git' % \
                                     (self.config.git_root, self.name)
        self.repo_dir = os.path.join(self.config.local_sources, self.name)
        self._previous_env = None
        # For forced commits in the config
        self.commit = self.config.recipe_commit(self.name) or self.commit
        self.remotes.update(self.config.recipes_remotes.get(self.name, {}))

    async def fetch(self, checkout=True):
        # Could have multiple recipes using the same repo.
        lock = self._fetch_locks[self.repo_dir]
        async with lock:
            if self.repo_dir in self._fetch_done:
                return
            await self.fetch_impl(checkout)
            self._fetch_done.add(self.repo_dir)

    async def fetch_impl(self, checkout):
        # First try to get the sources from the cached dir if there is one
        cached_dir = os.path.join(self.config.cached_sources,  self.name)

        if not os.path.exists(self.repo_dir):
            if not cached_dir and self.offline:
                msg = 'Offline mode: git repo for {!r} not found in cached sources ({}) or local sources ({})'
                raise FatalError(msg.format(self.name, self.config.cached_sources, self.repo_dir))
            git.init(self.repo_dir, logfile=get_logfile(self))

        if os.path.isdir(os.path.join(cached_dir, ".git")):
            for remote, url in self.remotes.items():
                git.add_remote(self.repo_dir, remote, "file://" + cached_dir, logfile=get_logfile(self))
            await git.fetch(self.repo_dir, fail=False, logfile=get_logfile(self))
        else:
            cached_dir = None
            # add remotes from both upstream and config so user can easily
            # cherry-pick patches between branches
            for remote, url in self.remotes.items():
                git.add_remote(self.repo_dir, remote, url, logfile=get_logfile(self))
            # fetch remote branches
            if not self.offline:
                await git.fetch(self.repo_dir, fail=False, logfile=get_logfile(self))
        if checkout:
            await git.checkout(self.repo_dir, self.commit, logfile=get_logfile(self))
            if self.use_submodules:
                await git.submodules_update(self.repo_dir, cached_dir, fail=False, offline=self.offline, logfile=get_logfile(self))


    def built_version(self):
        return '%s+git~%s' % (self.version, git.get_hash(self.repo_dir, self.commit, logfile=get_logfile(self)))


class Git (GitCache):
    '''
    Source handler for git repositories
    '''

    _extract_locks = collections.defaultdict(asyncio.Lock)
    _extract_done = set()

    def __init__(self):
        GitCache.__init__(self)
        if self.commit is None:
            # Used by recipes in recipes/toolchain/
            self.commit = 'origin/sdk-%s' % self.version

    async def extract(self):
        # Could have multiple recipes using the same repo.
        lock = self._extract_locks[self.config_src_dir]
        async with lock:
            if self.config_src_dir in self._extract_done:
                return
            await self.extract_impl()
            self._extract_done.add(self.config_src_dir)

    async def extract_impl(self):
        if os.path.exists(self.config_src_dir):
            try:
                commit_hash = git.get_hash(self.repo_dir, self.commit, logfile=get_logfile(self))
                checkout_hash = git.get_hash(self.config_src_dir, 'HEAD', logfile=get_logfile(self))
                if commit_hash == checkout_hash and not self.patches:
                    return False
            except Exception:
                pass
            shutil.rmtree(self.config_src_dir)
        if not os.path.exists(self.config_src_dir):
            os.makedirs(self.config_src_dir)

        # checkout the current version
        await git.local_checkout(self.config_src_dir, self.repo_dir, self.commit, logfile=get_logfile(self), use_submodules=self.use_submodules)

        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)

            if self.strip == 1:
                git.apply_patch(patch, self.config_src_dir, logfile=get_logfile(self))
            else:
                shell.apply_patch(patch, self.config_src_dir, self.strip, logfile=get_logfile(self))

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

    def __init__(self):
        Git.__init__(self)
        self._files = {}

    async def extract(self):
        if not await Git.extract(self):
            return False
        for match in self.matches:
            self._files[match] = []
        self._find_files(self.config_src_dir)
        self._files['.in'] = [x for x in self._files['.in'] if
                os.path.join(self.config_src_dir, 'm4') not in x]
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

    async def fetch(self):
        cached_dir = os.path.join(self.config.cached_sources, self.package_name)
        if os.path.isdir(os.path.join(cached_dir, ".svn")):
            if os.path.exists(self.repo_dir):
                shutil.rmtree(self.repo_dir)
            m.action(_('Copying cached repo from %s to %s instead of %s') %
                     (cached_dir, self.repo_dir, self.url), logfile=get_logfile(self))
            shell.copy_dir(cached_dir, self.repo_dir)
            return

        checkout = True
        if os.path.exists(self.repo_dir):
            if os.path.isdir(os.path.join(self.repo_dir, '.svn')):
                if self.offline:
                    return
                checkout = False
            else:
                shutil.rmtree(self.repo_dir)

        if checkout:
            os.makedirs(self.repo_dir, exist_ok=True)
            await svn.checkout(self.url, self.repo_dir)
        await svn.update(self.repo_dir, self.revision)

    async def extract(self):
        if os.path.exists(self.config_src_dir):
            shutil.rmtree(self.config_src_dir)

        shutil.copytree(self.repo_dir, self.config_src_dir)

        for patch in self.patches:
            if not os.path.isabs(patch):
                patch = self.relative_path(patch)
            shell.apply_patch(patch, self.config_src_dir, self.strip, logfile=get_logfile(self))

    def built_version(self):
        return '%s+svn~%s' % (self.version, svn.revision(self.repo_dir))


class SourceType (object):

    CUSTOM = CustomSource
    TARBALL = Tarball
    GIT = Git
    GIT_TARBALL = GitExtractedTarball
    SVN = Svn
