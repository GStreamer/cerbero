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
import pickle
import shutil
from hashlib import sha256

from cerbero.commands import Command, register_command
from cerbero.enums import Platform, Distro
from cerbero.errors import FatalError
from cerbero.utils import N_, ArgparseArgument, git, shell, run_until_complete
from cerbero.utils import messages as m


class BaseCache(Command):
    base_url = 'https://artifacts.gstreamer-foundation.net/cerbero-deps'
    ssh_address = 'cerbero-deps-uploader@artifacts.gstreamer-foundation.net'
    deps_filename = 'cerbero-deps.tar.xz'
    log_filename = 'cerbero-deps.log'
    log_size = 10
    dry_run = False

    def __init__(self, args=[]):
        args += [
            ArgparseArgument(
                '--commit', action='store', type=str, default='HEAD', help='the commit to pick artifact from'
            ),
            ArgparseArgument('--branch', action='store', type=str, default='main', help='Git branch to search from'),
            ArgparseArgument('--dry-run', action='store_true', help='Run without doing any writes'),
            ArgparseArgument(
                '--project',
                action='store',
                type=str,
                default='gstreamer',
                help='Gitlab project (gstreamer or gst-plugins-rs)',
            ),
        ]
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
        ci_home_dir = os.environ.get('CERBERO_HOME', 'cerbero-build')
        return f'{ci_builds_dir}/{namespace}/cerbero/{ci_home_dir}'

    def get_gnu_sed(self, config):
        if config.platform == Platform.DARWIN:
            return os.path.join(config.build_tools_prefix, 'bin', 'sed')
        return 'sed'

    # FIXME: move this to utils
    def checksum(self, fname):
        h = sha256()
        if not self.dry_run:
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

    def get_artifact_dir(self, config, args):
        project = args.project
        branch = args.branch
        distro, arch = self.get_distro_and_arch(config)
        return '/'.join([project, branch, distro, arch])

    def make_url(self, config, args, filename):
        artifact_dir = self.get_artifact_dir(config, args)
        return '%s/%s/%s' % (self.base_url, artifact_dir, filename)

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
        self.dry_run = args.dry_run
        if not config.uninstalled:
            raise FatalError('fetch-cache is only available with cerbero-uninstalled')


