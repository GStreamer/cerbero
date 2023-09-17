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

import logging
import subprocess
import asyncio
import shlex
import sys
import os
import re
import tarfile
import zipfile
import tempfile
import time
import glob
import shutil
import hashlib
import urllib.request, urllib.error, urllib.parse
import collections
from pathlib import Path, PurePath

from cerbero.enums import CERBERO_VERSION, Platform, Distro
from cerbero.utils import _, system_info, split_version, CerberoSemaphore
from cerbero.utils import messages as m
from cerbero.utils import to_winpath
from cerbero.errors import CommandError, FatalError


PATCH = 'patch'
TAR = 'tar'
TARBALL_SUFFIXES = ('tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar.xz')
SUBPROCESS_EXCEPTIONS = (FileNotFoundError, PermissionError, subprocess.CalledProcessError)

info = system_info()
PLATFORM = info[0]
DISTRO = info[2]
CPU_BOUND_SEMAPHORE = CerberoSemaphore(info[4])
NON_CPU_BOUND_SEMAPHORE = CerberoSemaphore(2)
DRY_RUN = False

def _fix_mingw_cmd(path):
    reserved = ['/', ' ', '\\', ')', '(', '"']
    l_path = list(path)
    for i in range(len(path)):
        if path[i] == '\\':
            if i + 1 == len(path) or path[i + 1] not in reserved:
                l_path[i] = '/'
    return ''.join(l_path)

def _resolve_cmd(cmd, env):
    '''
    On Windows, we can't pass the PATH variable through the env= kwarg to
    subprocess.* and expect it to use that value to search for the command,
    because Python uses CreateProcess directly. Unlike execvpe, CreateProcess
    does not use the PATH env var in the env supplied to search for the
    executable. Hence, we need to search for it manually.
    '''
    if PLATFORM != Platform.WINDOWS or env is None or 'PATH' not in env:
        return cmd
    if not os.path.isabs(cmd[0]):
        resolved_cmd = shutil.which(cmd[0], path=env['PATH'])
        if not resolved_cmd:
            raise FatalError('Could not find {!r} in PATH {!r}'.format(cmd[0], env['PATH']))
        cmd[0] = resolved_cmd
    return cmd

def _cmd_string_to_array(cmd, env):
    if isinstance(cmd, list):
        return _resolve_cmd(cmd, env)
    assert(isinstance(cmd, str))
    if PLATFORM == Platform.WINDOWS:
        # fix paths with backslashes
        cmd = _fix_mingw_cmd(cmd)
    # If we've been given a string, run it through sh to get scripts working on
    # Windows and shell syntax such as && and env var setting working on all
    # platforms.
    return ['sh', '-c', cmd]

def set_max_cpu_bound_calls(number):
    global CPU_BOUND_SEMAPHORE
    CPU_BOUND_SEMAPHORE = CerberoSemaphore(number)

def set_max_non_cpu_bound_calls(number):
    global NON_CPU_BOUND_SEMAPHORE
    NON_CPU_BOUND_SEMAPHORE = CerberoSemaphore(number)

