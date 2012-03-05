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

from cerbero import build
from cerbero import source
from cerbero.utils import  N_


class MetaRecipe(type):

    def __new__(cls, name, bases, dct):
        if bases[0] != object :
            basedict = {'btype': None, 'stype': None}
            basedict['stype'] = bases[0].stype
            basedict['btype'] = bases[0].btype
            for base in ['stype', 'btype']:
                if dct.get(base):
                    basedict[base] = dct[base]
            bases = bases + tuple(basedict.values())
        return type.__new__(cls, name, bases, dct)


class Recipe(object):
    '''
    Base class for recipes.
    A Recipe describes a module and the way it's built.

    @cvar name: name of the module
    @type name: str
    @cvar version: version of the module
    @type version: str
    @cvar sources: url of the sources
    @type sources: str
    @cvar stype: type of sources
    @type stype: L{cerbero.source.SourceType}
    @cvar btype: build type
    @type btype: L{cerbero.build.BuildType}
    @cvar deps: module dependencies
    @type deps: list
    @cvar platform_deps: platform conditional depencies
    @type platform_deps: dict
    '''

    __metaclass__ = MetaRecipe

    name = None
    version = None
    package_name = None
    sources = None
    stype = source.SourceType.GIT_TARBALL
    btype = build.BuildType.AUTOTOOLS
    deps = list()
    platform_deps = {}
    force = False
    _steps = [(N_('Fetch'), 'fetch'), (N_('Extract'), 'extract'),
              (N_('Configure'), 'configure'), (N_('Compile'), 'compile'),
              (N_('Install'), 'install'),
              (N_('Post Install'), 'post_install')]
              # Not adding check as it's not automaticall done

    def __init__(self, config):
        self.config = config
        if self.package_name is None:
            self.package_name = "%s-%s" % (self.name, self.version)
        self.repo_dir = os.path.join(self.config.local_sources, self.package_name)
        self.repo_dir = os.path.abspath(self.repo_dir)
        self.build_dir = os.path.join(self.config.sources, self.package_name)
        self.build_dir = os.path.abspath(self.build_dir)
        self.stype.__init__(self)
        self.btype.__init__(self)

    def prepare(self):
        '''
        Can be overriden by subclasess to modify the recipe in function of
        the configuration, like modifying steps for a given platform
        '''
        pass

    def post_install (self):
        pass

    def list_deps(self):
        '''
        List all dependencies including conditional depencies
        '''
        deps = self.deps or []
        if self.config.target_platform in self.platform_deps:
            deps.append(self.platform_deps[self.config.target_platform])
        return deps

    def _remove_steps(self, steps):
        self._steps = [x for x in self._steps if x[1] not in steps]
