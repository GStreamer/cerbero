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


async def checkout(url, dest):
    '''
    Checkout a url to a given destination

    @param url: url to checkout
    @type url: string
    @param dest: path where to do the checkout
    @type url: string
    '''
    await shell.async_call(['svn', 'co', '--non-interactive', '--trust-server-cert', url, dest], cpu_bound=False)


async def update(repo, revision='HEAD'):
    '''
    Update a repositry to a given revision

    @param repo: repository path
    @type revision: str
    @param revision: the revision to checkout
    @type revision: str
    '''
    await shell.async_call(['svn', 'up', '--non-interactive', '--trust-server-cert', '-r', revision], repo, cpu_bound=False)


def checkout_file(url, out_path):
    '''
    Checkout a single file to out_path

    @param url: file URL
    @type url: str
    @param out_path: output path
    @type revision: str
    '''
    shell.call('svn export --force %s %s' % (url, out_path))


def revision(repo):
    '''
    Get the current revision of a repository with svnversion

    @param repo: the path to the repository
    @type  repo: str
    '''
    rev = shell.check_call('svnversion', repo).split('\n')[0]
    if rev[-1] == 'M':
        rev = rev[:-1]
    return rev
