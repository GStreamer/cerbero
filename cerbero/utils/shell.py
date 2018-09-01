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
from distutils.version import StrictVersion

from cerbero.enums import Platform
from cerbero.utils import _, system_info, to_unixpath
from cerbero.utils import messages as m
from cerbero.errors import FatalError


PATCH = 'patch'
TAR = 'tar'


PLATFORM = system_info()[0]
LOGFILE = None  # open('/tmp/cerbero.log', 'w+')
DRY_RUN = False


def set_logfile_output(location):
    '''
    Sets a file to log

    @param location: path for the log file
    @type location: str
    '''

    global LOGFILE
    if not LOGFILE is None:
        raise Exception("Logfile was already open. Forgot to call "
                        "close_logfile_output() ?")
    LOGFILE = open(location, "w+")


def close_logfile_output(dump=False):
    '''
    Close the current log file

    @param dump: dump the log file to stdout
    @type dump: bool
    '''
    global LOGFILE
    if LOGFILE is None:
        raise Exception("No logfile was open")
    if dump:
        LOGFILE.seek(0)
        while True:
            data = LOGFILE.read()
            if data:
                print(data)
            else:
                break
    # if logfile is empty, remove it
    pos = LOGFILE.tell()
    LOGFILE.close()
    if pos == 0:
        os.remove(LOGFILE.name)
    LOGFILE = None


class StdOut:

    def __init__(self, stream=sys.stdout):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


def _fix_mingw_cmd(path):
    reserved = ['/', ' ', '\\', ')', '(', '"']
    l_path = list(path)
    for i in range(len(path)):
        if path[i] == '\\':
            if i + 1 == len(path) or path[i + 1] not in reserved:
                l_path[i] = '/'
    return ''.join(l_path)


def call(cmd, cmd_dir='.', fail=True, verbose=False):
    '''
    Run a shell command

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    @param fail: whether or not to raise an exception if the command fails
    @type fail: bool
    '''
    try:
        if LOGFILE is None:
            if verbose:
                m.message("Running command '%s'" % cmd)
        else:
            LOGFILE.write("Running command '%s'\n" % cmd)
            LOGFILE.flush()
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
        stream = LOGFILE or sys.stdout
        if DRY_RUN:
            # write to sdterr so it's filtered more easilly
            m.error("cd %s && %s && cd %s" % (cmd_dir, cmd, os.getcwd()))
            ret = 0
        else:
            ret = subprocess.check_call(cmd, cwd=cmd_dir,
                                       stderr=subprocess.STDOUT,
                                       stdout=StdOut(stream),
                                       env=os.environ.copy(), shell=shell)
    except subprocess.CalledProcessError:
        if fail:
            raise FatalError(_("Error running command: %s") % cmd)
        else:
            ret = 0
    return ret


def check_call(cmd, cmd_dir=None, shell=False, split=True, fail=False, env=None):
    if env is None:
        env = os.environ.copy()
    if split and isinstance(cmd, str):
        cmd = shlex.split(cmd)
    try:
        process = subprocess.Popen(cmd, cwd=cmd_dir, env=env,
                                   stdout=subprocess.PIPE,
                                   stderr=open(os.devnull), shell=shell)
        output, unused_err = process.communicate()
        if process.poll() and fail:
            raise Exception()
    except Exception:
        raise FatalError(_("Error running command: %s") % cmd)

    if sys.stdout.encoding:
        output = output.decode(sys.stdout.encoding)

    return output


def apply_patch(patch, directory, strip=1):
    '''
    Apply a patch

    @param patch: path of the patch file
    @type patch: str
    @param directory: directory to apply the apply
    @type: directory: str
    @param strip: strip
    @type strip: int
    '''

    logging.info("Applying patch %s" % (patch))
    call('%s -p%s -f -i %s' % (PATCH, strip, patch), directory)


def unpack(filepath, output_dir):
    '''
    Extracts a tarball

    @param filepath: path of the tarball
    @type filepath: str
    @param output_dir: output directory
    @type output_dir: str
    '''
    logging.info("Unpacking %s in %s" % (filepath, output_dir))
    if filepath.endswith('tar.gz') or filepath.endswith('tgz'):
        tf = tarfile.open(filepath, mode='r:gz')
        tf.extractall(path=output_dir)
    elif filepath.endswith('tar.bz2') or filepath.endswith('tbz2'):
        tf = tarfile.open(filepath, mode='r:bz2')
        tf.extractall(path=output_dir)
    elif filepath.endswith('tar.xz'):
        call("%s -Jxf %s" % (TAR, to_unixpath(filepath)), output_dir)
    elif filepath.endswith('.zip'):
        zf = zipfile.ZipFile(filepath, "r")
        zf.extractall(path=output_dir)
    else:
        raise FatalError("Unknown tarball format %s" % filepath)

def download_wget(url, destination=None, recursive=False, check_cert=True, overwrite=False):
    '''
    Downloads a file with wget

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    '''
    cmd = "wget %s " % url
    path = None
    if recursive:
        cmd += "-r "
        path = destination
    else:
        if destination is not None:
            cmd += "-O %s " % destination

    if not check_cert:
        cmd += " --no-check-certificate"

    if not recursive and not overwrite and os.path.exists(destination):
        if LOGFILE is None:
            logging.info("File %s already downloaded." % destination)
    else:
        if not recursive and not os.path.exists(os.path.dirname(destination)):
            os.makedirs(os.path.dirname(destination))
        elif recursive and not os.path.exists(destination):
            os.makedirs(destination)

        if LOGFILE:
            LOGFILE.write("Downloading %s\n" % url)
        else:
            logging.info("Downloading %s", url)
        try:
            call(cmd, path)
        except FatalError as e:
            if os.path.exists(destination):
                os.remove(destination)
            raise e


