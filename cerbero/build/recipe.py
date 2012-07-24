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
import logging

from cerbero.build import build, source
from cerbero.build.filesprovider import FilesProvider
from cerbero.config import Platform
from cerbero.ide.vs.genlib import GenLib
from cerbero.utils import N_


class MetaRecipe(type):
    ''' This metaclass modifies the base classes of a Receipt, adding 2 new
    base classes based on the class attributes 'stype' and 'btype'.

    class NewReceipt(Receipt):
        btype = Class1    ------>  class NewReceipt(Receipt, Class1, Class2)
        stype = Class2
    '''

    def __new__(cls, name, bases, dct):
        clsname = '%s.%s' % (dct['__module__'], name)
        recipeclsname = '%s.%s' % (cls.__module__, 'Recipe')
        # only modify it for Receipt's subclasses
        if clsname != recipeclsname and name == 'Recipe':
            # get the default build and source classes from Receipt
            # Receipt(DefaultSourceType, DefaultBaseType)
            basedict = {'btype': bases[0].btype, 'stype': bases[0].stype}
            # if this class define stype or btype, override the default one
            # Receipt(OverridenSourceType, OverridenBaseType)
            for base in ['stype', 'btype']:
                if base in dct:
                    basedict[base] = dct[base]
            # finally add this classes the Receipt bases
            # Receipt(BaseClass, OverridenSourceType, OverridenBaseType)
            bases = bases + tuple(basedict.values())
        return type.__new__(cls, name, bases, dct)


class BuildSteps(object):
    '''
    Enumeration factory for build steps
    '''

    FETCH = (N_('Fetch'), 'fetch')
    EXTRACT = (N_('Extract'), 'extract')
    CONFIGURE = (N_('Configure'), 'configure')
    COMPILE = (N_('Compile'), 'compile')
    INSTALL = (N_('Install'), 'install')
    CHECK = (N_('Check'), 'check')  # Not added by default
    POST_INSTALL = (N_('Post Install'), 'post_install')
    GEN_LIBFILES = (N_('Gen Library File'), 'gen_library_file')

    def __new__(klass):
        return [BuildSteps.FETCH, BuildSteps.EXTRACT,
                BuildSteps.CONFIGURE, BuildSteps.COMPILE, BuildSteps.INSTALL,
                BuildSteps.POST_INSTALL]


class Recipe(FilesProvider):
    '''
    Base class for recipes.
    A Recipe describes a module and the way it's built.

    @cvar name: name of the module
    @type name: str
    @cvar licenses: recipe licenses
    @type licenses: Licenses
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
    licenses = []
    version = None
    package_name = None
    sources = None
    stype = source.SourceType.GIT_TARBALL
    btype = build.BuildType.AUTOTOOLS
    deps = list()
    platform_deps = {}
    force = False
    _default_steps = BuildSteps()

    def __init__(self, config):
        self.config = config
        if self.package_name is None:
            self.package_name = "%s-%s" % (self.name, self.version)
        if not hasattr(self, 'repo_dir'):
            self.repo_dir = os.path.join(self.config.local_sources,
                    self.package_name)
        self.repo_dir = os.path.abspath(self.repo_dir)
        self.build_dir = os.path.join(self.config.sources, self.package_name)
        self.build_dir = os.path.abspath(self.build_dir)
        self.deps = self.deps or []
        self.platform_deps = self.platform_deps or []
        FilesProvider.__init__(self, config)
        try:
            self.stype.__init__(self)
            self.btype.__init__(self)
        except TypeError:
            # should only work with subclasses that really have Build and
            # Source in bases
            pass

        self._steps = self._default_steps[:]
        if self.config.target_platform == Platform.WINDOWS:
            self._steps.append(BuildSteps.GEN_LIBFILES)

    def __str__(self):
        return self.name

    def prepare(self):
        '''
        Can be overriden by subclasess to modify the recipe in function of
        the configuration, like modifying steps for a given platform
        '''
        pass

    def post_install(self):
        '''
        Runs a post installation steps
        '''
        pass

    def list_deps(self):
        '''
        List all dependencies including conditional dependencies
        '''
        deps = []
        deps.extend(self.deps)
        if self.config.target_platform in self.platform_deps:
            deps.extend(self.platform_deps[self.config.target_platform])
        return deps

    def list_licenses_by_categories(self, categories):
        licenses = {}
        for c in categories:
            if c in licenses:
                raise Exception('multiple licenses for the same category %s '
                                'defined' % c)

            if not c:
                licenses[None] = self.licenses
                continue

            attr = 'licenses_' + c
            platform_attr = 'platform_licenses_' + c
            if hasattr(self, attr):
                licenses[c] = getattr(self, attr)
            elif hasattr(self, platform_attr):
                l = getattr(self, platform_attr)
                licenses[c] = l.get(self.platform, [])
            else:
                licenses[c] = self.licenses
        return licenses

    def gen_library_file(self, output_dir=None):
        '''
        Generates library files (.lib) for the dll's provided by this recipe
        '''
        genlib = GenLib()
        for dllpath in self.libraries():
            implib = genlib.create(os.path.join(self.config.prefix, dllpath),
                    os.path.join(self.config.prefix, 'lib'))
            logging.debug('Created %s' % implib)

    def recipe_dir(self):
        '''
        Gets the directory path where this recipe is stored

        @return: directory path
        @rtype: str
        '''
        return os.path.dirname(self.__file__)

    def relative_path(self, path):
        '''
        Gets a path relative to the recipe's directory

        @return: absolute path relative to the pacakge's directory
        @rtype: str
        '''
        return os.path.abspath(os.path.join(self.recipe_dir(), path))

    @property
    def steps(self):
        return self._steps

    def _remove_steps(self, steps):
        self._steps = [x for x in self._steps if x not in steps]
