# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2020 Nicolas Dufresne <nicolas.dufresne@collabora.com>
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
import sys
import json
import tempfile
import shutil
from hashlib import sha256

from cerbero.commands import Command, register_command
from cerbero.enums import Platform, Distro
from cerbero.errors import FatalError
from cerbero.utils import _, N_, ArgparseArgument, git, shell, run_until_complete
from cerbero.utils import messages as m


class BaseCache(Command):
    base_url = 'https://artifacts.gstreamer-foundation.net/cerbero-deps/%s/%s/%s'
    ssh_address = 'cerbero-deps-uploader@artifacts.gstreamer-foundation.net'
    deps_filename = 'cerbero-deps.tar.xz'
    log_filename = 'cerbero-deps.log'
    log_size = 10

    def __init__(self, args=[]):
        args.append(
            ArgparseArgument(
                '--commit', action='store', type=str, default='HEAD', help=_('the commit to pick artifact from')
            )
        )
        args.append(
            ArgparseArgument('--branch', action='store', type=str, default='main', help=_('Git branch to search from'))
        )
        Command.__init__(self, args)

    def get_ci_builds_dir(self, config):
        if 'CI_BUILDS_DIR' in os.environ:
            return os.environ['CI_BUILDS_DIR'].replace('\\', '/')
        # For the convenience of people downloading the cache by hand
        if config.platform == Platform.DARWIN:
            return '/private/tmp/builds'
        elif config.platform == Platform.WINDOWS:
            return 'C:/Users/Administrator/runner/builds'
        return '/builds'

    def get_cache_home_dir(self, config, namespace):
        ci_builds_dir = self.get_ci_builds_dir(config)
        return f'{ci_builds_dir}/{namespace}/cerbero/cerbero-build'

    def get_gnu_sed(self, config):
        if config.platform == Platform.DARWIN:
            return os.path.join(config.build_tools_prefix, 'bin', 'sed')
        return 'sed'

    # FIXME: move this to utils
    def checksum(self, fname):
        h = sha256()
        with open(fname, 'rb') as f:
            # Read in chunks of 512k till f.read() returns b'' instead of reading
            # the whole file at once which will fail on systems with low memory
            for block in iter(lambda: f.read(512 * 1024), b''):
                h.update(block)
        return h.hexdigest()

    def get_git_sha(self, commit):
        git_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        return git.get_hash(git_dir, commit)

    def get_git_sha_is_ancestor(self, commit):
        git_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        return git.get_hash_is_ancestor(git_dir, commit)

    def json_get(self, url):
        m.message('GET %s' % url)

        tmpdir = tempfile.mkdtemp()
        tmpfile = os.path.join(tmpdir, 'deps.json')
        run_until_complete(shell.download(url, tmpfile))
        m.message(f'{tmpfile} downloaded')

        with open(tmpfile, 'r') as f:
            resp = f.read()
        shutil.rmtree(tmpdir)

        return json.loads(resp)

    def get_distro_and_arch(self, config):
        distro = config.target_distro
        target_arch = config.target_arch
        if distro == Distro.REDHAT:
            distro = 'fedora'
        elif distro == Distro.OS_X:
            distro = 'macos'
        elif distro == Distro.WINDOWS:
            # When targeting Windows, we need to differentiate between mingw,
            # msvc, and uwp (debug/release) jobs. When cross-compiling this
            # will always be 'cross-windows-mingw' right now, but that might
            # change at some point.
            toolchain, _ = config._get_toolchain_target_platform_arch()
            distro = 'windows-' + toolchain
        if config.cross_compiling():
            distro = 'cross-' + distro
        target_distro = f'{distro}_{config.arch}'
        return target_distro, target_arch

    def make_url(self, config, args, filename):
        branch = args.branch
        distro, arch = self.get_distro_and_arch(config)
        base_url = self.base_url % (branch, distro, arch)
        return '%s/%s' % (base_url, filename)

    def get_deps(self, config, args):
        url = self.make_url(config, args, self.log_filename)
        deps = []

        try:
            deps = self.json_get(url)
        except FatalError as e:
            m.warning('Could not get cache list: %s' % e.msg)
        return deps

    def get_deps_filepath(self, config):
        return os.path.join(config.home_dir, self.deps_filename)

    def get_log_filepath(self, config):
        return os.path.join(config.home_dir, self.log_filename)

    def run(self, config, args):
        if not config.uninstalled:
            raise FatalError(_('fetch-cache is only available with ' 'cerbero-uninstalled'))


