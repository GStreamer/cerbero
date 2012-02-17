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

from cerbero.utils import _
from cerbero.errors import FatalError


PATCH = 'patch'
TAR = 'tar'


def call (cmd, cmd_dir):
    try:
        logging.info ("Running command '%s'" % cmd)
        ret = subprocess.check_call(cmd, cwd=cmd_dir,
                                    stderr=subprocess.STDOUT,
                                    stdout=sys.stdout, env=os.environ.copy(),
                                    shell=True)
    except Exception, ex:
        raise FatalError (_("Error running command %s: %s") % (cmd, ex))
    return ret


def check_call (cmd, cmd_dir):
    try:
        ret = subprocess.check_output (shlex.split(cmd), cwd=cmd_dir)
    except Exception, ex:
        raise FatalError (_("Error running command %s: %s") % (cmd, ex))
    return ret


def apply_patch(patch, directory, strip=1):
    logging.info("Applying patch %s" % (patch))
    call ('%s -p%s -f -i %s', (PATCH, strip, patch))


def unpack(filename, dest):
    logging.info("Unpacking %s in %s" % (filename, dest))
    if filename.endswith('tar.gz') or filename.endswith('tar.bz2'):
        tf = tarfile.open(filename, mode='r:*')
        tf.extractall(path=dest)
    if filename.endswith('tar.xz'):
        call ("%s -Jxf %s" % (TAR, filename), dest)