def download_urllib2(url, destination=None, recursive=False, check_cert=True, overwrite=False):
    '''
    Download a file with urllib2, which does not rely on external programs

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    '''
    if recursive:
        logging.warn("Recursive download is not implemented with urllib2, trying wget")
        download_wget(url, destination, recursive, check_cert, overwrite)
        return
    ctx = None
    if not check_cert:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    # This is roughly what wget and curl do
    if not destination:
        destination = os.path.basename(url)

    if not overwrite and os.path.exists(destination):
        if LOGFILE is None:
            logging.info("File %s already downloaded." % destination)
        return
    if not os.path.exists(os.path.dirname(destination)):
        os.makedirs(os.path.dirname(destination))
    if LOGFILE:
        LOGFILE.write("Downloading %s\n" % url)
    else:
        logging.info("Downloading %s", url)
    try:
        logging.info(destination)
        with open(destination, 'wb') as d:
            f = urllib.request.urlopen(url, context=ctx)
            d.write(f.read())
    except urllib.error.HTTPError as e:
        if os.path.exists(destination):
            os.remove(destination)
        raise e


def download_curl(url, destination=None, recursive=False, check_cert=True, overwrite=False):
    '''
    Downloads a file with cURL

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    '''
    path = None
    if recursive:
        raise FatalError(_("cURL doesn't support recursive downloads"))

    cmd = "curl -L "
    if not check_cert:
        cmd += " -k "
    if destination is not None:
        cmd += "%s -o %s " % (url, destination)
    else:
        cmd += "-O %s " % url

    if not recursive and not overwrite and os.path.exists(destination):
        logging.info("File %s already downloaded." % destination)
    else:
        if not recursive and not os.path.exists(os.path.dirname(destination)):
            os.makedirs(os.path.dirname(destination))
        elif recursive and not os.path.exists(destination):
            os.makedirs(destination)

        logging.info("Downloading %s", url)
        try:
            call(cmd, path)
        except FatalError as e:
            if os.path.exists(destination):
                os.remove(destination)
            raise e


def _splitter(string, base_url):
    lines = string.split('\n')
    for line in lines:
        try:
            yield "%s/%s" % (base_url, line.split(' ')[2])
        except:
            continue


def recursive_download(url, destination):
    '''
    Recursive download for servers that don't return a list a url's but only
    the index.html file
    '''
    raw_list = check_call('curl %s' % url)

    with tempfile.NamedTemporaryFile() as f:
        for path in _splitter(raw_list, url):
            f.file.write(path + '\n')
        if not os.path.exists(destination):
            os.makedirs(destination)
        call("wget -i %s %s" % (f.name, url), destination)


def ls_files(files, prefix):
    if files == []:
        return files
    sfiles = check_call('ls %s' % ' '.join(files),
                        prefix, True, False, False).split('\n')
    sfiles.remove('')
    return list(set(sfiles))


def ls_dir(dirpath, prefix):
    files = []
    for root, dirnames, filenames in os.walk(dirpath):
        _root = root.split(prefix)[1]
        if _root[0] == '/':
            _root = _root[1:]
        files.extend([os.path.join(_root, x) for x in filenames])
    return files


def find_newer_files(prefix, compfile, include_link=False):
    include_links = include_link and '-L' or ''
    cmd = 'find %s * -type f -cnewer %s' % (include_links, compfile)
    sfiles = check_call(cmd, prefix, True, False, False).split('\n')
    sfiles.remove('')
    return sfiles


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


def enter_build_environment(platform, arch, sourcedir=None):
    '''
    Enters to a new shell with the build environment
    '''
    BASHRC =  '''
if [ -e ~/.bashrc ]; then
source ~/.bashrc
fi
PS1='\[\033[01;32m\][cerbero-%s-%s]\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
'''

    bashrc = tempfile.NamedTemporaryFile()
    bashrc.write((BASHRC % (platform, arch)).encode())
    bashrc.flush()

    if sourcedir:
        os.chdir(sourcedir)

    if PLATFORM == Platform.WINDOWS:
        # $MINGW_PREFIX/home/username
        msys = os.path.join(os.path.expanduser('~'),
                            '..', '..', 'msys.bat')
        subprocess.check_call('%s -noxvrt' % msys)
    else:
        shell = os.environ.get('SHELL', '/bin/bash')
        if os.system("%s --rcfile %s -c echo 'test' > /dev/null 2>&1" % (shell, bashrc.name)) == 0:
            os.execlp(shell, shell, '--rcfile', bashrc.name)
        else:
            os.environ["CERBERO_ENV"] = "[cerbero-%s-%s]" % (platform, arch)
            os.execlp(shell, shell)

    bashrc.close()

def which(pgm, path=None):
    if path is None:
        path = os.getenv('PATH')
    for p in path.split(os.path.pathsep):
        p = os.path.join(p, pgm)
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
        if PLATFORM == Platform.WINDOWS:
            for ext in os.getenv('PATHEXT').split(';'):
                pext = p + ext
                if os.path.exists(pext):
                    return pext

def check_perl_version(needed):
    perl = which('perl')
    try:
        out = check_call([perl, '--version'])
    except FatalError:
        return None, None, None
    m = re.search('v[0-9]+\.[0-9]+(\.[0-9]+)?', out)
    if not m:
        raise FatalError('Could not detect perl version')
    found = m.group()[1:]
    newer = StrictVersion(found) >= StrictVersion(needed)
    return perl, found, newer
