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
import shutil
import tempfile
import time

from cerbero.build import build, source
from cerbero.build.filesprovider import FilesProvider
from cerbero.config import Platform
from cerbero.errors import FatalError
from cerbero.ide.vs.genlib import GenLib
from cerbero.tools.osxuniversalgenerator import OSXUniversalGenerator
from cerbero.utils import N_, _
from cerbero.utils import shell
from cerbero.utils import messages as m


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
    POST_INSTALL = (N_('Post Install'), 'post_install')

    # Not added by default
    CHECK = (N_('Check'), 'check')
    GEN_LIBFILES = (N_('Gen Library File'), 'gen_library_file')
    MERGE = (N_('Merge universal binaries'), 'merge')

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
    @cvar runtime_dep: runtime dep common to all recipes
    @type runtime_dep: bool
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
    runtime_dep = False
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
        self._steps = self._default_steps[:]
        if self.config.target_platform == Platform.WINDOWS:
            self._steps.append(BuildSteps.GEN_LIBFILES)
        FilesProvider.__init__(self, config)
        try:
            self.stype.__init__(self)
            self.btype.__init__(self)
        except TypeError:
            # should only work with subclasses that really have Build and
            # Source in bases
            pass

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<Recipe %s>" % self.name

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

    def built_version(self):
        '''
        Gets the current built version of the recipe.
        Sources can override it to provide extended info in the version
        such as the commit hash for recipes using git and building against
        master: eg (1.2.0~git+2345435)
        '''
        if hasattr(self.stype, 'built_version'):
            return self.stype.built_version(self)
        return self.version

    def list_deps(self):
        '''
        List all dependencies including conditional dependencies
        '''
        deps = []
        deps.extend(self.deps)
        if self.config.target_platform in self.platform_deps:
            deps.extend(self.platform_deps[self.config.target_platform])
        if self.config.variants.gi and self.use_gobject_introspection():
            if self.name != 'gobject-introspection':
                deps.append('gobject-introspection')
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
        if output_dir is None:
            output_dir = os.path.join(self.config.prefix,
                                      'lib' + self.config.lib_suffix)
        genlib = GenLib()
        for (libname, dllpaths) in self.libraries().items():
            if len(dllpaths) > 1:
                m.warning("BUG: Found multiple DLLs for libname {}:\n{}".format(libname, '\n'.join(dllpaths)))
                continue
            if len(dllpaths) == 0:
                m.warning("Could not create {}.lib, no matching DLLs found".format(libname))
                continue
            try:
                implib = genlib.create(libname,
                    os.path.join(self.config.prefix, dllpaths[0]),
                    self.config.target_arch,
                    output_dir)
                logging.debug('Created %s' % implib)
            except:
                m.warning("Could not create {}.lib, gendef might be missing".format(libname))

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

    def get_for_arch (self, arch, name):
        return getattr (self, name)


class MetaUniversalRecipe(type):
    '''
    Wraps all the build steps for the universal recipe to be called for each
    one of the child recipes.
    '''

    def __init__(cls, name, bases, ns):
        step_func = ns.get('_do_step')
        for _, step in BuildSteps():
            setattr(cls, step, lambda self, name=step: step_func(self, name))


class UniversalRecipe(object):
    '''
    Stores similar recipe objects that are going to be built together

    Useful for the universal architecture, where the same recipe needs
    to be built for different architectures before being merged. For the
    other targets, it will likely be a unitary group
    '''

    __metaclass__ = MetaUniversalRecipe

    def __init__(self, config):
        self._config = config
        self._recipes = {}
        self._proxy_recipe = None

    def __str__(self):
        if self._recipes.values():
            return str(self._recipes.values()[0])
        return super(UniversalRecipe, self).__str__()

    def add_recipe(self, recipe):
        '''
        Adds a new recipe to the group
        '''
        if self._proxy_recipe is None:
            self._proxy_recipe = recipe
        else:
            if recipe.name != self._proxy_recipe.name:
                raise FatalError(_("Recipes must have the same name"))
        self._recipes[recipe.config.target_arch] = recipe

    def is_empty(self):
        return len(self._recipes) == 0

    @property
    def steps(self):
        if self.is_empty():
            return []
        return self._proxy_recipe.steps[:]

    def __getattr__(self, name):
        if not self._proxy_recipe:
            raise AttributeError(_("Attribute %s was not found in the "
                "Universal recipe, which is empty. You might need to add a "
                "recipe first."))
        return getattr(self._proxy_recipe, name)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name not in ['_config', '_recipes', '_proxy_recipe']:
            for o in self._recipes.values():
                setattr(o, name, value)

    def get_for_arch (self, arch, name):
        if arch:
            return getattr (self._recipes[arch], name)
        else:
            return getattr (self, name)

    def _do_step(self, step):
        if step in BuildSteps.FETCH:
            # No, really, let's not download a million times...
            stepfunc = getattr(self._recipes.values()[0], step)
            try:
                stepfunc()
            except FatalError, e:
                e.arch = arch
                raise e
            return

        for arch, recipe in self._recipes.iteritems():
            config = self._config.arch_config[arch]
            config.do_setup_env()
            stepfunc = getattr(recipe, step)

            # Call the step function
            try:
                stepfunc()
            except FatalError, e:
                e.arch = arch
                raise e


