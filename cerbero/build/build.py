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
import re
import glob
import copy
import shutil
import shlex
import sys
import subprocess
import asyncio
from pathlib import Path
from itertools import chain

from cerbero.enums import Platform, Architecture, Distro, LibraryType
from cerbero.errors import FatalError, InvalidRecipeError
from cerbero.utils import shell, add_system_libs, determine_num_of_cpus, determine_total_ram
from cerbero.utils import EnvValue, EnvValueSingle, EnvValueArg, EnvValueCmd, EnvValuePath
from cerbero.utils import messages as m


def get_optimization_from_config(config):
    if config.variants.optimization:
        if config.target_platform in (Platform.ANDROID, Platform.IOS):
            return 's'
        return '2'
    return '0'


def modify_environment(func):
    '''
    Decorator to modify the build environment

    When called recursively, it only modifies the environment once.
    '''
    def call(*args):
        self = args[0]
        try:
            self._modify_env()
            res = func(*args)
            return res
        finally:
            self._restore_env()

    async def async_call(*args):
        self = args[0]
        try:
            self._modify_env()
            res = await func(*args)
            return res
        finally:
            self._restore_env()

    if asyncio.iscoroutinefunction(func):
        ret = async_call
    else:
        ret = call

    ret.__name__ = func.__name__
    return ret


class EnvVarOp:
    '''
    An operation to be done on the values of a particular env var
    '''
    def __init__(self, op, var, vals, sep):
        self.execute = getattr(self, op)
        self.op = op
        self.var = var
        self.vals = vals
        self.sep = sep

    def set(self, env):
        if not self.vals:
            # An empty array means unset the env var
            if self.var in env:
                del env[self.var]
        else:
            if len(self.vals) == 1:
                env[self.var] = self.vals[0]
            else:
                env[self.var] = self.sep.join(self.vals)

    def append(self, env):
        # Avoid appending trailing space
        val = self.sep.join(self.vals)
        if not val:
            return
        if self.var not in env or not env[self.var]:
            env[self.var] = val
        else:
            env[self.var] += self.sep + val

    def prepend(self, env):
        # Avoid prepending a leading space
        val = self.sep.join(self.vals)
        if not val:
            return
        if self.var not in env or not env[self.var]:
            env[self.var] = val
        else:
            env[self.var] = val + self.sep + env[self.var]

    def remove(self, env):
        if self.var not in env:
            return
        # Split values taking in account spaces and quotes if the
        # separator is ' '
        if self.sep == ' ':
            old = shlex.split(env[self.var])
        else:
            old = env[self.var].split(self.sep)
        new = [x for x in old if x not in self.vals]
        if self.sep == ' ':
            env[self.var] = self.sep.join([shlex.quote(sub) for sub in new])
        else:
            env[self.var] = self.sep.join(new)

    def __repr__(self):
        vals = "None"
        if self.sep:
            vals = self.sep.join(self.vals)
        return "<EnvVarOp " + self.op + " " + self.var + " with " + vals + ">"


