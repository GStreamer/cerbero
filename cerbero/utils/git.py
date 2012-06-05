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

import os
import shutil

from cerbero.utils import shell


GIT = 'git'


def init(git_dir):
    '''
    Initialize a git repository with 'git init'

    @param git_dir: path of the git repository
    @type git_dir: str
    '''
    shell.call('mkdir -p %s' % git_dir)
    shell.call('%s init' % GIT, git_dir)


def clean(git_dir):
    '''
    Clean a git respository with clean -dfx

    @param git_dir: path of the git repository
    @type git_dir: str
    '''
    return shell.call('%s clean -dfx' % GIT, git_dir)


def list_tags(git_dir, fail=True):
    '''
    List all tags

    @param git_dir: path of the git repository
    @type git_dir: str
    @param fail: raise an error if the command failed
    @type fail: false
    @return: list of tag names (str)
    @rtype: list
    '''
    tags = shell.check_call('%s tag -l' % GIT, git_dir, fail=fail)
    tags = tags.strip()
    if tags:
        tags = tags.split('\n')
    return tags


def create_tag(git_dir, tagname, tagdescription, commit, fail=True):
    '''
    Create a tag using commit

    @param git_dir: path of the git repository
    @type git_dir: str
    @param tagname: name of the tag to create
    @type tagname: str
    @param tagdescription: the tag description
    @type tagdescription: str
    @param commit: the tag commit to use
    @type commit: str
    @param fail: raise an error if the command failed
    @type fail: false
    '''
    shell.call('%s tag -s %s -m "%s" %s' % (GIT, tagname, tagdescription, commit),
            git_dir, fail=fail)
    return shell.call('%s push origin --tags' % GIT, git_dir, fail=fail)


def delete_tag(git_dir, tagname, fail=True):
    '''
    Delete a tag

    @param git_dir: path of the git repository
    @type git_dir: str
    @param tagname: name of the tag to delete
    @type tagname: str
    @param fail: raise an error if the command failed
    @type fail: false
    '''
    return shell.call('%s tag -d %s' % (GIT, tagname), git_dir, fail=fail)


def fetch(git_dir, fail=True):
    '''
    Fetch all refs from all the remotes

    @param git_dir: path of the git repository
    @type git_dir: str
    @param fail: raise an error if the command failed
    @type fail: false
    '''
    # Remove all tags in case they have been updated, because
    # git won't fetch tags if they are already fetched
    for tagname in list_tags(git_dir, fail):
        delete_tag(git_dir, tagname, fail)
    return shell.call('%s fetch --all' % GIT, git_dir, fail=fail)


def checkout(git_dir, commit):
    '''
    Reset a git repository to a given commit

    @param git_dir: path of the git repository
    @type git_dir: str
    @param commit: the commit to checkout
    @type commit: str
    '''
    return shell.call('%s reset --hard %s' % (GIT, commit), git_dir)


def get_hash(git_dir, commit):
    '''
    Get a commit hash from a valid commit.
    Can be used to check if a commit exists

    @param git_dir: path of the git repository
    @type git_dir: str
    @param commit: the commit to log
    @type commit: str
    '''
    return shell.check_call('%s show -s --pretty=%%H %s' %
                            (GIT, commit), git_dir)


def local_checkout(git_dir, local_git_dir, commit):
    '''
    Clone a repository for a given commit in a different location

    @param git_dir: destination path of the git repository
    @type git_dir: str
    @param local_git_dir: path of the source git repository
    @type local_git_dir: str
    @param commit: the commit to checkout
    @type commit: false
    '''
    # reset to a commit in case it's the first checkout and the masterbranch is
    # missing
    shell.call('%s reset --hard %s' % (GIT, commit), local_git_dir)
    shell.call('%s branch build' % GIT, local_git_dir, fail=False)
    shell.call('%s checkout build' % GIT, local_git_dir)
    shell.call('%s reset --hard %s' % (GIT, commit), local_git_dir)
    return shell.call('%s clone %s -b build .' % (GIT, local_git_dir), git_dir)


def add_remote(git_dir, name, url):
    '''
    Add a remote to a git repository

    @param git_dir: destination path of the git repository
    @type git_dir: str
    @param name: name of the remote
    @type name: str
    @param url: url of the remote
    @type url: str
    '''
    shell.call('%s remote add -f %s %s' % (GIT, name, url), git_dir,
               fail=False)