class FetchCache(BaseCache):
    doc = N_('Fetch a cached build from external storage based on cerbero git ' 'revision.')
    name = 'fetch-cache'

    def __init__(self, args=[]):
        args.append(
            ArgparseArgument(
                '--namespace', action='store', type=str, default='gstreamer', help='GitLab namespace to relocate from'
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

    @staticmethod
    def _is_mach_o_file(filename):
        fileext = os.path.splitext(filename)[1]
        if '.dylib' in fileext:
            return True
        filedesc = shell.check_output(['file', '-bh', filename])
        if fileext == '.a' and 'ar archive' in filedesc:
            return False
        return filedesc.startswith('Mach-O')

    @staticmethod
    def _list_shared_libraries(object_file):
        res = shell.check_output(['otool', '-L', object_file]).splitlines()
        # We don't use the first line
        libs = res[1:]
        # Remove the first character tabulation
        libs = [x[1:] for x in libs]
        # Remove the version info
        libs = [x.split(' ', 1)[0] for x in libs]
        return libs

    @classmethod
    def _change_lib_paths(self, object_file, old_path, new_path):
        for lib in self._list_shared_libraries(object_file):
            if old_path not in lib:
                continue
            new = lib.replace(old_path, new_path)
            cmd = ['install_name_tool', '-change', lib, new, object_file]
            shell.new_call(cmd, fail=True, verbose=True)

    def relocate_macos_build_tools(self, config, old_path, new_path):
        """
        build-tools on macOS have absolute paths as install names for all
        Mach-O files, so we need to relocate them to the new prefix.
        The Universal build isn't affected because Cerbero relocates the
        binaries there.
        """
        paths = [
            os.path.join(config.build_tools_prefix, 'bin'),
            os.path.join(config.build_tools_prefix, 'lib'),
        ]
        for dir_path in paths:
            for dirpath, _dirnames, filenames in os.walk(dir_path):
                for f in filenames:
                    object_file = os.path.join(dirpath, f)
                    if not self._is_mach_o_file(object_file):
                        continue
                    self._change_lib_paths(object_file, old_path, new_path)

    def mark_windows_build_tools_dirty(self, config):
        """
        On Windows, Python virtualenv writes out an executable for all
        pip-installed Python programs, which need to be rebuilt for the current
        prefix. Currently, this is just Meson in build-tools.
        """
        cache_file = os.path.join(config.home_dir, config.build_tools_cache)
        with open(cache_file, 'rb+') as f:
            p = pickle.load(f)
            # Reset the recipe status
            del p['meson']
            f.seek(0)
            f.truncate(0)
            pickle.dump(p, f)

    def relocate_prefix(self, config, namespace):
        """
        We need to relocate pc files that weren't generated by meson and
        python programs installed with pip because the shebang set by the
        virtualenv python uses an absolute path.
        """
        origin = self.get_cache_home_dir(config, namespace)
        dest = config.home_dir
        if origin == dest:
            return
        m.action(f'Relocating text files from {origin} to {dest}')
        sed = self.get_gnu_sed(config)
        # This is hacky, but fast enough
        shell.call(f'grep -lrIe {origin} {dest} | xargs {sed} "s#{origin}#{dest}#g" -i', verbose=True)
        # Need to relocate RPATHs and names in binaries
        if config.platform == Platform.DARWIN:
            self.relocate_macos_build_tools(config, origin, dest)
        elif config.platform == Platform.WINDOWS:
            self.mark_windows_build_tools_dirty(config)

    async def fetch_dep(self, config, dep, namespace):
        is_ci = 'CI' in os.environ
        try:
            dep_path = os.path.join(config.home_dir, os.path.basename(dep['url']))
            m.action(f'Downloading deps cache {dep["url"]}')
            if self.dry_run:
                return
            await shell.download(dep['url'], dep_path, overwrite=is_ci)
            if dep['checksum'] != self.checksum(dep_path):
                m.warning('Corrupted dependency file, ignoring.')
            m.action(f'Unpacking deps cache {dep_path}')
            await shell.unpack(dep_path, config.home_dir)
            if is_ci:
                m.action('Unpack complete, deleting artifact')
                os.remove(dep_path)

            self.relocate_prefix(config, namespace)
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

    def create_tarball(self, workdir, out_file, *in_files):
        exclude = ['var/tmp']
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
        if not self.dry_run:
            shell.new_call(cmd)

    def gen_dep(self, config, args, deps, sha):
        deps_filepath = self.get_deps_filepath(config)
        if not self.dry_run and os.path.exists(deps_filepath):
            os.remove(deps_filepath)

        log_filepath = self.get_log_filepath(config)
        if not self.dry_run and os.path.exists(log_filepath):
            os.remove(log_filepath)

        workdir = config.home_dir
        platform_arch = '_'.join(config._get_toolchain_target_platform_arch())
        distdir = f'dist/{platform_arch}'
        try:
            self.create_tarball(
                workdir, deps_filepath, 'build-tools', config.build_tools_cache, distdir, config.cache_file
            )
            url = self.make_url(config, args, '%s-%s' % (sha, self.deps_filename))
            deps.insert(0, {'commit': sha, 'checksum': self.checksum(deps_filepath), 'url': url})
            deps = deps[0 : self.log_size]
            log_json = json.dumps(deps, indent=1)
            if self.dry_run:
                print('Generated JSON:')
                print(log_json)
            else:
                with open(log_filepath, 'w') as outfile:
                    outfile.write(log_json)
        except FatalError:
            if os.path.exists(deps_filepath):
                os.remove(deps_filepath)
            if os.path.exists(log_filepath):
                os.remove(log_filepath)
            raise
        if self.dry_run:
            fsize = -1
        else:
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
        if not self.dry_run:
            if not os.path.exists(deps_filepath) or not os.path.exists(log_filepath):
                raise FatalError('gen-cache must be run before running upload-cache.')

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
            base_dir = self.get_artifact_dir(config, args)
            m.message(f'Making directory structure: {base_dir}')
            if not self.dry_run:
                shell.new_call(ssh_cmd + ['mkdir -p %s' % base_dir], verbose=True)

            # Upload the deps files first
            remote_deps_filepath = os.path.join(base_dir, '%s-%s' % (sha, self.deps_filename))
            upload_cmd = scp_cmd + [deps_filepath, f'{self.ssh_address}:{remote_deps_filepath}']
            m.message(f'Uploading deps file: {upload_cmd!r}')
            if not self.dry_run:
                shell.new_call(upload_cmd, verbose=True)

            # Upload the new log
            remote_tmp_log_filepath = os.path.join(base_dir, '%s-%s' % (sha, self.log_filename))
            upload_cmd = scp_cmd + [log_filepath, f'{self.ssh_address}:{remote_tmp_log_filepath}']
            m.message(f'Uploading deps log: {upload_cmd!r}')
            if not self.dry_run:
                shell.new_call(upload_cmd, verbose=True)

            # Override the new log in a way that we reduce the risk of corrupted
            # fetch.
            remote_log_filepath = os.path.join(base_dir, self.log_filename)
            rename_cmd = ssh_cmd + ['mv', '-f', remote_tmp_log_filepath, remote_log_filepath]
            m.message(f'Renaming deps log: {rename_cmd!r}')
            if not self.dry_run:
                shell.new_call(rename_cmd, verbose=True)
            m.message('New deps cache uploaded and deps log updated')

            # Now remove the obsoleted dep file if needed
            for dep in deps[self.log_size - 1 :]:
                old_remote_deps_filepath = os.path.relpath(dep['url'], self.base_url)
                rm_cmd = ['rm', '-f', old_remote_deps_filepath]
                m.message(f'Removing obsolete dep file: {rm_cmd!r}')
                if not self.dry_run:
                    shell.new_call(ssh_cmd + rm_cmd, verbose=True)
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
