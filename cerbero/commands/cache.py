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

import os, sys
import json
import tempfile
import shutil
from hashlib import sha256

from cerbero.commands import Command, register_command
from cerbero.errors import FatalError
from cerbero.utils import _, N_, ArgparseArgument, git, shell, run_until_complete
from cerbero.utils import messages as m
from cerbero.config import Distro

class BaseCache(Command):
    base_url = 'https://artifacts.gstreamer-foundation.net/cerbero-deps/%s/%s/%s'
    ssh_address = 'cerbero-deps-uploader@artifacts.gstreamer-foundation.net'
    build_dir = '/builds/%s/cerbero/cerbero-build'
    deps_filename = 'cerbero-deps.tar.xz'
    log_filename = 'cerbero-deps.log'
    log_size = 10

    def __init__(self, args=[]):
        args.append(ArgparseArgument('--commit', action='store', type=str,
                    default='HEAD', help=_('the commit to pick artifact from')))
        args.append(ArgparseArgument('--branch', action='store', type=str,
                    default='master', help=_('Git branch to search from')))
        Command.__init__(self, args)

    # FIXME: move this to utils
    def checksum(self, fname):
        h = sha256()
        with open(fname, 'rb') as f:
            # Read in chunks of 512k till f.read() returns b'' instead of reading
            # the whole file at once which will fail on systems with low memory
            for block in iter(lambda: f.read(512 * 1024), b''):
                h.update(block)
        return h.hexdigest()

    def get_git_sha(self, args):
        git_dir = os.path.abspath(os.path.dirname(sys.argv[0]))
        return git.get_hash(git_dir, args.commit)

    def json_get(self, url):
        m.message("GET %s" % url)

        tmpdir = tempfile.mkdtemp()
        tmpfile = os.path.join(tmpdir, 'deps.json')
        run_until_complete(shell.download(url, destination=tmpfile,
              logfile=open(os.devnull, 'w')))

        with open(tmpfile, 'r') as f:
            resp = f.read()
        shutil.rmtree(tmpdir)

        return json.loads(resp)

    def get_distro_and_arch(self, config):
        distro = config.target_distro
        arch = config.target_arch
        if distro == Distro.REDHAT:
            distro = 'fedora'
        if distro == Distro.OS_X:
            distro = 'macos'
        if config.cross_compiling():
            distro = 'cross-' + distro
        return distro, arch

    def make_url(self, config, args, filename):
        branch = args.branch
        distro, arch = self.get_distro_and_arch(config)
        base_url = self.base_url % (branch, distro, arch)
        return "%s/%s" % (base_url, filename)

    def get_deps(self, config, args):
        url = self.make_url(config, args, self.log_filename)
        deps = []

        try:
            deps = self.json_get(url)
        except FatalError as e:
            m.warning("Could not get cache list: %s" % e.msg)

        return deps

    def get_deps_filename(self, config):
        return os.path.join(config.home_dir, self.deps_filename)

    def get_log_filename(self, config):
        return os.path.join(config.home_dir, self.log_filename)

    def run(self, config, args):
        if not config.uninstalled:
            raise FatalError(_("fetch-cache is only available with "
                        "cerbero-uninstalled"))

class FetchCache(BaseCache):
    doc = N_('Fetch a cached build from external storage based on cerbero git '
            'revision.')
    name = 'fetch-cache'

    def __init__(self, args=[]):
        args.append(ArgparseArgument('--namespace', action='store', type=str,
                    default='gstreamer', help=_('GitLab namespace to search from')))
        BaseCache.__init__(self, args)

    def find_dep(self, deps, sha):
        for dep in deps:
            if dep['commit'] == sha:
                return dep

        m.warning("Did not find cache for commit %s" % sha)
        return None

    async def fetch_dep(self, config, dep, namespace):
        try:
            dep_path = os.path.join(config.home_dir, os.path.basename(dep['url']))
            await shell.download(dep['url'], dep_path, check_cert=True, overwrite=True)
            if dep['checksum'] == self.checksum(dep_path):
                await shell.unpack(dep_path, config.home_dir)
            else:
                m.warning("Corrupted dependency file, ignoring.")
            os.remove(dep_path)

            origin = self.build_dir % namespace
            m.message("Relocating from %s to %s" % (origin, config.home_dir))
            # FIXME: Just a quick hack for now
            shell.call(("grep -lnrIU %(origin)s | xargs "
                        "sed \"s#%(origin)s#%(dest)s#g\" -i") % {
                            'origin': origin, 'dest': config.home_dir},
                        config.home_dir)
        except FatalError as e:
            m.warning("Could not retrieve dependencies for commit %s: %s" % (
                        dep['commit'], e.msg))

    def run(self, config, args):
        BaseCache.run(self, config, args)

        sha = self.get_git_sha(args)
        deps = self.get_deps(config, args)
        dep = self.find_dep(deps, sha)
        if dep:
            run_until_complete(self.fetch_dep(config, dep, args.namespace))