def call(cmd, cmd_dir='.', fail=True, verbose=False, logfile=None, env=None):
    '''
    Run a shell command
    DEPRECATED: Use new_call and a cmd array wherever possible

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    @param fail: whether or not to raise an exception if the command fails
    @type fail: bool
    '''
    try:
        if logfile is None:
            if verbose:
                m.message("Running command '%s'" % cmd)
            stream = None
        else:
            logfile.write("Running command '%s'\n" % cmd)
            logfile.flush()
            stream = logfile
        shell = True
        if PLATFORM == Platform.WINDOWS:
            # windows do not understand ./
            if cmd.startswith('./'):
                cmd = cmd[2:]
            # run all processes through sh.exe to get scripts working
            cmd = '%s "%s"' % ('sh -c', cmd)
            # fix paths with backslashes
            cmd = _fix_mingw_cmd(cmd)
            # Disable shell which uses cmd.exe
            shell = False
        if DRY_RUN:
            # write to sdterr so it's filtered more easilly
            m.error("cd %s && %s && cd %s" % (cmd_dir, cmd, os.getcwd()))
            ret = 0
        else:
            if env is not None:
                env = env.copy()
            else:
                env = os.environ.copy()

            # Force python scripts to print their output on newlines instead
            # of on exit. Ensures that we get continuous output in log files.
            env['PYTHONUNBUFFERED'] = '1'
            ret = subprocess.check_call(cmd, cwd=cmd_dir, bufsize=1,
                                       stderr=subprocess.STDOUT, stdout=stream,
                                       stdin=subprocess.DEVNULL,
                                       universal_newlines=True,
                                       env=env, shell=shell)
    except SUBPROCESS_EXCEPTIONS as e:
        if fail:
            msg = ''
            if stream:
                msg = 'Output in logfile {}'.format(logfile.name)
            raise CommandError(msg, cmd, getattr(e, 'returncode', -1))
        else:
            ret = 0
    return ret


def check_output(cmd, cmd_dir=None, fail=True, logfile=None, env=None, quiet=False):
    cmd = _cmd_string_to_array(cmd, env)
    stderr = logfile
    if quiet and not logfile:
        stderr = subprocess.DEVNULL
    if logfile:
        logfile.write(f'Running command {cmd!r} in {cmd_dir}\n')
        logfile.flush()

    try:
        o = subprocess.check_output(cmd, cwd=cmd_dir, env=env, stderr=stderr)
    except SUBPROCESS_EXCEPTIONS as e:
        msg = getattr(e, 'output', '')
        if isinstance(msg, bytes):
            msg = msg.decode(sys.stdout.encoding, errors='replace')
        if not fail:
            return msg
        if logfile:
            msg += '\nstderr in logfile {}'.format(logfile.name)
        raise CommandError(msg, cmd, getattr(e, 'returncode', -1))

    if sys.stdout.encoding:
        o = o.decode(sys.stdout.encoding, errors='replace')
    return o


def new_call(cmd, cmd_dir=None, fail=True, logfile=None, env=None, verbose=False, interactive=False, shell=False):
    cmd = _cmd_string_to_array(cmd, env)
    if logfile:
        logfile.write(f'Running command {cmd!r} in {cmd_dir}\n')
        logfile.flush()
    if verbose:
        m.message('Running {!r}\n'.format(cmd))
    if not interactive:
        stdin = subprocess.DEVNULL
    else:
        stdin = None
    try:
        subprocess.check_call(cmd, cwd=cmd_dir, env=env,
                              stdout=logfile, stderr=subprocess.STDOUT,
                              stdin=stdin, shell=shell)
    except SUBPROCESS_EXCEPTIONS as e:
        returncode = getattr(e, 'returncode', -1)
        if not fail:
            stream = logfile or sys.stderr
            if isinstance(e, FileNotFoundError):
                stream.write('{}: file not found\n'.format(cmd[0]))
            if isinstance(e, PermissionError):
                stream.write('{!r}: permission error\n'.format(cmd))
            return returncode
        msg = ''
        if logfile:
            msg = 'Output in logfile {}'.format(logfile.name)
        raise CommandError(msg, cmd, returncode)
    return 0