class UniversalFlatRecipe(UniversalRecipe):
    '''
    Unversal recipe for iOS and OS X creating flat libraries
    in the target prefix instead of subdirs for each architecture
    '''

    def __init__(self, config):
        UniversalRecipe.__init__(self, config)

    @property
    def steps(self):
        if self.is_empty():
            return []
        return self._proxy_recipe.steps[:] + [BuildSteps.MERGE]

    def merge(self):
        arch_inputs = {}
        for arch, recipe in self._recipes.iteritems():
            # change the prefix temporarly to the arch prefix where files are
            # actually installed
            recipe.config.prefix = os.path.join(self.config.prefix, arch)
            arch_inputs[arch] = set(recipe.files_list())
            recipe.config.prefix = self._config.prefix

        # merge the common files
        inputs = reduce(lambda x, y: x & y, arch_inputs.values())
        output = self._config.prefix
        generator = OSXUniversalGenerator(output)
        generator.merge_files(list(inputs),
                [os.path.join(self._config.prefix, arch) for arch in
                 self._recipes.keys()])

        # merge the architecture specific files
        for arch in self._recipes.keys():
            ainputs = list(inputs ^ arch_inputs[arch])
            output = self._config.prefix
            generator = OSXUniversalGenerator(output)
            generator.merge_files(ainputs,
                    [os.path.join(self._config.prefix, arch)])

    def _do_step(self, step):
        if step in BuildSteps.FETCH:
            # No, really, let's not download a million times...
            stepfunc = getattr(self._recipes.values()[0], step)
            stepfunc()
            return

        # For the universal build we need to configure both architectures with
        # with the same final prefix, but we want to install each architecture
        # on a different path (eg: /path/to/prefix/x86).

        archs_prefix = self._recipes.keys()

        for arch, recipe in self._recipes.iteritems():
            config = self._config.arch_config[arch]
            config.do_setup_env()
            stepfunc = getattr(recipe, step)

            # Create a stamp file to list installed files based on the
            # modification time of this file
            if step in [BuildSteps.INSTALL[1], BuildSteps.POST_INSTALL[1]]:
                time.sleep(2) #wait 2 seconds to make sure new files get the
                              #proper time difference, this fixes an issue of
                              #the next recipe to be built listing the previous
                              #recipe files as their own
                tmp = tempfile.NamedTemporaryFile()
                # the modification time resolution depends on the filesystem,
                # where FAT32 has a resolution of 2 seconds and ext4 1 second
                t = time.time() - 2
                os.utime(tmp.name, (t, t))

            # Call the step function
            stepfunc()

            # Move installed files to the architecture prefix
            if step in [BuildSteps.INSTALL[1], BuildSteps.POST_INSTALL[1]]:
                installed_files = shell.find_newer_files(self._config.prefix,
                                                         tmp.name, True)
                tmp.close()
                for f in installed_files:

                    def not_in_prefix(src):
                        for p in archs_prefix + ['Libraries']:
                            if src.startswith(p):
                                return True
                        return False

                    # skip files that are installed in the arch prefix
                    if not_in_prefix(f):
                        continue
                    src = os.path.join(self._config.prefix, f)

                    dest = os.path.join(self._config.prefix,
                                        recipe.config.target_arch, f)
                    if not os.path.exists(os.path.dirname(dest)):
                        os.makedirs(os.path.dirname(dest))
                    shutil.move(src, dest)
