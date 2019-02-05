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
from functools import reduce
from pathlib import Path

from cerbero.enums import LicenseDescription
from cerbero.build import build, source
from cerbero.build.filesprovider import FilesProvider
from cerbero.config import Platform
from cerbero.errors import FatalError
from cerbero.ide.vs.genlib import GenLib, GenGnuLib
from cerbero.tools.osxuniversalgenerator import OSXUniversalGenerator
from cerbero.tools.osxrelocator import OSXRelocator
from cerbero.utils import N_, _
from cerbero.utils import shell, add_system_libs
from cerbero.utils import messages as m
from cerbero.tools.libtool import LibtoolLibrary

LICENSE_INFO_FILENAME = 'README-LICENSE-INFO.txt'

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
    RELOCATE_OSX_LIBRARIES = (N_('Relocate OSX libraries'), 'relocate_osx_libraries')

    def __new__(klass):
        return [BuildSteps.FETCH, BuildSteps.EXTRACT,
                BuildSteps.CONFIGURE, BuildSteps.COMPILE, BuildSteps.INSTALL,
                BuildSteps.POST_INSTALL]


class Recipe(FilesProvider, metaclass=MetaRecipe):
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

    # Licenses are declared as an array of License.enums or dicts of the type:
    #
    #   {License.enum: ['path-to-license-file-in-source-tree']}
    #
    # If the array element is License.enum or if in a dict, the value of
    # a License.enum key is None, the license does not have any specific
    # copyright or author info, and the copy inside data/licenses will be
    # used instead.
    #
    # This format is chosen to allow you to declare when a recipe is licensed
    # under multiple licenses in various combinations. For example:
    #
    #  (LICENSE1 && LICENSE2) || (LICENSE3) || (LICENSE4 && LICENSE5)
    #
    # can be represented as
    #
    #  licenses = [
    #   License.L1,
    #   {License.L2: ['l2.txt'], License.L3: ['l3.txt', 'other-info.txt']},
    #   {License.L4: None, License.Misc: ['some-info.txt']},
    #  ]
    #
    # Reasons for choosing this format:
    # * Many BSD projects are licensed under multiple BSD licenses, which must be
    #   followed together.
    # * Some other projects are licensed under multiple licenses, such as MPL
    #   || LGPL, and so on.
    # * Some projects have miscellaneous files with important copyright of
    #   licensing information
    licenses = []

    # Other recipe metadata
    name = None
    version = None
    package_name = None
    sources = None
    stype = source.SourceType.GIT_TARBALL
    btype = build.BuildType.AUTOTOOLS
    deps = None
    platform_deps = None
    runtime_dep = False

    # Internal properties
    force = False
    _default_steps = BuildSteps()
    _licenses_disclaimer = '''\
DISCLAIMER: THIS LICENSING INFORMATION IS PROVIDED ON A BEST-EFFORT BASIS
AND IS NOT MEANT TO BE LEGAL ADVICE. PLEASE TALK TO A LAWYER FOR ADVICE ON
SOFTWARE LICENSE COMPLIANCE.\n\n'''
    _licenses_terms = 'The {} in this package may be used under the terms of license file(s):\n\n'

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
        self.platform_deps = self.platform_deps or {}
        self._steps = self._default_steps[:]
        if self.config.target_platform == Platform.WINDOWS:
            self._steps.append(BuildSteps.GEN_LIBFILES)
        if self.config.target_platform == Platform.DARWIN:
            self._steps.append(BuildSteps.RELOCATE_OSX_LIBRARIES)
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

    def _get_arch_prefix(self):
        if self.config.cross_universal_type() == 'flat':
            return os.path.join(self.config.prefix, self.config.target_arch)
        return self.config.prefix

    def _get_unique_ordered(self, elems):
        used = []
        return [x for x in elems if x not in used and (used.append(x) or True)]

    def _get_la_deps_from_pc (self, laname, pcname, env):
        ret = shell.check_call('pkg-config --libs-only-l --static ' + pcname, env=env)
        # Don't add the library itself to the list of dependencies
        return ['lib' + lib[2:] for lib in self._get_unique_ordered(ret.split()) if lib[2:] != laname[3:]]

    def _resolve_deps(self, deps):
        resolved = []
        unresolved = []

        def resolve_step(node):
            unresolved.append(node.name)
            for dep in node.deps:
                if dep not in resolved:
                    if dep in unresolved:
                        raise RuntimeError('Circular reference detected: %s -> %s' % (node.name, dep))
                    possible_nodes = [d for d in deps if d.name == dep]
                    if len(possible_nodes) > 0:
                        resolve_step(possible_nodes[0])
            if node.name not in resolved:
                resolved.append(node.name)
            unresolved.remove(node.name)

        for node in deps:
            resolve_step(node)

        ret = []
        for dep in resolved:
            possible = [d for d in deps if d.name == dep]
            if len(dep) > 0:
                ret.append(possible[0])

        return ret

    def generate_gst_la_files(self):
        '''
        Generate .la files for all libraries and plugins packaged by this Meson
        recipe using the pkg-config files installed by our Meson build files.
        '''
        class GeneratedLA(object):
            name = None
            major = None
            minor = None
            micro = None
            libdir = None
            platform = None
            deps = None

            def __init__(self, la_name, major, minor, micro, libdir, deps=None):
                if not deps:
                    deps = []

                self.name = la_name
                self.major = major
                self.minor = minor
                self.micro = micro
                self.libdir = libdir
                self.deps = deps

            def __eq__(self, other):
                if not isinstance(other, GeneratedLA):
                    return False
                return self.name == other.name and self.libdir == other.libdir

            def __str__(self):
                return "<GeneratedLA:%s@%s version:%s.%s.%s in \'%s\' deps: [%s]" % (
                        str(self.name), str(hex(id(self))), str(self.major),
                        str(self.minor), str(self.micro), str(self.libdir),
                        ", ".join(self.deps))

        lib_to_pcname_map = {
            'gstadaptivedemux-1.0' : None,
            'gstbadaudio-1.0' : 'gstreamer-bad-audio-1.0',
            'gstbasecamerabinsrc-1.0' : None,
            'gstisoff-1.0' : None,
            'gstphotography-1.0' : None,
            'gsturidownloader-1.0' : None,
            'gstrtspserver-1.0' : 'gstreamer-rtsp-server-1.0',
            'gstvalidate-1.0' : 'gst-validate-1.0',
            'ges-1.0' : 'gst-editing-services-1.0',
        }
        generated_libs = []

        pluginpcdir = os.path.join(self.config.libdir, 'gstreamer-1.0', 'pkgconfig')
        env = os.environ.copy()
        env['PKG_CONFIG_LIBDIR'] += os.pathsep + pluginpcdir
        if self.use_system_libs:
            add_system_libs(self.config, env)

        # retrieve the list of files we need to generate
        for f in self.devel_files_list():
            if not f.endswith('.a') or not f.startswith('lib/'):
                continue
            if f.startswith('lib/gstreamer-1.0/'):
                libtype = 'plugin'
            else:
                libtype = 'library'
            fpath = os.path.join(self._get_arch_prefix(), f)
            if not os.path.isfile(fpath):
                arch = self.config.target_arch
                m.warning('{} {} {!r} not found'.format(arch, libtype, fpath))
                continue
            pcname = os.path.basename(f)[3:-6 if f.endswith('.dll.a') else -2]
            la_path = os.path.splitext(f)[0]
            ladir, laname = os.path.split(la_path)
            ladir = os.path.join(self._get_arch_prefix(), ladir)

            major = minor = micro = None
            if libtype == 'library':
                if pcname in lib_to_pcname_map:
                    pcname = lib_to_pcname_map[pcname]
                elif not pcname.startswith('gstreamer-'):
                    pcname = pcname.replace('gst', 'gstreamer-')

                # some libs don't have .pc files
                if not pcname:
                    continue

                minor, micro = (map(int, self.version.split('.')[1:3]))
                minor = minor * 100 + micro
                major = micro = 0

            pcpath = os.path.join(ladir, 'pkgconfig', pcname + '.pc')
            if not os.path.isfile(pcpath):
                arch = self.config.target_arch
                # XXX: make this fatal?
                m.warning('{} pkg-config file {!r} not found'.format(arch, pcpath))
                continue

            deps = self._get_la_deps_from_pc(laname, pcname, env)

            generated = GeneratedLA(laname, major, minor, micro, ladir, deps)
            generated_libs.append(generated)

        # resolve dependencies so that dependant libs are generated
        # before libraries/plugins using them
        for lib in self._resolve_deps(generated_libs):
            dep_libs = []
            for dep in lib.deps:
                # check if the lib is available as an .la and use that instead
                # of -l arguments
                lafile = os.path.join(self.config.libdir, dep + '.la')
                if os.path.isfile(lafile):
                    # LibtoolLibrary prepends the libdir and appends '.la' for us
                    dep_libs.append(lafile[:-3])
                else:
                    if dep.startswith('lib'):
                        dep = dep[3:]
                    dep_libs.append('-l' + dep)

            LibtoolLibrary(lib.name, lib.major, lib.minor, lib.micro, lib.libdir,
                      self.config.target_platform, deps=dep_libs).save()

    def relocate_osx_libraries(self):
        '''
        Make OSX libraries relocatable
        '''
        relocator = OSXRelocator(self.config.prefix, self.config.prefix, True)
        def get_real_path(fp):
            return os.path.realpath(os.path.join(self.config.prefix, fp))

        def file_is_relocatable(fp):
            return fp.split('/')[0] in ['lib', 'bin', 'libexec'] and \
                    os.path.splitext(fp)[1] not in ['.a', '.pc', '.la']

        # Only relocate files are that are potentially relocatable and
        # remove duplicates by symbolic links so we relocate libs only
        # once.
        for f in set([get_real_path(x) for x in self.files_list() \
                if file_is_relocatable(x)]):
            relocator.relocate_file(f)

    def _install_srcdir_license(self, lfiles, install_dir):
        '''
        Copy specific licenses from the project's source dir. Used for BSD,
        MIT, and other licenses which have copyright headers that are important
        to fulfilling the licensing terms.
        '''
        files = []
        for f in lfiles:
            fname = f.replace('/', '_')
            if fname == LICENSE_INFO_FILENAME:
                raise RuntimeError('{}.recipe: license file collision: {!r}'
                                   .format(self.name, LICENSE_INFO_FILENAME))
            dest = str(install_dir / fname)
            src = os.path.join(self.build_dir, f)
            shutil.copyfile(src, dest)
            files.append(fname)
        return files

    def _install_datadir_license(self, lobj, install_dir):
        '''
        Copy generic licenses from the cerbero licenses datadir.
        '''
        if lobj.acronym.startswith(('BSD', 'MIT')):
            raise RuntimeError('{}.recipe: must specify the license file for BSD and MIT licenses'
                               .format(self.name))
        fname = lobj.acronym + '.txt'
        dest = str(install_dir / fname)
        src = os.path.join(self.config.data_dir, 'licenses', lobj.acronym + '.txt')
        shutil.copyfile(src, dest)
        return [fname]

    def _write_license_readme(self, licenses_files, install_dir, applies_to):
        with (install_dir / LICENSE_INFO_FILENAME).open('w') as f:
            f.write(self._licenses_disclaimer)
            f.write(self._licenses_terms.format(applies_to))
            f.write('\n(OR)\n'.join([' (AND) '.join(lfiles) for lfiles in licenses_files]))

    def _install_licenses(self, install_dir, licenses):
        if not install_dir.is_dir():
            install_dir.mkdir(parents=True)
        licenses_files = []
        for each in licenses:
            lfiles = []
            if isinstance(each, dict):
                for lobj, value in each.items():
                    assert(isinstance(lobj, LicenseDescription))
                    if value is None:
                        lfiles += self._install_datadir_license(lobj, install_dir)
                    else:
                        assert(isinstance(value, list))
                        lfiles += self._install_srcdir_license(value, install_dir)
            elif isinstance(each, LicenseDescription):
                lfiles = self._install_datadir_license(each, install_dir)
            else:
                raise AssertionError('{}.recipe: unknown license array element type'.format(self.name))
            licenses_files.append(lfiles)
        return licenses_files

    def install_licenses(self):
        '''
        NOTE: This list of licenses is only indicative and is not guaranteed to
        match the actual licenses and copyright headers you need to display in
        your application or adhere to during license compliance.
        '''
        install_dir = Path(self.config.prefix) / 'share' / 'licenses' / self.name
        # Install licenses for libraries
        if isinstance(self.licenses, list):
            licenses_files = self._install_licenses(install_dir, self.licenses)
        else:
            raise AssertionError('{}.recipe: unknown licenses type'.format(self.name))
        # Only write license info for binaries if different from libraries
        if not hasattr(self, 'licenses_bins'):
            self._write_license_readme(licenses_files, install_dir, 'libraries and binaries')
            return
        else:
            self._write_license_readme(licenses_files, install_dir, 'libraries')
        # Install licenses for binaries
        install_dir = install_dir / 'bins'
        if isinstance(self.licenses_bins, list):
            licenses_files = self._install_licenses(install_dir, self.licenses_bins)
            self._write_license_readme(licenses_files, install_dir, 'binaries')
        elif self.licenses_bins is not None:
            raise AssertionError('{}.recipe: unknown licenses_bins type'.format(self.name))

    def post_install(self):
        '''
        Runs post installation steps
        '''
        if self.btype == build.BuildType.MESON and self.name.startswith('gst'):
            self.generate_gst_la_files()
        self.install_licenses()

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

    @staticmethod
    def flatten_licenses(licenses):
        '''
        self.licenses* can be arrays of LicenseDescription or arrays of dicts
        with LicenseDescription as keys. Flatten that to just get a list of
        licenses.
        '''
        flattened = []
        for each in licenses:
            if isinstance(each, LicenseDescription):
                flattened.append(each)
            elif isinstance(each, dict):
                flattened += each.keys()
            else:
                raise AssertionError('Unknown license array element: {!r}'.format(each))
        return flattened

    def list_licenses_by_categories(self, categories):
        licenses = {}
        for c in categories:
            if c in licenses:
                raise Exception('multiple licenses for the same category %s '
                                'defined' % c)

            if not c:
                licenses[None] = self.flatten_licenses(self.licenses)
                continue

            attr = 'licenses_' + c
            platform_attr = 'platform_licenses_' + c
            if hasattr(self, attr):
                licenses[c] = self.flatten_licenses(getattr(self, attr))
            elif hasattr(self, platform_attr):
                l = getattr(self, platform_attr)
                licenses[c] = self.flatten_licenses(l.get(self.platform, []))
            else:
                licenses[c] = self.flatten_licenses(self.licenses)
        return licenses

    def gen_library_file(self, output_dir=None):
        '''
        Generates library files (.lib or .dll.a) for the DLLs provided by this recipe
        '''
        if output_dir is None:
            output_dir = os.path.join(self.config.prefix,
                                      'lib' + self.config.lib_suffix)
        # Generate a GNU import library or an MSVC import library
        genlib = GenGnuLib() if self.using_msvc() else GenLib()
        # Generate the .dll.a or .lib file as needed
        for (libname, dllpaths) in list(self.libraries().items()):
            if len(dllpaths) > 1:
                m.warning("BUG: Found multiple DLLs for libname {!r}:\n{}".format(libname, '\n'.join(dllpaths)))
                continue
            if len(dllpaths) == 0:
                m.warning("Could not create import library for {!r}, no matching DLLs found".format(libname))
                continue
            try:
                implib = genlib.create(libname,
                    os.path.join(self.config.prefix, dllpaths[0]),
                    self.config.platform, self.config.target_arch,
                    output_dir)
                logging.debug('Created %s' % implib)
            except FatalError as e:
                m.warning("Could not create {!r}: {}".format(genlib.filename, e.msg))

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

    def get_checksum(self):
        '''
        Returns the current checksum of the recipe file and other files
        it depends on, like patches.
        This checksum is used in the cache to determine if a
        recipe changed in the last build

        @return: a checksum of the recipe file and its dependencies
        @rtype: str
        '''
        return shell.files_checksum(self._get_files_dependencies())

    def get_mtime(self):
        '''
        Returns the recipe last modification time, including the dependent
        files

        @return: last modification time
        @rtype: str
        '''
        return  max(map(os.path.getmtime, self._get_files_dependencies()))

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