async def async_call(cmd, cmd_dir='.', fail=True, logfile=None, cpu_bound=True, env=None):
    '''
    Run a shell command

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    '''
    global CPU_BOUND_SEMAPHORE, NON_CPU_BOUND_SEMAPHORE
    semaphore = CPU_BOUND_SEMAPHORE if cpu_bound else NON_CPU_BOUND_SEMAPHORE

    async with semaphore:
        cmd = _cmd_string_to_array(cmd, env)

        if logfile is None:
            stream = None
        else:
            logfile.write(f'Running command {cmd!r} in {cmd_dir}\n')
            logfile.flush()
            stream = logfile

        if DRY_RUN:
            # write to sdterr so it's filtered more easilly
            m.error("cd %s && %s && cd %s" % (cmd_dir, cmd, os.getcwd()))
            return

        env = os.environ.copy() if env is None else env.copy()
        # Force python scripts to print their output on newlines instead
        # of on exit. Ensures that we get continuous output in log files.
        env['PYTHONUNBUFFERED'] = '1'
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=cmd_dir,
                            stderr=subprocess.STDOUT, stdout=stream,
                            stdin=subprocess.DEVNULL, env=env)
        await proc.wait()
        if proc.returncode != 0 and fail:
            msg = ''
            if stream:
                msg = 'Output in logfile {}'.format(logfile.name)
            raise CommandError(msg, cmd, proc.returncode)

        return proc.returncode


async def async_call_output(cmd, cmd_dir=None, logfile=None, cpu_bound=True, env=None):
    '''
    Run a shell command and get the output

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    '''
    global CPU_BOUND_SEMAPHORE, NON_CPU_BOUND_SEMAPHORE
    semaphore = CPU_BOUND_SEMAPHORE if cpu_bound else NON_CPU_BOUND_SEMAPHORE

    async with semaphore:
        cmd = _cmd_string_to_array(cmd, env)

        if logfile:
            logfile.write(f'Running command {cmd!r} in {cmd_dir}\n')
            logfile.flush()

        if PLATFORM == Platform.WINDOWS:
            import cerbero.hacks
            # On Windows, create_subprocess_exec with a PIPE fails while creating
            # a named pipe using tempfile.mktemp because we override os.path.join
            # to use / on Windows. Override the tempfile module's reference to the
            # original implementation, then change it back later so it doesn't leak.
            # XXX: Get rid of this once we move to Path.as_posix() everywhere
            tempfile._os.path.join = cerbero.hacks.oldjoin
            # The tempdir is derived from TMP and TEMP which use / as the path
            # separator, which fails for the same reason as above. Ensure that \ is
            # used instead.
            tempfile.tempdir = str(PurePath(tempfile.gettempdir()))

        proc = await asyncio.create_subprocess_exec(*cmd, cwd=cmd_dir,
                stdout=subprocess.PIPE, stderr=logfile,
                stdin=subprocess.DEVNULL, env=env)
        (output, unused_err) = await proc.communicate()

        if PLATFORM == Platform.WINDOWS:
            os.path.join = cerbero.hacks.join

        if sys.stdout.encoding:
            output = output.decode(sys.stdout.encoding, errors='replace')

        if proc.returncode != 0:
            raise CommandError(output, cmd, proc.returncode)

        return output


def apply_patch(patch, directory, strip=1, logfile=None):
    '''
    Apply a patch

    @param patch: path of the patch file
    @type patch: str
    @param directory: directory to apply the apply
    @type: directory: str
    @param strip: strip
    @type strip: int
    '''
    m.log("Applying patch {}".format(patch), logfile)
    new_call([PATCH, f'-p{strip}', '-f', '-i', patch], cmd_dir=directory, logfile=logfile)


