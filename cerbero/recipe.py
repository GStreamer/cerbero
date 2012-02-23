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

from cerbero import build
from cerbero import source
from cerbero.utils import  N_


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
    '''

    name = None
    version = None
    package_name = None
    sources = None
    stype = source.SourceType.LOCAL_TARBALL
    btype = build.BuildType.AUTOTOOLS
    deps = list()
    _mtime = 0
    _steps = [(N_('Fetch'), 'fetch'), (N_('Extract'), 'extract'),
              (N_('Configure'), 'configure'), (N_('Compile'), 'compile'),
              (N_('Install'), 'install'),
              (N_('Post Install'), 'post_install')]

    def __init__(self, config):
        self.config = config
        if self.package_name is None:
            self.package_name = "%s-%s" % (self.name, self.version)
        self.source = source.get_handler(self, config)
        self.build = build.get_handler(self, config)

    def prepare (self):
        '''
        Can be overriden by subclasess to modify the recipe in function of
        the configuration, like modifying steps for a given platform
        '''
        pass

    def fetch (self):
        '''
        Fetch the sources
        '''
        self.source.fetch()

    def extract (self):
        '''
        Extracts the sources
        '''
        self.source.extract()

    def configure (self):
        '''
        Configures the module
        '''
        self.build.do_configure()

    def compile (self):
        '''
        Compiles the module
        '''
        self.build.do_make()

    def install (self):
        '''
        Installs the module
        '''
        self.build.do_install()

    def post_install (self):
        '''
        Runs a custom post-install step
        '''
        pass

    def set_mtime (self, mtime):
        self._mtime = mtime

    def _remove_steps (self, steps):
        self._steps = [x for x in self._steps if x[1] not in steps]
