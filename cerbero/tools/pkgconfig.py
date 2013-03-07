#!/usr/bin/env python
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


class PkgConfigWritter(object):

    VARIABLES_TPL = '''\
prefix=%(prefix)s
exec_prefix=${prefix}
libdir=${prefix}/%(rel_libdir)s
includedir=${prefix}/%(rel_incldir)s
datarootdir=${prefix}/%(rel_sharedir)s
datadir=${datarootdir}
'''
    BODY_TPL = '''\

Name: %(name)s
Description: %(desc)s
Version: %(version)s
Requires: %(req)s
Requires.private: %(req_priv)s
Libs: %(libs)s
Libs.private: %(libs_priv)s
Cflags: %(cflags)s
'''

    rel_libdir = 'lib'
    rel_incldir = 'include'
    rel_sharedir = 'share'

    def __init__(self, name, desc, version, req, libs, cflags, prefix):
        self.name = name
        self.desc = desc
        self.version = version
        self.req = req
        self.libs = libs
        self.cflags = cflags
        self.prefix = prefix
        self.libs_priv = ''
        self.req_priv = ''

    def save(self, name, pkgconfigdir):
        variables = self._get_variables()
        body = self._get_body()
        with open(os.path.join(pkgconfigdir, '%s.pc' % name), 'w+') as f:
            f.write(variables)
            f.write(body)

    def _get_variables(self):
        return self.VARIABLES_TPL % {
            'prefix': self.prefix,
            'rel_libdir': self.rel_libdir,
            'rel_incldir': self.rel_incldir,
            'rel_sharedir': self.rel_sharedir}

    def _get_body(self):
        return self.BODY_TPL % {
            'name': self.name,
            'desc': self.desc,
            'version': self.version,
            'req': self.req,
            'req_priv': self.req_priv,
            'libs': self.libs,
            'libs_priv': self.libs_priv,
            'cflags': self.cflags}