async def unpack(filepath, output_dir, logfile=None, force_tarfile=False):
    '''
    Extracts a tarball

    @param filepath: path of the tarball
    @type filepath: str
    @param output_dir: output directory
    @type output_dir: str
    @param force_tarfile: forces use of tarfile
    @type force_tarfile: bool
    '''
    m.log('Unpacking {} in {}'.format(filepath, output_dir), logfile)

    if filepath.endswith(TARBALL_SUFFIXES):
        # Recent versions of tar are much faster than the tarfile module, but we
        # can't use tar on Windows because MSYS tar is ancient and buggy.
        if DISTRO == Distro.MSYS or force_tarfile:
            cmode = 'bz2' if filepath.endswith('bz2') else filepath[-2:]
            tf = tarfile.open(filepath, mode='r:' + cmode)
            tf.extractall(path=output_dir)
        else:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            await async_call([get_tar_cmd(), '-C', output_dir, '-xf', filepath, '--no-same-owner'])

    elif filepath.endswith('.zip'):
        zf = zipfile.ZipFile(filepath, "r")
        zf.extractall(path=output_dir)
    elif filepath.endswith('.dmg'):
        out_dir_name = os.path.splitext(os.path.split(filepath)[1])[0]
        with tempfile.TemporaryDirectory() as vol_name:
            output_dir = os.path.join(output_dir, out_dir_name)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            await async_call(['hdiutil', 'attach', '-readonly', '-mountpoint', vol_name, filepath], logfile=logfile, cpu_bound=False)
            await async_call(['cp', '-r', vol_name + '/', output_dir], logfile=logfile, cpu_bound=False)
            await async_call(['hdiutil', 'detach', vol_name], logfile=logfile, cpu_bound=False)
    else:
        raise FatalError("Unknown tarball format %s" % filepath)


async def download(url, dest, check_cert=True, overwrite=False, logfile=None, mirrors=None):
    '''
    Downloads a file

    @param url: url to download
    @type: str
    @param dest: dest where the file will be saved
    @type dest: str
    @param check_cert: whether to check certificates or not
    @type check_cert: bool
    @param overwrite: whether to overwrite the dest or not
    @type check_cert: bool
    @param logfile: path to the file to log instead of stdout
    @type logfile: str
    @param mirrors: list of mirrors to use as fallback
    @type logfile: list
    '''
    user_agent = 'GStreamerCerbero/' + CERBERO_VERSION

    if not overwrite and os.path.exists(dest):
        if logfile is None:
            logging.info("File %s already downloaded." % dest)
        return
    else:
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        m.log("Downloading {}".format(url), logfile)

    urls = [url]
    if mirrors is not None:
        filename = os.path.basename(url)
        # Add a traling '/' the url so that urljoin joins correctly urls
        # in case users provided it without the trailing '/'
        urls += [urllib.parse.urljoin(u + '/', filename) for u in mirrors]

    if sys.platform.startswith('win'):
        cmd = ['powershell', '-Command', 'Set-Variable -Name ' \
               'ProgressPreference -Value \'SilentlyContinue\'; ' \
               f'Invoke-WebRequest -UserAgent {user_agent} -OutFile {dest} ' \
               '-Method Get -Uri %s']
    elif shutil.which('wget'):
        cmd = ['wget', '--user-agent', user_agent, '--tries=2', '--timeout=20',
               '--progress=dot:giga', '-O', dest]
        if not check_cert:
            cmd += ['--no-check-certificate']
        cmd += ['%s']
    elif shutil.which('curl'):
        cmd = ['curl', '-L', '--fail', '--user-agent', user_agent, '--retry', '2',
               '--connect-timeout', '20', '--progress-bar', '-o', dest]
        if not check_cert:
            cmd += ['-k']
        cmd += ['%s']
    else:
        raise FatalError('Need either wget or curl to download things')

    errors = []
    url_fmt = cmd[-1]
    cmd = cmd[:-1]
    for murl in urls:
        tries = 2
        while tries > 0:
            try:
                return await async_call(cmd + [url_fmt % murl], cpu_bound=False,
                                        logfile=logfile)
            except Exception as ex:
                if os.path.exists(dest):
                    os.remove(dest)
                tries -= 1
                if tries == 0:
                    errors.append((murl, ex))
    if len(errors) == 1:
        errors = errors[0]
    raise FatalError('Failed to download {!r}: {!r}'.format(url, errors))


def _splitter(string, base_url):
    lines = string.split('\n')
    for line in lines:
        try:
            yield "%s/%s" % (base_url, line.split(' ')[2])
        except:
            continue