class GenCache(BaseCache):
    doc = N_('Generate build cache from current state.')
    name = 'gen-cache'

    def __init__(self, args=[]):
        BaseCache.__init__(self, args)

    def gen_dep(self, config, args, deps, sha):
        deps_filename = self.get_deps_filename(config)
        if os.path.exists(deps_filename):
          os.remove(deps_filename)

        log_filename = self.get_log_filename(config)
        if os.path.exists(log_filename):
          os.remove(log_filename)

        # Workaround special mangling for windows hidden in the config
        arch = os.path.basename(config.sources)
        try:
            shell.new_call(
                ['tar',
                    '-C', config.home_dir,
                    '--use-compress-program=xz --threads=0',
                    '--exclude=var/tmp',
                    '-cf', deps_filename,
                    'build-tools',
                    config.build_tools_cache,
                    os.path.join('dist', arch),
                    config.cache_file])
            url = self.make_url(config, args, '%s-%s' % (sha, self.deps_filename))
            deps.insert(0, {'commit': sha, 'checksum': self.checksum(deps_filename), 'url': url})
            deps = deps[0:self.log_size]
            with open(log_filename, 'w') as outfile:
                    json.dump(deps, outfile, indent=1)
        except FatalError:
            os.remove(deps_filename)
            os.remove(log_filename)
            raise

    def run(self, config, args):
        BaseCache.run(self, config, args)

        sha = self.get_git_sha(args)
        deps = self.get_deps(config, args)
        self.gen_dep(config, args, deps, sha)

class UploadCache(BaseCache):
    doc = N_('Build build cache to external storage.')
    name = 'upload-cache'

    def __init__(self, args=[]):
        BaseCache.__init__(self, args)

    def upload_dep(self, config, args, deps):
      sha = self.get_git_sha(args)
      for dep in deps:
        if dep['commit'] == sha:
          m.message('Cache already uploaded for this commit.')
          return

      tmpdir = tempfile.mkdtemp()
      private_key = os.getenv('CERBERO_PRIVATE_SSH_KEY');
      private_key_path = os.path.join(tmpdir, 'id_rsa')

      deps_filename = self.get_deps_filename(config)
      log_filename = self.get_log_filename(config)
      if not os.path.exists(deps_filename) or not os.path.exists(log_filename):
          raise FatalError(_('gen-cache must be run before running upload-cache.'))

      try:
          # Setup tempory private key from env
          ssh_opt = ['-o', 'StrictHostKeyChecking=no']
          if private_key:
              with os.fdopen(os.open(private_key_path, os.O_WRONLY | os.O_CREAT, 0o600), 'w') as f:
                  f.write(private_key)
                  f.write("\n")
                  f.close()
              ssh_opt += ['-i', private_key_path]
          ssh_cmd = ['ssh'] + ssh_opt + [self.ssh_address]
          scp_cmd = ['scp'] + ssh_opt

          # Ensure directory sturcture is in place
          branch = args.branch
          distro, arch = self.get_distro_and_arch(config)
          base_dir = os.path.join(branch, distro, arch)
          shell.new_call(ssh_cmd + ['mkdir -p %s' % base_dir ], verbose=True)

          # Upload the deps files first
          remote_deps_filename = os.path.join(base_dir, '%s-%s' % (sha, self.deps_filename))
          shell.new_call(scp_cmd + [deps_filename, '%s:%s' % (self.ssh_address, remote_deps_filename)],
                         verbose=True)

          # Upload the new log
          remote_tmp_log_filename = os.path.join(base_dir, '%s-%s' % (sha, self.log_filename))
          shell.new_call(scp_cmd + [log_filename, '%s:%s' % (self.ssh_address, remote_tmp_log_filename)],
                         verbose=True)

          # Override the new log in a way that we reduce the risk of corrupted
          # fetch.
          remote_log_filename = os.path.join(base_dir, self.log_filename)
          shell.new_call(ssh_cmd + ['mv', '-f', remote_tmp_log_filename, remote_log_filename],
                         verbose=True)

          # Now remove the obsoleted dep file if needed
          for dep in deps[self.log_size - 1:]:
              old_remote_deps_filename = os.path.join(base_dir, os.path.basename(dep['url']))
              shell.new_call(ssh_cmd + ['rm', '-f', old_remote_deps_filename], verbose=True)
      finally:
          shutil.rmtree(tmpdir)

    def run(self, config, args):
        BaseCache.run(self, config, args)
        deps = self.get_deps(config, args)
        self.upload_dep(config, args, deps)

register_command(FetchCache)
register_command(GenCache)
register_command(UploadCache)