class FetchCache(BaseCache):
    doc = N_('Fetch a cached build from external storage based on cerbero git ' 'revision.')
    name = 'fetch-cache'

    def __init__(self, args=[]):
        args.append(
            ArgparseArgument(
                '--namespace', action='store', type=str, default='gstreamer', help=_('GitLab namespace to search from')
            )
        )
        BaseCache.__init__(self, args)

    def find_dep(self, deps, sha, allow_old=False):
        for dep in deps:
            if dep['commit'] == sha:
                m.message(f"Matching cache file is {dep['url']}")
                return dep
        if allow_old:
            m.message(f'Did not find cache for commit {sha}, looking for an older one...')
            for dep in deps:
                if self.get_git_sha_is_ancestor(dep['commit']):
                    m.message(f"Latest available cache file is {dep['url']}")
                    return dep
            m.warning(f'Did not find any cache for commit {sha}')
        else:
            m.warning(f'Did not find cache for commit {sha}')
        return None

    async def fetch_dep(self, config, dep, namespace):
        is_ci = 'CI' in os.environ
        try:
            dep_path = os.path.join(config.home_dir, os.path.basename(dep['url']))
            m.action(f'Downloading deps cache {dep["url"]}')
            await shell.download(dep['url'], dep_path, overwrite=is_ci)
            if dep['checksum'] != self.checksum(dep_path):
                m.warning('Corrupted dependency file, ignoring.')
            m.action(f'Unpacking deps cache {dep_path}')
            await shell.unpack(dep_path, config.home_dir)
            if is_ci:
                m.action('Unpack complete, deleting artifact')
                os.remove(dep_path)

            # We need to relocate pc files that weren't generated by meson and
            # python programs installed with pip because the shebang set by the
            # virtualenv python uses an absolute path.
            origin = self.get_cache_home_dir(config, namespace)
            dest = config.home_dir
            if origin != dest:
                m.action(f'Relocating text files from {origin} to {dest}')
                sed = self.get_gnu_sed(config)
                # This is hacky, but fast enough
                shell.call(f'grep -lrIe {origin} {dest} | xargs {sed} "s#{origin}#{dest}#g" -i', verbose=True)
        except FatalError as e:
            m.warning('Could not retrieve dependencies for commit %s: %s' % (dep['commit'], e.msg))

    def run(self, config, args):
        BaseCache.run(self, config, args)

        sha = self.get_git_sha(args.commit)
        deps = self.get_deps(config, args)
        dep = self.find_dep(deps, sha, allow_old=True)
        if dep:
            run_until_complete(self.fetch_dep(config, dep, args.namespace))
        m.message('All done!')


class GenCache(BaseCache):
    doc = N_('Generate build cache from current state.')
    name = 'gen-cache'

    def __init__(self, args=[]):
        BaseCache.__init__(self, args)

    def create_tarball_tarfile(self, workdir, out_file, *in_files, exclude=None):
        import tarfile

        m.action('Generating cache file with tarfile + xz')

        def exclude_filter(tarinfo):
            for each in exclude:
                if each in tarinfo.name:
                    return None
            print(tarinfo.name)
            return tarinfo

        prev_cwd = os.getcwd()
        os.chdir(workdir)
        out_tar, _ = os.path.splitext(out_file)
        try:
            with tarfile.open(out_tar, 'w') as tf:
                for in_file in in_files:
                    tf.add(in_file, filter=exclude_filter)
        finally:
            os.chdir(prev_cwd)
        m.action('Compressing cache file with xz')
        shell.new_call(['xz', '-vv', '--threads=0', out_tar])

    def create_tarball_tar(self, workdir, out_file, *in_files, exclude=None):
        cmd = [
            shell.get_tar_cmd(),
            '-C',
            workdir,
            '--verbose',
            '--use-compress-program=xz --threads=0',
        ]
        for each in exclude:
            cmd += ['--exclude=' + each]
        cmd += ['-cf', out_file]
        cmd += in_files
        m.action(f'Generating cache file with {cmd!r}')
        shell.new_call(cmd)

    def create_tarball(self, config, workdir, *args):
        exclude = ['var/tmp']
        # MSYS tar seems to hang sometimes while compressing on Windows CI, so
        # use the tarfile module
        if config.platform == Platform.WINDOWS:
            self.create_tarball_tarfile(workdir, *args, exclude=exclude)
        else:
            self.create_tarball_tar(workdir, *args, exclude=exclude)

    def gen_dep(self, config, args, deps, sha):
        deps_filepath = self.get_deps_filepath(config)
        if os.path.exists(deps_filepath):
            os.remove(deps_filepath)

        log_filepath = self.get_log_filepath(config)
        if os.path.exists(log_filepath):
            os.remove(log_filepath)

        workdir = config.home_dir
        platform_arch = '_'.join(config._get_toolchain_target_platform_arch())
        distdir = f'dist/{platform_arch}'
        try:
            self.create_tarball(
                config, workdir, deps_filepath, 'build-tools', config.build_tools_cache, distdir, config.cache_file
            )
            url = self.make_url(config, args, '%s-%s' % (sha, self.deps_filename))
            deps.insert(0, {'commit': sha, 'checksum': self.checksum(deps_filepath), 'url': url})
            deps = deps[0 : self.log_size]
            with open(log_filepath, 'w') as outfile:
                json.dump(deps, outfile, indent=1)
        except FatalError:
            if os.path.exists(deps_filepath):
                os.remove(deps_filepath)
            if os.path.exists(log_filepath):
                os.remove(log_filepath)
            raise
        fsize = os.path.getsize(deps_filepath) / (1024 * 1024)
        m.message(f'build-dep cache {deps_filepath} of size {fsize:.2f}MB generated')

    def run(self, config, args):
        BaseCache.run(self, config, args)

        sha = self.get_git_sha(args.commit)
        deps = self.get_deps(config, args)
        self.gen_dep(config, args, deps, sha)