def ls_files(files, prefix):
    if not files:
        return []
    sfiles = set()
    prefix = Path(prefix)
    for f in ' '.join(files).split():
        sfiles.update([i.relative_to(prefix).as_posix() for i in prefix.glob(f)])
    return list(tuple(sfiles))

def ls_dir(dirpath, prefix):
    files = []
    for root, dirnames, filenames in os.walk(dirpath):
        _root = root.split(prefix)[1]
        if _root[0] == '/':
            _root = _root[1:]
        files.extend([os.path.join(_root, x) for x in filenames])
    return files


def find_newer_files(prefix, compfile):
    cmd = ['find', '.', '-type', 'f', '-cnewer', compfile]
    out = check_call(cmd, cmd_dir=prefix, fail=False)
    return out.strip().split('\n')


def replace(filepath, replacements):
    ''' Replaces keys in the 'replacements' dict with their values in file '''
    with open(filepath, 'r') as f:
        content = f.read()
    for k, v in replacements.items():
        content = content.replace(k, v)
    with open(filepath, 'w+') as f:
        f.write(content)


def find_files(pattern, prefix):
    return glob.glob(os.path.join(prefix, pattern))


def prompt(message, options=[]):
    ''' Prompts the user for input with the message and options '''
    if len(options) != 0:
        message = "%s [%s] " % (message, '/'.join(options))
    res = input(message)
    while res not in [str(x) for x in options]:
        res = input(message)
    return res


def prompt_multiple(message, options):
    ''' Prompts the user for input with using a list of string options'''
    output = message + '\n'
    for i in range(len(options)):
        output += "[%s] %s\n" % (i, options[i])
    res = input(output)
    while res not in [str(x) for x in range(len(options))]:
        res = input(output)
    return options[int(res)]


def copy_dir(src, dest):
    if not os.path.exists(src):
        return
    for path in os.listdir(src):
        s = os.path.join(src, path)
        d = os.path.join(dest, path)
        if not os.path.exists(os.path.dirname(d)):
            os.makedirs(os.path.dirname(d))
        if os.path.isfile(s):
            shutil.copy(s, d)
        elif os.path.isdir(s):
            copy_dir(s, d)


def touch(path, create_if_not_exists=False, offset=0):
    if not os.path.exists(path):
        if create_if_not_exists:
            open(path, 'w').close()
        else:
            return
    t = time.time() + offset
    os.utime(path, (t, t))


def file_hash(path):
    '''
    Get the file md5 hash
    '''
    return hashlib.md5(open(path, 'rb').read()).digest()


def files_checksum(paths):
    '''
    Get the md5 checksum of the files

    @paths: list of paths
    @type: list
    @return: the md5 checksum
    @rtype: str
    '''
    m = hashlib.md5()
    for f in paths:
        m.update(open(f, 'rb').read())
    return m.digest()