class UniversalRecipe(object, metaclass=MetaUniversalRecipe):
    '''
    Stores similar recipe objects that are going to be built together

    Useful for the universal architecture, where the same recipe needs
    to be built for different architectures before being merged. For the
    other targets, it will likely be a unitary group
    '''

    def __init__(self, config):
        self._config = config
        self._recipes = {}
        self._proxy_recipe = None

    def __str__(self):
        if list(self._recipes.values()):
            return str(list(self._recipes.values())[0])
        return super(UniversalRecipe, self).__str__()

    def add_recipe(self, recipe):
        '''
        Adds a new recipe to the group
        '''
        if self._proxy_recipe is None:
            self._proxy_recipe = recipe
        else:
            for attr in ('name', 'deps', 'platform_deps'):
                if getattr(recipe, attr) != getattr(self._proxy_recipe, attr):
                    raise FatalError(_("Recipes must have the same " + attr))
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
            arch, recipe = list(self._recipes.items())[0]
            # No, really, let's not download a million times...
            stepfunc = getattr(recipe, step)
            try:
                stepfunc()
            except FatalError as e:
                e.arch = arch
                raise e
            return

        for arch, recipe in self._recipes.items():
            config = self._config.arch_config[arch]
            config.do_setup_env()
            stepfunc = getattr(recipe, step)

            # Call the step function
            try:
                stepfunc()
            except FatalError as e:
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
        for arch, recipe in self._recipes.items():
            # change the prefix temporarly to the arch prefix where files are
            # actually installed
            recipe.config.prefix = os.path.join(self.config.prefix, arch)
            arch_inputs[arch] = set(recipe.files_list())
            recipe.config.prefix = self._config.prefix

        # merge the common files
        inputs = reduce(lambda x, y: x & y, arch_inputs.values())
        output = self._config.prefix
        generator = OSXUniversalGenerator(output)
        dirs = [os.path.join(self._config.prefix, arch) for arch in self._recipes.keys()]
        generator.merge_files(inputs, dirs)

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
            stepfunc = getattr(list(self._recipes.values())[0], step)
            stepfunc()
            return

        # For the universal build we need to configure both architectures with
        # with the same final prefix, but we want to install each architecture
        # on a different path (eg: /path/to/prefix/x86).

        archs_prefix = list(self._recipes.keys())

        for arch, recipe in self._recipes.items():
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