class UploadCache(BaseCache):
    doc = N_('Build build cache to external storage.')
    name = 'upload-cache'

    def __init__(self, args=[]):
        BaseCache.__init__(self, args)

    def upload_dep(self, config, args, deps):
        sha = self.get_git_sha(args.commit)
        for dep in deps:
            if dep['commit'] == sha:
                m.message('Cache already uploaded for this commit.')
                return

        tmpdir = tempfile.mkdtemp()
        private_key = os.getenv('CERBERO_PRIVATE_SSH_KEY')
        private_key_path = os.path.join(tmpdir, 'id_rsa')

        deps_filepath = self.get_deps_filepath(config)
        log_filepath = self.get_log_filepath(config)
        if not os.path.exists(deps_filepath) or not os.path.exists(log_filepath):
            raise FatalError(_('gen-cache must be run before running upload-cache.'))

        try:
            # Setup tempory private key from env
            ssh_opt = ['-o', 'StrictHostKeyChecking=no']
            if private_key:
                with os.fdopen(os.open(private_key_path, os.O_WRONLY | os.O_CREAT, 0o600), 'w') as f:
                    f.write(private_key)
                    f.write('\n')
                    f.close()
                ssh_opt += ['-i', private_key_path]
            ssh_cmd = ['ssh'] + ssh_opt + [self.ssh_address]
            scp_cmd = ['scp'] + ssh_opt

            # Ensure directory sturcture is in place
            branch = args.branch
            distro, arch = self.get_distro_and_arch(config)
            base_dir = os.path.join(branch, distro, arch)
            shell.new_call(ssh_cmd + ['mkdir -p %s' % base_dir], verbose=True)

            # Upload the deps files first
            remote_deps_filepath = os.path.join(base_dir, '%s-%s' % (sha, self.deps_filename))
            shell.new_call(scp_cmd + [deps_filepath, '%s:%s' % (self.ssh_address, remote_deps_filepath)], verbose=True)

            # Upload the new log
            remote_tmp_log_filepath = os.path.join(base_dir, '%s-%s' % (sha, self.log_filename))
            shell.new_call(
                scp_cmd + [log_filepath, '%s:%s' % (self.ssh_address, remote_tmp_log_filepath)], verbose=True
            )

            # Override the new log in a way that we reduce the risk of corrupted
            # fetch.
            remote_log_filepath = os.path.join(base_dir, self.log_filename)
            shell.new_call(ssh_cmd + ['mv', '-f', remote_tmp_log_filepath, remote_log_filepath], verbose=True)
            m.message('New deps cache uploaded and deps log updated')

            # Now remove the obsoleted dep file if needed
            for dep in deps[self.log_size - 1 :]:
                old_remote_deps_filepath = os.path.join(base_dir, os.path.basename(dep['url']))
                shell.new_call(ssh_cmd + ['rm', '-f', old_remote_deps_filepath], verbose=True)
        finally:
            shutil.rmtree(tmpdir)

    def run(self, config, args):
        BaseCache.run(self, config, args)
        deps = self.get_deps(config, args)
        self.upload_dep(config, args, deps)
        m.message('All done!')


register_command(FetchCache)
register_command(GenCache)
register_command(UploadCache)