def enter_build_environment(platform, arch, distro, sourcedir=None, bash_completions=None, env=None):
    '''
    Enters to a new shell with the build environment
    '''
    SHELLRC =  '''
if [ -e ~/{rc_file} ]; then
source ~/{rc_file}
fi
{sourcedirsh}
{prompt}
# For some reason MSYS2 refuses to inherit PATH from the env, so force it
if [ "$MSYSTEM" = "UCRT64" ]; then
  PATH=$(cygpath -p "{path}")
fi
BASH_COMPLETION_SCRIPTS="{bash_completions}"
BASH_COMPLETION_PATH="$CERBERO_PREFIX/share/bash-completion/completions"
for f in $BASH_COMPLETION_SCRIPTS; do
  [ -f "$BASH_COMPLETION_PATH/$f" ] && . "$BASH_COMPLETION_PATH/$f"
done
'''
    MSYSBAT = '''
C:\\MinGW\\msys\\1.0\\bin\\bash.exe --rcfile %s
'''
    MSYS2BAT =  '''
C:\\msys64\\msys2_shell.cmd -ucrt64 -defterm -no-start -here -use-full-path -c 'bash --rcfile %s'
'''
    if sourcedir:
        sourcedirsh = 'cd ' + sourcedir
    else:
        sourcedirsh = ''
    if bash_completions is None:
        bash_completions = set()
    bash_completions = ' '.join(bash_completions)

    env = os.environ.copy() if env is None else env

    shell = os.environ.get('SHELL', '/bin/bash')
    if 'zsh' in shell:
        rc_file = '.zshrc'
        rc_opt = '--rcs'
        prompt = os.environ.get('PROMPT', '')
        prompt = 'PROMPT="%{{$fg[green]%}}[cerbero-{platform}-{arch}]%{{$reset_color%}} $PROMPT"'.format(
            platform=platform, arch=arch)
    else:
        rc_file = '.bashrc'
        rc_opt = '--rcfile'
        prompt = os.environ.get('PS1', '')
        prompt = r'PS1="\[\033[01;32m\][cerbero-{platform}-{arch}]\[\033[00m\] $PS1"'.format(
            platform=platform, arch=arch)
    shellrc = SHELLRC.format(rc_file=rc_file, sourcedirsh=sourcedirsh,
        prompt=prompt, bash_completions=bash_completions, path=env['PATH'])

    if PLATFORM == Platform.WINDOWS:
        if distro == Distro.MSYS:
            bat_tpl = MSYSBAT
        else:
            bat_tpl = MSYS2BAT
        msysbatdir = tempfile.mkdtemp()
        msysbat = os.path.join(msysbatdir, "msys.bat")
        bashrc = os.path.join(msysbatdir, "bash.rc")
        with open(msysbat, 'w+') as f:
            f.write(bat_tpl % bashrc)
        with open(bashrc, 'w+') as f:
            f.write(shellrc)
        subprocess.check_call(msysbat, shell=True, env=env)
        # We should remove the temporary directory
        # but there is a race with the bash process
    else:
        with tempfile.TemporaryDirectory() as tmp:
            rc_tmp = open(os.path.join(tmp, rc_file), 'w+')
            rc_tmp.write(shellrc)
            rc_tmp.flush()
            if 'zsh' in shell:
                env["ZDOTDIR"] = tmp.name
                os.execlpe(shell, shell, env)
            else:
                # Check if the shell supports passing the rcfile
                if os.system("%s %s %s -c echo 'test' > /dev/null 2>&1" % (shell, rc_opt, rc_tmp.name)) == 0:
                    os.execlpe(shell, shell, rc_opt, rc_tmp.name, env)
                else:
                    env["CERBERO_ENV"] = "[cerbero-%s-%s]" % (platform, arch)
                    os.execlpe(shell, shell, env)


def get_tar_cmd():
    '''
    Returns the tar command to use

    @return: the tar command
    @rtype: str
    '''
    # Use bsdtar with MSYS2 since tar hangs
    # https://github.com/msys2/MSYS2-packages/issues/1548
    if DISTRO == Distro.MSYS2:
        return 'bsdtar'
    else:
        return TAR


def get_path_minus_msys(path):
    path = path.split(os.pathsep)
    newpath = []
    msys2_prefix = to_winpath('/')
    for p in path:
        if msys2_prefix not in p:
            newpath.append(p)
    return os.pathsep.join(newpath)


def check_tool_version(tool_name, needed, env, version_arg=None):
    found = False
    newer = False
    if version_arg is None:
        version_arg = '--version'
    if env is None:
        env = os.environ.copy()
    path = env['PATH']
    # We do not want the MSYS2 CMake because it doesn't support MSVC
    if tool_name == 'cmake' and DISTRO == Distro.MSYS2:
        path = get_path_minus_msys(path)
    tool = shutil.which(tool_name, path=path)
    if not tool:
        return None, False, False
    try:
        out = check_output([tool, version_arg], env=env)
    except FatalError:
        return None, False, False
    m = re.search(r'([0-9]+\.[0-9]+(\.[0-9]+)?)', out)
    if m:
        found = m.groups()[0]
        newer = split_version(found) >= split_version(needed)

    return tool, found, newer