class ModifyEnvBase:
    '''
    Base class for build systems and recipes that require extra env variables
    '''

    use_system_libs = False
    # Use the outdated MSYS perl instead of the new perl downloaded in bootstrap
    use_msys_perl = False

    def __init__(self):
        # An array of #EnvVarOp operations that will be performed sequentially
        # on the env when @modify_environment is called.
        self._new_env = []
        # Set of env vars that will be modified
        self._env_vars = set()
        # Old environment to restore
        self._old_env = {}

        class ModifyEnvFuncWrapper(object):
            def __init__(this, target, method):
                this.target = target
                this.method = method

            def __call__(this, var, *vals, sep=' ', when='later'):
                if vals == (None,):
                    vals = None
                op = EnvVarOp(this.method, var, vals, sep)
                if when == 'later':
                    this.target.check_reentrancy()
                    this.target._env_vars.add(var)
                    this.target._new_env.append(op)
                elif when == 'now-with-restore':
                    this.target._save_env_var(var)
                    op.execute(this.target.env)
                elif when == 'now':
                    op.execute(this.target.env)
                else:
                    raise RuntimeError('Unknown when value: ' + when)

            def __repr__(this):
                return "<ModifyEnvFuncWrapper " + this.method + " for " + repr(this.target) + "  at " + str(hex(id(this))) + ">"

        for i in ('append', 'prepend', 'set', 'remove'):
            setattr(self, i + '_env', ModifyEnvFuncWrapper(self, i))

    def setup_buildtype_env_ops(self):
        buildtype_args = '-Wall '
        if self.config.variants.debug:
            buildtype_args += '-g '
        buildtype_args += '-O{} '.format(get_optimization_from_config(self.config))
        for var in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'OBJCFLAGS'):
            self.append_env(var, buildtype_args)

    def setup_toolchain_env_ops(self):
        if self.config.qt5_pkgconfigdir:
            self.append_env('PKG_CONFIG_LIBDIR', self.config.qt5_pkgconfigdir, sep=os.pathsep)
        if self.config.target_platform != Platform.WINDOWS:
            return

        if isinstance(self, (Cargo, Meson)):
            if self.using_msvc():
                toolchain_env = self.config.msvc_env_for_toolchain.items()
            else:
                toolchain_env = self.config.mingw_env_for_toolchain.items()
        else:
            if self.using_msvc():
                toolchain_env = chain(self.config.msvc_env_for_toolchain.items(),
                                      self.config.msvc_env_for_build_system.items())
            else:
                toolchain_env = chain(self.config.mingw_env_for_toolchain.items(),
                                      self.config.mingw_env_for_build_system.items())
        # Set the toolchain environment
        for var, val in toolchain_env:
            # PATH and LDFLAGS are already set in self.env by config.py, so we
            # need to prepend those.
            if var in ('PATH', 'LDFLAGS'):
                self.prepend_env(var, val.get(), sep=val.sep)
            else:
                self.set_env(var, val.get(), sep=val.sep)

    def unset_toolchain_env(self):
        for var in ('CC', 'CXX', 'OBJC', 'OBJCXX', 'AR', 'WINDRES', 'STRIP',
                    'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'OBJCFLAGS', 'LDFLAGS'):
            if var in self.env:
                # Env vars that are edited by the recipe will be restored by
                # @modify_environment when we return from the build step but
                # other env vars won't be, so add those.
                self.set_env(var, None, when='now-with-restore')

    def check_reentrancy(self):
        if self._old_env:
            raise RuntimeError('Do not modify the env inside @modify_environment, it will have no effect')

    @modify_environment
    def get_recipe_env(self):
        '''
        Used in oven.py to start a shell prompt with the correct env on recipe
        build failure
        '''
        return self.env.copy()

    def _save_env_var(self, var):
        # Will only store the first 'save'.
        if var not in self._old_env:
            if var in self.env:
                self._old_env[var] = self.env[var]
            else:
                self._old_env[var] = None

    def _modify_env(self):
        '''
        Modifies the build environment by inserting env vars from new_env
        '''
        # If requested, remove the new mingw-perl downloaded in bootstrap from
        # PATH and use the MSYS Perl instead
        if self.config.distro == Distro.MSYS and self.use_msys_perl:
            mingw_perl_bindir = Path(self.config.mingw_perl_prefix) / 'bin'
            self.remove_env('PATH', mingw_perl_bindir.as_posix(), sep=os.pathsep)
        # Don't modify env again if already did it once for this function call
        if self._old_env:
            return
        # Store old env
        for var in self._env_vars:
            self._save_env_var(var)
        # Modify env
        for env_op in self._new_env:
            env_op.execute(self.env)

    def _restore_env(self):
        ''' Restores the old environment '''
        for var, val in self._old_env.items():
            if val is None:
                if var in self.env:
                    del self.env[var]
            else:
                self.env[var] = val
        self._old_env.clear()

    def maybe_add_system_libs(self, step=''):
        '''
        Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
        can be found.
        '''
        # Note: this is expected to be called with the environment already
        # modified using @{async_,}modify_environment

        # don't add system libs unless explicitly asked for
        if not self.use_system_libs or not self.config.allow_system_libs:
            return;

        # this only works because add_system_libs() does very little
        # this is a possible source of env conflicts
        new_env = {}
        add_system_libs(self.config, new_env, self.env)

        if 'configure' not in step:
            # gobject-introspection gets the paths to internal libraries all
            # wrong if we add system libraries during compile.  We should only
            # need PKG_CONFIG_PATH during configure so just unset it everywhere
            # else we will get linker errors compiling introspection binaries
            if 'PKG_CONFIG_PATH' in new_env:
                del new_env['PKG_CONFIG_PATH']
        for var, val in new_env.items():
            self.set_env(var, val, when='now-with-restore')


class Build(object):
    '''
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    library_type = LibraryType.BOTH
    # Whether this recipe's build system can be built with MSVC
    can_msvc = False

    def __init__(self):
        self._properties_keys = []

    @modify_environment
    def get_env(self, var, default=None):
        if var in self.env:
            return self.env[var]
        return default

    def using_msvc(self):
        if not self.can_msvc:
            return False
        if not self.config.variants.visualstudio:
            return False
        return True

    def using_uwp(self):
        if not self.config.variants.uwp:
            return False
        # When the uwp variant is enabled, we must never select recipes that
        # don't have can_msvc = True
        if not self.can_msvc:
            raise RuntimeError("Tried to build a recipe that can't use MSVC when using UWP")
        if not self.config.variants.visualstudio:
            raise RuntimeError("visualstudio variant wasn't set when uwp variant was set")
        return True

    async def configure(self):
        '''
        Configures the module
        '''
        raise NotImplemented("'configure' must be implemented by subclasses")

    async def compile(self):
        '''
        Compiles the module
        '''
        raise NotImplemented("'make' must be implemented by subclasses")

    async def install(self):
        '''
        Installs the module
        '''
        raise NotImplemented("'install' must be implemented by subclasses")

    def check(self):
        '''
        Runs any checks on the module
        '''
        pass

    def num_of_cpus(self):
        if self.config.allow_parallel_build and getattr(self, 'allow_parallel_build', True) \
                and self.config.num_of_cpus > 1:
            return self.config.num_of_cpus
        return None

class CustomBuild(Build, ModifyEnvBase):

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)

    async def configure(self):
        pass

    async def compile(self):
        pass

    async def install(self):
        pass


class MakefilesBase (Build, ModifyEnvBase):
    '''
    Base class for makefiles build systems like autotools and cmake
    '''

    config_sh = ''
    configure_tpl = ''
    configure_options = ''
    make = None
    make_install = None
    make_check = None
    make_clean = None
    allow_parallel_build = True
    srcdir = '.'
    requires_non_src_build = False
    # recipes often use shell constructs
    config_sh_needs_shell = True

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self.setup_toolchain_env_ops()
        if not self.using_msvc():
            self.setup_buildtype_env_ops()

        if self.requires_non_src_build:
            self.make_dir = os.path.join (self.config_src_dir, "cerbero-build-dir")
        else:
            self.make_dir = os.path.abspath(os.path.join(self.config_src_dir,
                                                           self.srcdir))

        self.make = self.make or ['make', 'V=1']
        self.make_install = self.make_install or ['make', 'install']
        self.make_clean = self.make_clean or ['make', 'clean']

        ncpu = self.num_of_cpus()
        if ncpu:
            self.make += ['-j%d' % ncpu]

        # Make sure user's env doesn't mess up with our build.
        self.set_env('MAKEFLAGS', when='now')
        # Disable site config, which is set on openSUSE
        self.set_env('CONFIG_SITE', when='now')

    async def configure(self):
        '''
        Base configure method

        When called from a method in deriverd class, that method has to be
        decorated with modify_environment decorator.
        '''
        if not os.path.exists(self.make_dir):
            os.makedirs(self.make_dir)
        if self.requires_non_src_build:
            self.config_sh = os.path.join('../', self.config_sh)

        substs = {
            'config-sh': self.config_sh,
            'prefix': self.config.prefix,
            'libdir': self.config.libdir,
            'host': self.config.host,
            'target': self.config.target,
            'build': self.config.build,
            'options': self.configure_options,
            'build_dir': self.build_dir,
            'make_dir': self.make_dir,
        }

        # Construct a command list when possible
        if not self.config_sh_needs_shell:
            configure_cmd = []
            for arg in self.configure_tpl.split():
                if arg == '%(options)s':
                    options = self.configure_options
                    if isinstance(options, str):
                        options = options.split()
                    configure_cmd += options
                else:
                    configure_cmd.append(arg % substs)
        else:
            configure_cmd = self.configure_tpl % substs

        self.maybe_add_system_libs(step='configure')

        await shell.async_call(configure_cmd, self.make_dir,
                               logfile=self.logfile, env=self.env)

    @modify_environment
    async def compile(self):
        self.maybe_add_system_libs(step='compile')
        await shell.async_call(self.make, self.make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='install')
        await shell.async_call(self.make_install, self.make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def clean(self):
        self.maybe_add_system_libs(step='clean')
        shell.new_call(self.make_clean, self.make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def check(self):
        if self.make_check:
            self.maybe_add_system_libs(step='check')
            shell.new_call(self.make_check, self.build_dir, logfile=self.logfile, env=self.env)


class Makefile (MakefilesBase):
    '''
    Build handler for Makefile project
    '''
    @modify_environment
    async def configure(self):
        await MakefilesBase.configure(self)


class Autotools (MakefilesBase):
    '''
    Build handler for autotools project

    @cvar override_libtool: overrides ltmain.sh to generate a libtool
                            script with the one built by cerbero.
    @type override_libtool: boolean
    '''

    autoreconf = False
    autoreconf_sh = 'autoreconf -f -i'
    config_sh = './configure'
    configure_tpl = "%(config-sh)s --prefix %(prefix)s "\
                    "--libdir %(libdir)s"
    add_host_build_target = True
    can_use_configure_cache = True
    supports_cache_variables = True
    disable_introspection = False
    override_libtool = True

    def __init__(self):
        MakefilesBase.__init__(self)
        self.make_check = self.make_check or ['make', 'check']

    @modify_environment
    async def configure(self):
        # Build with PIC for static linking
        self.configure_tpl += ' --with-pic '
        # Disable automatic dependency tracking, speeding up one-time builds
        self.configure_tpl += ' --disable-dependency-tracking '
        # Only use --disable-maintainer mode for real autotools based projects
        if os.path.exists(os.path.join(self.config_src_dir, 'configure.in')) or\
                os.path.exists(os.path.join(self.config_src_dir, 'configure.ac')):
            self.configure_tpl += " --disable-maintainer-mode "
            self.configure_tpl += " --disable-silent-rules "
            # Never build gtk-doc documentation
            self.configure_tpl += " --disable-gtk-doc "

        if self.config.variants.gi and not self.disable_introspection \
                and self.use_gobject_introspection():
            self.configure_tpl += " --enable-introspection "
        else:
            self.configure_tpl += " --disable-introspection "

        if self.autoreconf:
            await shell.async_call(self.autoreconf_sh, self.config_src_dir,
                                   logfile=self.logfile, env=self.env)

        # We don't build libtool on Windows
        if self.config.platform == Platform.WINDOWS:
            self.override_libtool = False

        # Use our own config.guess and config.sub
        config_datadir = os.path.join(self.config._relative_path('data'), 'autotools')
        cfs = {'config.guess': config_datadir, 'config.sub': config_datadir}
        # ensure our libtool modifications are actually picked up by recipes
        if self.name != 'libtool' and self.override_libtool:
            cfs['ltmain.sh'] = os.path.join(self.config.build_tools_prefix, 'share/libtool/build-aux')
        for cf, srcdir in cfs.items():
            find_cmd = 'find {} -type f -name {}'.format(self.config_src_dir, cf)
            files = await shell.async_call_output(find_cmd, logfile=self.logfile, env=self.env)
            files = files.split('\n')
            files.remove('')
            for f in files:
                o = os.path.join(srcdir, cf)
                m.log("CERBERO: copying %s to %s" % (o, f), self.logfile)
                shutil.copy(o, f)

        if self.config.platform == Platform.WINDOWS and \
                self.supports_cache_variables:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in self.env.items():
                if k[2:6] == '_cv_':
                    self.configure_tpl += ' %s="%s"' % (k, v)

        if self.add_host_build_target:
            if self.config.host is not None:
                self.configure_tpl += ' --host=%(host)s'
            if self.config.build is not None:
                self.configure_tpl += ' --build=%(build)s'
            if self.config.target is not None:
                self.configure_tpl += ' --target=%(target)s'

        use_configure_cache = self.config.use_configure_cache
        if self.use_system_libs and self.config.allow_system_libs:
            use_configure_cache = False

        if self._new_env:
            use_configure_cache = False

        if use_configure_cache and self.can_use_configure_cache:
            cache = os.path.join(self.config.sources, '.configure.cache')
            self.configure_tpl += ' --cache-file=%s' % cache

        # Add at the very end to allow recipes to override defaults
        self.configure_tpl += "  %(options)s "

        await MakefilesBase.configure(self)


class CMake (MakefilesBase):
    '''
    Build handler for cmake projects
    '''

    cmake_generator = 'make'
    config_sh_needs_shell = False
    config_sh = None
    configure_tpl = '%(config-sh)s -DCMAKE_INSTALL_PREFIX=%(prefix)s ' \
                    '-H%(make_dir)s ' \
                    '-B%(build_dir)s ' \
                    '-DCMAKE_LIBRARY_OUTPUT_PATH=%(libdir)s ' \
                    '-DCMAKE_INSTALL_LIBDIR=%(libdir)s ' \
                    '-DCMAKE_INSTALL_BINDIR=bin ' \
                    '-DCMAKE_INSTALL_INCLUDEDIR=include ' \
                    '%(options)s -DCMAKE_BUILD_TYPE=Release '\
                    '-DCMAKE_FIND_ROOT_PATH=$CERBERO_PREFIX '\
                    '-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=true '

    def __init__(self):
        MakefilesBase.__init__(self)
        self.build_dir = os.path.join(self.build_dir, '_builddir')
        self.config_sh = 'cmake'
        if self.config.distro == Distro.MSYS2:
            # We do not want the MSYS2 CMake because it doesn't support MSVC
            self.config_sh = shutil.which('cmake', path=shell.get_path_minus_msys(self.env['PATH']))

    @modify_environment
    async def configure(self):
        cc = self.env.get('CC', 'gcc')
        cxx = self.env.get('CXX', 'g++')
        cflags = self.env.get('CFLAGS', '')
        cxxflags = self.env.get('CXXFLAGS', '')
        # FIXME: CMake doesn't support passing "ccache $CC"
        if self.config.use_ccache:
            cc = cc.replace('ccache', '').strip()
            cxx = cxx.replace('ccache', '').strip()
        cc = cc.split(' ')[0]
        cxx = cxx.split(' ')[0]

        if self.configure_options:
            self.configure_options = self.configure_options.split()
        else:
            self.configure_options = []

        if self.cmake_generator == 'ninja' or self.using_msvc():
            self.configure_options += ['-G', 'Ninja']
            self.make = ['ninja', '-v']
            ncpu = self.num_of_cpus()
            if ncpu:
                self.make += ['-j%d' % ncpu]
            else:
                self.make += ['-j1']
            self.make_install = self.make + ['install']
        else:
            if self.config.platform == Platform.WINDOWS and \
                    self.config.distro != Distro.MSYS :
                self.configure_options += ['-G', 'MSYS Makefiles']
            else:
                self.configure_options += ['-G', 'Unix Makefiles']
            self.make += ['VERBOSE=1']

        if self.config.target_platform == Platform.WINDOWS:
            system_name = 'Windows'
        elif self.config.target_platform in (Platform.LINUX, Platform.ANDROID):
            system_name = 'Linux'
        elif self.config.target_platform == Platform.DARWIN:
            system_name = 'Darwin'
        elif self.config.target_platform == Platform.IOS:
            system_name = 'iOS'

        if self.config.cross_compiling() or self.config.target_platform == Platform.WINDOWS:
            self.configure_options += [f'-DCMAKE_SYSTEM_NAME={system_name}']

        if self.config.target_platform in (Platform.DARWIN, Platform.IOS):
            self.configure_options += ['-DCMAKE_OSX_ARCHITECTURES=' + self.config.target_arch]

        # FIXME: Maybe export the sysroot properly instead of doing regexp magic
        if self.config.target_platform in [Platform.DARWIN, Platform.IOS]:
            r = re.compile(r".*-isysroot ([^ ]+) .*")
            sysroot = r.match(cflags).group(1)
            self.configure_options += ['-DCMAKE_OSX_SYSROOT=' + sysroot]

        self.configure_options += [
            '-DCMAKE_C_COMPILER=' + cc,
            '-DCMAKE_CXX_COMPILER=' + cxx,
            '-DCMAKE_C_FLAGS=' + cflags,
            '-DCMAKE_CXX_FLAGS=' + cxxflags,
            '-DLIB_SUFFIX=' + self.config.lib_suffix,
        ]

        cmake_cache = os.path.join(self.make_dir, 'CMakeCache.txt')
        cmake_files = os.path.join(self.make_dir, 'CMakeFiles')
        if os.path.exists(cmake_cache):
            os.remove(cmake_cache)
        if os.path.exists(cmake_files):
            shutil.rmtree(cmake_files)
        await MakefilesBase.configure(self)
        if not os.path.exists(self.build_dir):
            os.makedirs(self.build_dir)
        # as build_dir is different from source dir, makefile location will be in build_dir.
        self.make_dir = self.build_dir

MESON_FILE_TPL = \
'''
[host_machine]
system = '{system}'
cpu_family = '{cpu_family}'
cpu = '{cpu}'
endian = '{endian}'

[properties]
{extra_properties}

[binaries]
c = {CC}
cpp = {CXX}
objc = {OBJC}
objcpp = {OBJCXX}
ar = {AR}
pkgconfig = {PKG_CONFIG}
{extra_binaries}
'''

class Meson (Build, ModifyEnvBase) :
    '''
    Build handler for meson project
    '''

    make = None
    make_install = None
    make_check = None
    make_clean = None

    meson_sh = None
    meson_options = None
    meson_subprojects = None
    meson_backend = 'ninja'
    # All meson recipes are MSVC-compatible, except if the code itself isn't
    can_msvc = True
    # Build files require a build machine compiler when cross-compiling
    meson_needs_build_machine_compiler = False
    meson_builddir = "_builddir"
    # We do not use cmake dependency files by default, speed up the build by disabling it
    need_cmake = False

    def __init__(self):
        self.meson_options = self.meson_options or {}
        self.meson_subprojects = self.meson_subprojects or []

        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self.setup_toolchain_env_ops()

        # Find Meson
        if not self.meson_sh:
            # meson installs `meson.exe` on windows and `meson` on other
            # platforms that read shebangs
            self.meson_sh = os.path.join(self.config.build_tools_prefix, 'bin', 'meson')

        # Find ninja
        if not self.make:
            self.make = ['ninja', '-v', '-d', 'keeprsp']
            ncpu = self.num_of_cpus()
            if ncpu:
                self.make += ['-j%d' % ncpu]
            else:
                self.make += ['-j1']
        if not self.make_install:
            self.make_install = [self.meson_sh, 'install', '--skip-subprojects']
        if not self.make_check:
            self.make_check = self.make + ['test']
        if not self.make_clean:
            self.make_clean = self.make + ['clean']

        # Allow CMake dependencies to be found if requested
        if self.need_cmake:
            self.append_env('CMAKE_PREFIX_PATH', self.config.prefix, sep=os.pathsep)
        self.meson_dir = os.path.join(self.build_dir, self.meson_builddir)

    @staticmethod
    def _get_option_value(opt_type, value):
        if opt_type == 'feature':
            return 'enabled' if value else 'disabled'
        if opt_type == 'boolean':
            return 'true' if value else 'false'
        raise AssertionError('Invalid option type {!r}'.format(opt_type))

    def _set_option(self, opt_names, variant_name):
        '''
        Parse the meson_options.txt file, figure out whether any of the provided option names exist,
        figure out the type, and enable/disable it as per the cerbero configuration.
        '''
        # Don't overwrite if it's already set
        if opt_names.intersection(self.meson_options):
            return
        # Error out on invalid usage
        if not os.path.isdir(self.build_dir):
            raise FatalError('Build directory doesn\'t exist yet?')
        # Check if the option exists, and if so, what the type is
        meson_options = os.path.join(self.build_dir, 'meson_options.txt')
        if not os.path.isfile(meson_options):
            return
        opt_name = None
        opt_type = None
        with open(meson_options, 'r', encoding='utf-8') as f:
            options = f.read()
            # iterate over all option()s individually
            option_regex = r"option\s*\(\s*(?:'(?P<name>[^']+)')\s*,\s*(?P<entry>(?P<identifier>[a-zA-Z0-9]+)\s*:\s*(?:(?P<string>'[^']+')|[^'\),\s]+)\s*,?\s*)+\)"
            for match in re.finditer(option_regex, options, re.MULTILINE):
                option = match.group(0)
                # find the option(), if it exists
                opt_name = match.group('name')
                if opt_name in opt_names:
                    # get the type of the option
                    type_regex = r"type\s*:\s*'(?P<type>[^']+)'"
                    ty = re.search (type_regex, option, re.MULTILINE)
                    if ty:
                        if ty.group('type') in ('feature', 'boolean'):
                            opt_type = ty.group('type')
                            break
                        elif ty.group('type') == 'string':
                            break
                    raise FatalError('Unable to detect type of option {!r}'.format(opt_name))
        if opt_name and opt_type:
            value = getattr(self.config.variants, variant_name) if variant_name else False
            self.meson_options[opt_name] = self._get_option_value(opt_type, value)

    def _get_target_cpu_family(self):
        if Architecture.is_arm(self.config.target_arch):
            if Architecture.is_arm32(self.config.target_arch):
                return 'arm'
            else:
                return 'aarch64'
        return self.config.target_arch

    def _get_moc_path(self, qmake_path):
        qmake = Path(qmake_path)
        moc_name = qmake.name.replace('qmake', 'moc')
        return str(qmake.parent / moc_name)

    def _get_meson_target_file_contents(self):
        '''
        Get the toolchain configuration for the target machine. This will
        either go into a cross file or a native file depending on whether we're
        cross-compiling or not.
        '''
        def merge_env(old_env, new_env):
            ret_env = {}
            # Set/merge new values
            for k, new_v in new_env.items():
                new_v = EnvValue.from_key(k, new_v)
                if k not in old_env:
                    ret_env[k] = new_v
                    continue
                old_v = old_env[k]
                assert(isinstance(old_v, EnvValue))
                if isinstance(old_v, (EnvValueSingle, EnvValueCmd)) or (new_v == old_v):
                    ret_env[k] = new_v
                elif isinstance(old_v, (EnvValuePath, EnvValueArg)):
                    ret_env[k] = new_v + old_v
                else:
                    raise FatalError("Don't know how to combine the environment "
                        "variable '%s' with values '%s' and '%s'" % (k, new_v, old_v))
            # Set remaining old values
            for k in old_env.keys():
                if k not in new_env:
                    ret_env[k] = old_env[k]
            return ret_env

        # Extract toolchain config for the build system from the appropriate
        # config env dict. Start with `self.env`, since it contains toolchain
        # config set by the recipe and when building for target platforms other
        # than Windows, it also contains build tools and the env for the
        # toolchain set by config/*.config.
        #
        # On Windows, the toolchain config is `self.config.msvc_env_for_build_system`
        # or `self.config.mingw_env_for_build_system` depending on which toolchain
        # this recipe will use.
        if self.config.target_platform == Platform.WINDOWS:
            if self.using_msvc():
                build_env = dict(self.config.msvc_env_for_build_system)
            else:
                build_env = dict(self.config.mingw_env_for_build_system)
        else:
            build_env = {}
        # Override/merge toolchain env with recipe env and return a new dict
        # with values as EnvValue objects
        build_env = merge_env(build_env, self.env)

        cc = build_env.pop('CC')
        cxx = build_env.pop('CXX')
        objc = build_env.pop('OBJC', ['false'])
        objcxx = build_env.pop('OBJCXX', ['false'])
        ar = build_env.pop('AR')
        # We currently don't set the pre-processor or the linker when building with meson
        build_env.pop('CPP', None)
        build_env.pop('LD', None)

        # Operate on a copy of the recipe properties to avoid accumulating args
        # from all archs when doing universal builds
        props = {}
        build_env.pop('CPP', None) # Meson does not read this
        build_env.pop('CPPFLAGS', None) # Meson does not read this, and it's duplicated in *FLAGS
        props['c_args'] = build_env.pop('CFLAGS', [])
        props['cpp_args'] = build_env.pop('CXXFLAGS', [])
        props['objc_args'] = build_env.pop('OBJCFLAGS', [])
        props['objcpp_args'] = build_env.pop('OBJCXXFLAGS', [])
        # Link args
        props['c_link_args'] = build_env.pop('LDFLAGS', [])
        props['cpp_link_args'] = props['c_link_args']
        props['objc_link_args'] = build_env.pop('OBJLDFLAGS', props['c_link_args'])
        props['objcpp_link_args'] = props['objc_link_args']
        for key, value in self.config.meson_properties.items():
            if key not in props:
                props[key] = value
            else:
                props[key] += value

        if self.need_cmake:
            binaries = {}
        else:
            binaries = {'cmake': ['false']}
        # Get qmake and moc paths
        if self.config.qt5_qmake_path:
            binaries['qmake5'] = [self.config.qt5_qmake_path]
        if self.config.qt6_qmake_path:
            binaries['qmake6'] = [self.config.qt6_qmake_path]

        # Point meson to rustc with correct arguments to ensure it's detected when cross-compiling
        if self.config.cargo_home:
            target_triple = self.config.rust_triple(self.config.target_arch,
                self.config.target_platform, self.using_msvc())
            binaries['rust'] = [self.config.cargo_home + '/bin/rustc', '--target', target_triple]

        # Try to detect build tools in the remaining env vars
        build_tool_paths = build_env['PATH'].get()
        for name, tool in build_env.items():
            # Autoconf env vars, incorrectly detected as a build tool because of 'yes'
            if name.startswith('ac_cv'):
                continue
            # Files are always executable on Windows
            if name in ('HISTFILE', 'GST_REGISTRY_1_0'):
                continue
            if tool and shutil.which(tool[0], path=build_tool_paths):
                binaries[name.lower()] = tool

        extra_properties = ''
        for k, v in props.items():
            extra_properties += '{} = {}\n'.format(k, str(v))

        extra_binaries = ''
        for k, v in binaries.items():
            extra_binaries += '{} = {}\n'.format(k, str(v))

        contents = MESON_FILE_TPL.format(
                system=self.config.target_platform,
                cpu=self.config.target_arch,
                cpu_family=self._get_target_cpu_family(),
                # Assume all supported target archs are little endian
                endian='little',
                CC=cc,
                CXX=cxx,
                OBJC=objc,
                OBJCXX=objcxx,
                AR=ar,
                PKG_CONFIG="'pkg-config'",
                extra_binaries=extra_binaries,
                extra_properties=extra_properties)
        return contents

    def _get_meson_native_file_contents(self):
        '''
        Get a toolchain configuration that points to the build machine's
        toolchain. On Windows, this is the MinGW toolchain that we ship. On
        Linux and macOS, this is the system-wide compiler.
        When targetting android, we can use the NDK bundled clang compiler
        for this purpose as well.
        '''
        false = ['false']
        if self.config.platform == Platform.WINDOWS:
            cc = self.config.mingw_env_for_build_system['CC']
            cxx = self.config.mingw_env_for_build_system['CXX']
            ar = self.config.mingw_env_for_build_system['AR']
            objc = false
            objcxx = false
        elif self.config.platform == Platform.DARWIN:
            cc = ['clang']
            cxx = ['clang++']
            ar = ['ar']
            objc = cc
            objcxx = cxx
        elif self.config.target_platform == Platform.ANDROID:
            cc = ['clang']
            cxx = ['clang++']
            ar = ['llvm-ar']
            objc = cc
            objcxx = cxx
        else:
            cc = ['cc']
            cxx = ['c++']
            ar = ['ar']
            objc = false
            objcxx = false
        # We do not use cmake dependency files, speed up the build by disabling it
        extra_binaries = 'cmake = {}'.format(str(false))
        contents = MESON_FILE_TPL.format(
                system=self.config.platform,
                cpu=self.config.arch,
                cpu_family=self.config.arch,
                endian='little',
                CC=cc,
                CXX=cxx,
                OBJC=objc,
                OBJCXX=objcxx,
                AR=ar,
                PKG_CONFIG=false,
                extra_binaries=extra_binaries,
                extra_properties='')
        return contents

    def _get_meson_dummy_file_contents(self):
        '''
        Get a toolchain configuration that points to `false` for everything.
        This forces Meson to not detect a build-machine (native) compiler when
        cross-compiling.
        '''
        # Tell meson to not use a native compiler for anything
        false = ['false']
        # We do not use cmake dependency files, speed up the build by disabling it
        extra_binaries = 'cmake = {}'.format(str(false))
        contents = MESON_FILE_TPL.format(
                system=self.config.platform,
                cpu=self.config.arch,
                cpu_family=self.config.arch,
                endian='little',
                CC=false,
                CXX=false,
                OBJC=false,
                OBJCXX=false,
                AR=false,
                PKG_CONFIG=false,
                extra_binaries=extra_binaries,
                extra_properties='')
        return contents

    def _write_meson_file(self, contents, fname):
        fpath = os.path.join(self.meson_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(contents)
        return fpath

    @modify_environment
    async def configure(self):
        # self.build_dir is different on each call to configure() when doing universal builds
        self.meson_dir = os.path.join(self.build_dir, self.meson_builddir)
        if os.path.exists(self.meson_dir):
            # Only remove if it's not empty
            if os.listdir(self.meson_dir):
                shutil.rmtree(self.meson_dir)
                os.makedirs(self.meson_dir)
        else:
            os.makedirs(self.meson_dir)

        # Explicitly enable/disable introspection, same as Autotools
        self._set_option({'introspection', 'gir'}, 'gi')
        # Control python support using the variant
        self._set_option({'python'}, 'python')
        # Always disable gtk-doc, same as Autotools
        self._set_option({'gtk_doc'}, None)
        # Automatically disable examples
        self._set_option({'examples'}, None)

        # NOTE: self.tagged_for_release is set in recipes/custom.py
        is_gstreamer_recipe = hasattr(self, 'tagged_for_release')
        # Enable -Werror for gstreamer recipes and when running under CI
        if is_gstreamer_recipe and self.config.variants.werror:
            # Let recipes override the value
            if 'werror' not in self.meson_options:
                self.meson_options['werror'] = 'true'

        debug = 'true' if self.config.variants.debug else 'false'
        opt = get_optimization_from_config(self.config)

        if self.library_type == LibraryType.NONE:
            raise RuntimeException("meson recipes cannot be LibraryType.NONE")

        meson_cmd = [self.meson_sh, 'setup', '--prefix=' + self.config.prefix,
            '--libdir=lib' + self.config.lib_suffix, '-Ddebug=' + debug,
            '--default-library=' + self.library_type, '-Doptimization=' + opt,
            '--backend=' + self.meson_backend, '--wrap-mode=nodownload',
            '-Dpkgconfig.relocatable=true']

        if self.using_msvc():
            meson_cmd.append('-Db_vscrt=' + self.config.variants.vscrt)

        # Get platform config in the form of a meson native/cross file
        contents = self._get_meson_target_file_contents()
        # If cross-compiling, write contents to the cross file and get contents for
        # a native file that will cause all native compiler detection to fail.
        #
        # Else, write contents to a native file.
        if self.config.cross_compiling():
            meson_cmd += ['--cross-file', self._write_meson_file(contents, 'meson-cross-file.txt')]
            if self.meson_needs_build_machine_compiler:
                contents = self._get_meson_native_file_contents()
            else:
                contents = self._get_meson_dummy_file_contents()
        meson_cmd += ['--native-file', self._write_meson_file(contents, 'meson-native-file.txt')]

        if 'default_library' in self.meson_options:
            raise RuntimeError('Do not set `default_library` in self.meson_options, use self.library_type instead')

        for (key, value) in self.meson_options.items():
            meson_cmd += ['-D%s=%s' % (key, str(value))]

        # We export the target toolchain with env vars, but that confuses Meson
        # when cross-compiling (it will pick the env vars for the build
        # machine). We always set this using the cross file or native file as
        # applicable, so always unset these.
        # FIXME: We need an argument for meson that tells it to not pick up the
        # toolchain from the env.
        # https://gitlab.freedesktop.org/gstreamer/cerbero/issues/48
        self.unset_toolchain_env()

        self.maybe_add_system_libs(step='configure')
        await shell.async_call(meson_cmd, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def compile(self):
        self.maybe_add_system_libs(step='compile')
        await shell.async_call(self.make, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='install')
        await shell.async_call(self.make_install, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def clean(self):
        self.maybe_add_system_libs(step='clean')
        shell.new_call(self.make_clean, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def check(self):
        self.maybe_add_system_libs(step='check')
        shell.new_call(self.make_check, self.meson_dir, logfile=self.logfile, env=self.env)


class Cargo(Build, ModifyEnvBase):
    '''
    Cargo build system recipes

    NOTE: Currently only intended for build-tools recipes
    '''
    srcdir = '.'
    can_msvc = True
    cargo_features = None

    def __init__(self):
        self.cargo_features = self.cargo_features or []

        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self.setup_toolchain_env_ops()
        if not self.using_msvc():
            self.setup_buildtype_env_ops()

        self.config_src_dir = os.path.abspath(os.path.join(self.build_dir,
                                                           self.srcdir))
        self.cargo_dir = os.path.join(self.config_src_dir, '_builddir')
        self.cargo = os.path.join(self.config.cargo_home, 'bin',
                'cargo' + self.config._get_exe_suffix())

        # Debuginfo is enormous, about 0.5GB per plugin, so it's split out
        # where enabled by default (macOS and MSVC) and stripped everywhere
        # else because the split-debuginfo option is unstable and actually
        # crashes.
        # TODO: We don't ship split debuginfo (dSYM, PDB) in the packages yet:
        # https://gitlab.freedesktop.org/gstreamer/cerbero/-/issues/381
        if self.config.target_platform == Platform.DARWIN or self.using_msvc():
            self.rustc_debuginfo = 'split'
        else:
            self.rustc_debuginfo = 'strip'
        try:
            self.target_triple = self.config.rust_triple(self.config.target_arch,
                    self.config.target_platform, self.using_msvc())
        except FatalError as e:
            raise InvalidRecipeError(self.name, e.msg)

        self.cargo_args = [
            '--verbose', '--offline',
            '--target', self.target_triple,
            '--target-dir', self.cargo_dir,
        ]

        jobs = self.num_of_rustc_jobs()
        if jobs is not None:
            self.cargo_args += [f'-j{jobs}']

        # https://github.com/lu-zero/cargo-c/issues/278
        if self.config.target_platform in (Platform.ANDROID, Platform.IOS):
            self.library_type = LibraryType.STATIC

    def num_of_rustc_jobs(self):
        '''
        Restricts parallelism with <= 4 threads or with <= 8 GB RAM.
        '''
        ncpu = super().num_of_cpus()
        num_of_jobs = determine_num_of_cpus()
        has_enough_ram = determine_total_ram() > (8 * 1 << 30) # 8 GB

        if num_of_jobs <= 4 or not has_enough_ram:
            return 1
        elif ncpu:
            return ncpu

        return None

    def get_cargo_features_args(self):
        if not self.cargo_features:
            return []
        return ['--features=' + ','.join(self.cargo_features)]

    def append_config_toml(self, s):
        dot_cargo = os.path.join(self.config_src_dir, '.cargo')
        os.makedirs(dot_cargo, exist_ok=True)
        # Append so we don't overwrite cargo vendor settings
        with open(os.path.join(dot_cargo, 'config.toml'), 'a') as f:
            f.write(s)

    def get_llvm_tool(self, tool: str) -> Path:
        '''
        Gets one of the LLVM tools matching the current Rust toolchain.
        '''
        root_dir = subprocess.run([self.config.cargo_home + '/bin/rustc',
                                   '--print', 'sysroot'], capture_text=True, text=True, check=True).stdout.strip()
        tools = glob.glob(f'**/{tool}', root_dir=root_dir)
        if len(tools) == 0:
            raise FatalError('Rust {tool} tool not found, try re-running bootstrap')
        return (Path(root_dir) / tools[0]).resolve()

    def get_cargo_toml_version(self):
        tomllib = self.config.find_toml_module()
        if not tomllib:
            raise FatalError('toml module not found, try re-running bootstrap')
        cargo_toml_list = [os.path.join(self.config_src_dir, 'Cargo.toml')]
        cargo_toml_list += glob.glob(f'{self.config_src_dir}/**/Cargo.toml', recursive=True)
        for cargo_toml in cargo_toml_list:
            with open(cargo_toml, 'r', encoding='utf-8') as f:
                data = tomllib.loads(f.read())
            try:
                version = data['package']['version']
            except KeyError:
                continue
            return version

    async def configure(self):
        if os.path.exists(self.cargo_dir):
            # Only remove if it's not empty
            if os.listdir(self.cargo_dir):
                shutil.rmtree(self.cargo_dir)
                os.makedirs(self.cargo_dir)
        else:
            os.makedirs(self.cargo_dir)

        # TODO: Ideally we should strip while packaging, not while linking
        if self.rustc_debuginfo == 'strip':
            s = '\n[profile.release]\nstrip = "debuginfo"\n'
            self.append_config_toml(s)
        else:
            s = '\n[profile.release]\nsplit-debuginfo = "packed"\n'
            self.append_config_toml(s)

        if self.config.target_platform == Platform.ANDROID:
            # Use the compiler's forwarding
            # See https://android.googlesource.com/platform/ndk/+/master/docs/BuildSystemMaintainers.md#linkers
            linker = self.get_env('RUSTC_LINKER')
            link_args = []
            args = iter(shlex.split(self.get_env('LDFLAGS', '')))
            # We need to extract necessary linker flags from LDFLAGS which is
            # passed to the compiler
            for arg in args:
                link_args += ['-C', f"link-args={arg}"]
            s = f'[target.{self.target_triple}]\n' \
                f'linker = "{linker}"\n' \
                f'rustflags = {link_args!r}\n'
            self.append_config_toml(s)
        # No configure step with cargo

    async def compile(self):
        # Intended only for build-tools recipes, which we will directly install
        recipe_subdir = os.path.basename(os.path.dirname(self.__file__))
        if 'build-tools' not in recipe_subdir:
            raise FatalError('BuildType.CARGO is only intended for build-tools recipes')

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='configure+install')
        cmd = [
            self.cargo, 'install',
            '--path', self.config_src_dir,
            '--root', self.config.prefix,
        ] + self.cargo_args + self.get_cargo_features_args()
        await self.retry_run(shell.async_call, cmd, logfile=self.logfile, env=self.env)


class CargoC(Cargo):
    '''
    Cargo-C build system recipes
    '''
    srcdir = '.'

    cargoc_packages = None

    def __init__(self):
        self.cargoc_packages = self.cargoc_packages or []
        Cargo.__init__(self)

    def get_cargoc_args(self):
        cargoc_args = [
            '--release', '--frozen',
            '--prefix', self.config.prefix,
            '--libdir', self.config.libdir,
        ]
        # --library-type args do not override, but are collected
        if self.library_type in (LibraryType.STATIC, LibraryType.BOTH):
            cargoc_args += ['--library-type', 'staticlib']
        if self.library_type in (LibraryType.SHARED, LibraryType.BOTH):
            cargoc_args += ['--library-type', 'cdylib']
        cargoc_args += self.cargo_args
        for package in self.cargoc_packages:
            args = ['-p', package]
            cargoc_args += args
        cargoc_args += self.get_cargo_features_args()
        return cargoc_args

    @modify_environment
    async def compile(self):
        self.maybe_add_system_libs(step='configure+compile')
        cmd = [self.cargo, 'cbuild'] + self.get_cargoc_args()
        await self.retry_run(shell.async_call, cmd, self.cargo_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='configure+install')
        cmd = [self.cargo, 'cinstall'] + self.get_cargoc_args()
        await self.retry_run(shell.async_call, cmd, self.cargo_dir, logfile=self.logfile, env=self.env)


class BuildType (object):

    CUSTOM = CustomBuild
    MAKEFILE = Makefile
    AUTOTOOLS = Autotools
    CMAKE = CMake
    MESON = Meson
    CARGO = Cargo
    CARGO_C = CargoC
