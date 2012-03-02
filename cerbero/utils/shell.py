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
import tarfile
import zipfile
import tempfile

from cerbero.utils import _
from cerbero.errors import FatalError


PATCH = 'patch'
TAR = 'tar'


def call(cmd, cmd_dir='.', fail=True):
    '''
    Run a shell command

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    @param fail: wheter to raise an exception if the command failed or not
    @type fail: bool
    '''
    try:
        logging.info("Running command '%s'" % cmd)
        ret = subprocess.check_call(cmd, cwd=cmd_dir,
                                    stderr=subprocess.STDOUT,
                                    stdout=sys.stdout, env=os.environ.copy(),
                                    shell=True)
    except Exception, ex:
        if fail:
            raise FatalError(_("Error running command %s: %s") % (cmd, ex))
        else:
            ret = 0
    return ret


def check_call(cmd, cmd_dir=None):
    try:
        ret = subprocess.check_output(shlex.split(cmd), cwd=cmd_dir)
    except Exception, ex:
        raise FatalError(_("Error running command %s: %s") % (cmd, ex))
    return ret


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
    call('%s -p%s -f -i %s', (PATCH, strip, patch))


def unpack(filepath, output_dir):
    '''
    Extracts a tarball

    @param filepath: path of the tarball
    @type filepath: str
    @param output_dir: output directory
    @type output_dir: str
    '''
    logging.info("Unpacking %s in %s" % (filepath, output_dir))
    if filepath.endswith('tar.gz') or filepath.endswith('tar.bz2'):
        tf = tarfile.open(filepath, mode='r:*')
        tf.extractall(path=output_dir)
    if filepath.endswith('tar.xz'):
        call("%s -Jxf %s" % (TAR, filepath), output_dir)
    if filepath.endswith('.zip'):
        zf = zipfile.ZipFile(filepath, "r")
        zf.extractall(path=output_dir)

def download(url, destination=None, recursive=False):
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

    if not recursive and os.path.exists(destination):
        logging.info("File %s already downloaded." % destination)
    else:
        logging.info("Downloading %s", url)
        try:
            call(cmd, path)
        except FatalError, e:
            os.remove (tarfile)
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
    Recursive download for servers that don't return a list a url's but only the
    index.html file
    '''
    raw_list = check_call('curl %s' % url)

    with tempfile.NamedTemporaryFile() as f:
        for path in _splitter(raw_list, url):
            f.file.write(path + '\n')
        if not os.path.exists(destination):
            os.makedirs(destination)
        call("wget -i %s %s" % (f.name, url), destination)