def windows_proof_rename(from_name, to_name):
    '''
    On Windows, if you try to rename a file or a directory that you've newly
    created, an anti-virus may be holding a lock on it, and renaming it will
    yield a PermissionError. In this case, the only thing we can do is try and
    try again.
    '''
    delays = [0.1, 0.1, 0.2, 0.2, 0.2, 0.5, 0.5, 1, 1, 1, 1, 2]
    if PLATFORM == Platform.WINDOWS:
        for d in delays:
            try:
                os.rename(from_name, to_name)
                return
            except PermissionError:
                time.sleep(d)
                continue
    # Try one last time and throw an error if it fails again
    os.rename(from_name, to_name)

def symlink(src, dst, working_dir=None):
    prev_wd = os.getcwd()
    if working_dir:
        os.chdir(working_dir)
    try:
        os.symlink(src, dst)
    except FileExistsError:
        # Explicitly raise this, since FileExistsError is a subclass of OSError
        # and would incorrectly trigger a copy below.
        raise
    except OSError:
        # if symlinking fails, copy instead
        if os.path.isdir(src):
            copy_dir(src, dst)
        else:
            shutil.copy(src, dst)
    finally:
        os.chdir(prev_wd)

class BuildStatusPrinter:
    def __init__(self, steps, interactive):
        self.steps = steps[:]
        self.step_to_recipe = collections.defaultdict(list)
        self.recipe_to_step = {}
        self.total = 0
        self.count = 0
        self.interactive = interactive
        # FIXME: Default MSYS shell doesn't handle ANSI escape sequences correctly
        if os.environ.get('TERM') == 'cygwin':
            m.message('Running under MSYS: reverting to basic build status output')
            self.interactive = False

    def remove_recipe(self, recipe_name):
        if recipe_name in self.recipe_to_step:
            self.step_to_recipe[self.recipe_to_step[recipe_name]].remove(recipe_name)
            del self.recipe_to_step[recipe_name]
        self.output_status_line()

    def built(self, count, recipe_name):
        self.count += 1
        if self.interactive:
            m.build_recipe_done(self.count, self.total, recipe_name, _("built"))
        self.remove_recipe(recipe_name)

    def already_built(self, count, recipe_name):
        self.count += 1
        if self.interactive:
            m.build_recipe_done(self.count, self.total, recipe_name, _("already built"))
        else:
            m.build_recipe_done(count, self.total, recipe_name, _("already built"))
        self.output_status_line()

    def _get_completion_percent (self):
        one_recipe = 100. / float (self.total)
        one_step = one_recipe / len (self.steps)
        completed = float(self.count) * one_recipe
        for i, step in enumerate (self.steps):
            completed += len(self.step_to_recipe[step]) * (i+1) * one_step
        return int(completed)

    def update_recipe_step(self, count, recipe_name, step):
        self.remove_recipe(recipe_name)
        self.step_to_recipe[step].append(recipe_name)
        self.recipe_to_step[recipe_name] = step
        if not self.interactive:
            m.build_step(count, self.total, self._get_completion_percent(), recipe_name, step)
        else:
            self.output_status_line()

    def generate_status_line(self):
        s = "[(" + str(self.count) + "/" + str(self.total) + " @ " + str(self._get_completion_percent()) + "%)"
        for step in self.steps:
            if self.step_to_recipe[step]:
                s += " " + str(step).upper() + ": " + ", ".join(self.step_to_recipe[step])
        s += "]"
        return s

    def output_status_line(self):
        if self.interactive:
            m.output_status(self.generate_status_line())

    def heartbeat(self):
        if not self.interactive:
            m.message(self.generate_status_line())
        else:
            self.output_status_line()
