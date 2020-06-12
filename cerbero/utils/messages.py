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
import os
import time
import datetime
import logging
import shutil


ACTION_TPL = '-----> %s'
DONE_STEP_TPL = '[(%s/%s) %s -> %s]'
STEP_TPL = '[(%s/%s @ %d%%) %s -> %s]'
START_TIME = None
SHELL_CLEAR_LINE = "\r\033[K"
SHELL_MOVE_UP = "\033[F"


def console_is_interactive():
    if not os.isatty(sys.stdout.fileno()):
        return False
    if os.environ.get('TERM') == 'dumb':
        return False
    return True


def log(msg, logfile):
    if logfile is None:
        logging.info(msg)
    else:
        logfile.write(msg + '\n')

class StdoutManager:
    def __init__(self):
        self.status_line = ""
        self.clear_lines = 0

    def output(self, msg):
        self.clear_status()
        sys.stdout.write(msg)
        sys.stdout.flush()
        self.status_line = ""
        self.clear_lines = 0

    def clear_status (self):
        if console_is_interactive() and sys.platform != 'win32':
            clear_prev_status = SHELL_CLEAR_LINE + "".join((SHELL_CLEAR_LINE + SHELL_MOVE_UP for i in range(self.clear_lines)))
            sys.stdout.write(clear_prev_status)
            sys.stdout.flush()

    def output_status(self, status):
        self.clear_status()
        sys.stdout.write(status)
        sys.stdout.flush()
        self.status_line = status

        if console_is_interactive():
            self.clear_lines = len (status) // shutil.get_terminal_size().columns

STDOUT = StdoutManager()

def prepend_time(end=' '):
    global START_TIME
    s = ''
    if START_TIME is not None:
        s += str(datetime.timedelta(microseconds=int((time.monotonic() - START_TIME) * 1e6)))
        s += end
    return s

def output(msg, fd, end='\n'):
    prefix = prepend_time()
    if fd == sys.stdout:
        STDOUT.output(prefix + msg + end)
    else:
        fd.write(prefix + msg + end)
        fd.flush()

def output_status(msg):
    prefix = prepend_time()
    STDOUT.output_status(prefix + msg)


def message(msg, logfile=None):
    if logfile is None:
        output(msg, sys.stdout)
    else:
        log(msg, logfile)


def error(msg, logfile=None):
    STDOUT.clear_status()
    output(msg, sys.stderr)
    if logfile is not None:
        log(msg, logfile=logfile)


def warning(msg, logfile=None):
    error("WARNING: %s" % msg, logfile=logfile)


def action(msg, logfile=None):
    message(ACTION_TPL % msg, logfile=logfile)


def build_step(recipe_i, total_recipes, completion_percent, recipe, step, logfile=None):
    message(STEP_TPL % (recipe_i, total_recipes, completion_percent, recipe, step), logfile=logfile)

def build_recipe_done (recipe_i, total_recipes, recipe, msg, logfile=None):
    message(DONE_STEP_TPL % (recipe_i, total_recipes, recipe, msg), logfile=logfile)
