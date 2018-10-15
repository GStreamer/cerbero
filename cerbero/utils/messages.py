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

import sys
import time
import datetime


ACTION_TPL = '-----> %s'
STEP_TPL = '[(%s/%s) %s -> %s ]'
START_TIME = None


def _output(msg, fd):
    global START_TIME
    prefix = ''
    if START_TIME is not None:
        prefix = str(datetime.timedelta(seconds=int(time.clock() - START_TIME)))
        prefix += ' '
    fd.write(prefix + msg + '\n')
    fd.flush()


def message(msg):
    _output(msg, sys.stdout)


def error(msg):
    _output(msg, sys.stderr)


def warning(msg):
    error("WARNING: %s" % msg)


def action(msg):
    message(ACTION_TPL % msg)


def build_step(count, total, recipe, step):
    message(STEP_TPL % (count, total, recipe, step))
