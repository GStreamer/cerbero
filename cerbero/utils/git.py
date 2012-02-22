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

from cerbero.utils import shell


GIT = '/usr/bin/git'


def init (git_dir):
    shell.call ('mkdir -p %s')
    shell.call ('%s init .' % GIT, git_dir)


def clean(git_dir):
    return shell.call('%s clean -dfx' % GIT, git_dir)


def fetch(git_dir):
    return shell.call('%s fetch --all' % GIT, git_dir)


def checkout(git_dir, ref):
    return shell.call('%s reset --hard %s' % (GIT, ref), git_dir)


def local_checkout(git_dir, local_repo_dir, ref):
    shell.call('%s clone --local %s .' % (GIT, local_repo_dir), git_dir)
    return shell.call('%s reset --hard %s' % (GIT, ref), git_dir)


def add_remote(git_dir, name, url):
    shell.call('%s remote add %s %s' % (GIT, name, url), git_dir,
               fail=False)
