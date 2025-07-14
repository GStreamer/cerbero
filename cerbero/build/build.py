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
import shutil
import shlex
import asyncio
from pathlib import Path
from itertools import chain

from cerbero.enums import Platform, Architecture, Distro, DistroVersion, LibraryType
from cerbero.errors import FatalError, InvalidRecipeError
from cerbero.utils import shell, add_system_libs, default_cargo_build_jobs
from cerbero.utils import messages as m


def get_optimization_from_config(config):
    if config.variants.optimization:
        if Platform.is_mobile(config.target_platform):
            return 's'
        return '2'
    return '0'


def modify_environment(func):
    """
    Decorator to modify the build environment

    When called recursively, it only modifies the environment once.
    """

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
    """
    An operation to be done on the values of a particular env var
    """

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
        vals = 'None'
        if self.sep:
            vals = self.sep.join(self.vals)
        return '<EnvVarOp ' + self.op + ' ' + self.var + ' with ' + vals + '>'


class ModifyEnvBase:
    """
    Base class for build systems and recipes that require extra env variables
    """

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
                return (
                    '<ModifyEnvFuncWrapper '
                    + this.method
                    + ' for '
                    + repr(this.target)
                    + '  at '
                    + str(hex(id(this)))
                    + '>'
                )

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
        if self.config.use_ccache and isinstance(self, CMake):
            self.set_env('CMAKE_C_COMPILER_LAUNCHER', 'ccache')
            self.set_env('CMAKE_CXX_COMPILER_LAUNCHER', 'ccache')
        if self.config.target_platform != Platform.WINDOWS:
            return

        if isinstance(self, (Cargo, Meson)):
            if self.using_msvc():
                toolchain_env = self.config.msvc_env_for_toolchain.items()
            else:
                toolchain_env = self.config.mingw_env_for_toolchain.items()
        else:
            if self.using_msvc():
                toolchain_env = chain(
                    self.config.msvc_env_for_toolchain.items(), self.config.msvc_env_for_build_system.items()
                )
            else:
                toolchain_env = chain(
                    self.config.mingw_env_for_toolchain.items(), self.config.mingw_env_for_build_system.items()
                )
        # Set the toolchain environment
        for var, val in toolchain_env:
            # PATH and LDFLAGS are already set in self.env by config.py, so we
            # need to prepend those.
            if var in ('PATH', 'LDFLAGS'):
                self.prepend_env(var, val.get(), sep=val.sep)
            else:
                self.set_env(var, val.get(), sep=val.sep)

    def unset_toolchain_env(self):
        for var in (
            'CC',
            'CXX',
            'OBJC',
            'OBJCXX',
            'AR',
            'WINDRES',
            'STRIP',
            'CFLAGS',
            'CXXFLAGS',
            'CPPFLAGS',
            'OBJCFLAGS',
            'LDFLAGS',
        ):
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
        """
        Used in oven.py to start a shell prompt with the correct env on recipe
        build failure
        """
        return self.env.copy()

    def _save_env_var(self, var):
        # Will only store the first 'save'.
        if var not in self._old_env:
            if var in self.env:
                self._old_env[var] = self.env[var]
            else:
                self._old_env[var] = None

    def _modify_env(self):
        """
        Modifies the build environment by inserting env vars from new_env
        """
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
        """Restores the old environment"""
        for var, val in self._old_env.items():
            if val is None:
                if var in self.env:
                    del self.env[var]
            else:
                self.env[var] = val
        self._old_env.clear()

    def maybe_add_system_libs(self, step=''):
        """
        Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
        can be found.
        """
        # Note: this is expected to be called with the environment already
        # modified using @{async_,}modify_environment

        # don't add system libs unless explicitly asked for
        if not self.use_system_libs or not self.config.allow_system_libs:
            return

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
    """
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    """

    library_type = LibraryType.BOTH
    # Whether this recipe's build system can be built with MSVC
    can_msvc = False

    def __init__(self):
        self._properties_keys = []
        # Initialize the default build dir
        # The folder where the build artifacts will be generated
        self.build_dir = os.path.abspath(os.path.join(self.config.sources, self.package_name))
        # The build dir might be different than the theoretical source dir
        Path(self.build_dir).mkdir(parents=True, exist_ok=True)
        # Initialize the default sources dir
        # The folder where the actual build system's sources are located
        self.config_src_dir = self.src_dir

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
        """
        Configures the module
        """
        raise NotImplementedError("'configure' must be implemented by subclasses")

    async def compile(self):
        """
        Compiles the module
        """
        raise NotImplementedError("'compile' must be implemented by subclasses")

    async def install(self):
        """
        Installs the module
        """
        raise NotImplementedError("'install' must be implemented by subclasses")

    def check(self):
        """
        Runs any checks on the module
        """
        pass

    def num_of_cpus(self):
        if (
            self.config.allow_parallel_build
            and getattr(self, 'allow_parallel_build', True)
            and self.config.num_of_cpus > 1
        ):
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


class MakefilesBase(Build, ModifyEnvBase):
    """
    Base class for makefiles build systems like autotools and cmake
    """

    config_sh = ''
    configure_tpl = None
    configure_options = None
    make = None
    make_install = None
    make_check = None
    make_clean = None
    allow_parallel_build = True
    srcdir = '.'
    # recipes often use shell constructs
    config_sh_needs_shell = True

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self._init_options()
        self.setup_toolchain_env_ops()
        if not self.using_msvc():
            self.setup_buildtype_env_ops()

        self.config_src_dir = os.path.abspath(os.path.join(self.src_dir, self.srcdir))
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

    def get_config_sh(self):
        return self.config_sh

    def get_configure_dir(self):
        return self.config_src_dir

    def get_make_dir(self):
        return self.build_dir

    def get_configure_cmd(self):
        substs = {
            'config-sh': self.get_config_sh(),
            'prefix': self.config.prefix,
            'libdir': self.config.libdir,
            'host': self.config.host,
            'target': self.config.target,
            'build': self.config.build,
            'options': self.configure_options,
            'build_dir': self.build_dir,
            'config_src_dir': self.config_src_dir,
        }

        configure_cmd = []
        # Construct a command list when possible
        if not self.config_sh_needs_shell:
            for arg in self.configure_tpl:
                if arg == '%(options)s':
                    for opt in self.configure_options:
                        configure_cmd.append(opt % substs)
                else:
                    configure_cmd.append(arg % substs)
        else:
            substs['options'] = ' '.join(self.configure_options)
            configure_cmd = ' '.join(self.configure_tpl) % substs
        return configure_cmd

    async def configure(self):
        """
        Base configure method

        When called from a method in deriverd class, that method has to be
        decorated with modify_environment decorator.
        """
        configure_dir = self.get_configure_dir()
        if not os.path.exists(configure_dir):
            os.makedirs(configure_dir)

        self.maybe_add_system_libs(step='configure')
        configure_cmd = self.get_configure_cmd()

        await shell.async_call(configure_cmd, configure_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def compile(self):
        make_dir = self.get_make_dir()
        if not os.path.exists(make_dir):
            os.makedirs(make_dir)

        self.maybe_add_system_libs(step='compile')
        await shell.async_call(self.make, make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='install')
        await shell.async_call(self.make_install, self.get_make_dir(), logfile=self.logfile, env=self.env)

    @modify_environment
    def clean(self):
        self.maybe_add_system_libs(step='clean')
        shell.new_call(self.make_clean, self.get_make_dir(), logfile=self.logfile, env=self.env)

    @modify_environment
    def check(self):
        if self.make_check:
            self.maybe_add_system_libs(step='check')
            shell.new_call(self.make_check, self.get_make_dir(), logfile=self.logfile, env=self.env)

    def _init_options(self):
        if isinstance(self.configure_tpl, str):
            m.deprecation(f'{self.name}: `configure_tpl` should be a list instead of a string')
            self.configure_tpl = self.configure_tpl.split()

        if not self.configure_options:
            self.configure_options = []

        if isinstance(self.configure_options, str):
            m.deprecation(f'{self.name}: `configure_options` should be a list instead of a string')
            self.configure_options = self.configure_options.split()


class Makefile(MakefilesBase):
    """
    Build handler for Makefile project
    """

    def __init__(self):
        # For a generic Makefile based project, the src dir can not be different than the build dir
        if self.src_dir != os.path.abspath(os.path.join(self.config.sources, self.package_name)):
            raise FatalError('For a Makefile based project, source and build dirs must be the same')
        # For a generic Makefile based project, the srcdir property is also set on the builddir
        MakefilesBase.__init__(self)
        self.build_dir = self.config_src_dir

    @modify_environment
    async def configure(self):
        await MakefilesBase.configure(self)


class Autotools(MakefilesBase):
    """
    Build handler for autotools project

    @cvar override_libtool: overrides ltmain.sh to generate a libtool
                            script with the one built by cerbero.
    @type override_libtool: boolean
    """

    autoreconf = False
    autoreconf_sh = 'autoreconf -f -i'
    configure_tpl = ['%(config-sh)s', '--prefix %(prefix)s', '--libdir %(libdir)s']
    add_host_build_target = True
    can_use_configure_cache = True
    supports_cache_variables = True
    disable_introspection = False
    override_libtool = True

    def __init__(self):
        MakefilesBase.__init__(self)
        self.make_check = self.make_check or ['make', 'check']

    def get_config_sh(self):
        # Use the absolute path for configure as we call it from build_dir
        return os.path.join(self.config_src_dir, 'configure')

    def get_configure_dir(self):
        return self.build_dir

    def get_make_dir(self):
        return self.build_dir

    @modify_environment
    async def configure(self):
        # Configuring an autotools project implies:
        # autoreconf_sh from self.config_src_dir
        # config_sh run from self.config_build_dir located at self.config_src_dir

        # Build with PIC for static linking
        self.configure_tpl.append('--with-pic')
        # Disable automatic dependency tracking, speeding up one-time builds
        self.configure_tpl.append('--disable-dependency-tracking')
        # Only use --disable-maintainer mode for real autotools based projects
        if os.path.exists(os.path.join(self.src_dir, 'configure.in')) or os.path.exists(
            os.path.join(self.src_dir, 'configure.ac')
        ):
            self.configure_tpl.append('--disable-maintainer-mode')
            self.configure_tpl.append('--disable-silent-rules')
            # Never build gtk-doc documentation
            self.configure_tpl.append('--disable-gtk-doc')

        # Enable or disable introspection based on configuration
        if self.config.variants.gi and not self.disable_introspection and self.use_gobject_introspection():
            self.configure_tpl.append('--enable-introspection')
        else:
            self.configure_tpl.append('--disable-introspection')

        if self.library_type == LibraryType.BOTH:
            self.configure_tpl.append('--enable-shared')
            self.configure_tpl.append('--enable-static')
        elif self.library_type == LibraryType.SHARED:
            self.configure_tpl.append('--enable-shared')
            self.configure_tpl.append('--disable-static')
        elif self.library_type == LibraryType.STATIC:
            self.configure_tpl.append('--disable-shared')
            self.configure_tpl.append('--enable-static')

        if self.autoreconf:
            await shell.async_call(self.autoreconf_sh, self.config_src_dir, logfile=self.logfile, env=self.env)

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
            find_cmd = 'find {} -maxdepth 0 -type f -name {}'.format(self.src_dir, cf)
            files = await shell.async_call_output(find_cmd, logfile=self.logfile, env=self.env)
            files = files.split('\n')
            files.remove('')
            for f in files:
                o = os.path.join(srcdir, cf)
                m.log('CERBERO: copying %s to %s' % (o, f), self.logfile)
                shutil.copy(o, f)

        if self.config.platform == Platform.WINDOWS and self.supports_cache_variables:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in self.env.items():
                if k[2:6] == '_cv_':
                    self.configure_tpl.append('%s="%s"' % (k, v))

        if self.add_host_build_target:
            if self.config.host is not None:
                self.configure_tpl.append('--host=%(host)s')
            if self.config.build is not None:
                self.configure_tpl.append('--build=%(build)s')
            if self.config.target is not None:
                self.configure_tpl.append('--target=%(target)s')

        use_configure_cache = self.config.use_configure_cache
        if self.use_system_libs and self.config.allow_system_libs:
            use_configure_cache = False

        if self._new_env:
            use_configure_cache = False

        if use_configure_cache and self.can_use_configure_cache:
            cache = os.path.join(self.config.sources, '.configure.cache')
            self.configure_tpl.append('--cache-file=%s' % cache)

        # Add at the very end to allow recipes to override defaults
        for opt in self.configure_options:
            self.configure_tpl.append(opt)

        await MakefilesBase.configure(self)


class CMake(MakefilesBase):
    """
    Build handler for cmake projects
    """

    cmake_generator = 'make'
    config_sh_needs_shell = False
    config_sh = None
    configure_tpl = [
        '%(config-sh)s',
        '-DCMAKE_INSTALL_PREFIX=%(prefix)s',
        '-B%(build_dir)s',
        '-DCMAKE_LIBRARY_OUTPUT_PATH=%(libdir)s',
        '-DCMAKE_INSTALL_BINDIR=bin',
        '-DCMAKE_INSTALL_INCLUDEDIR=include',
        '%(options)s',
        '-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_FIND_ROOT_PATH=%(prefix)s',
        '-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=true',
    ]

    def __init__(self):
        MakefilesBase.__init__(self)
        self.build_dir = os.path.join(self.build_dir, 'b')
        self.config_sh = 'cmake'
        self.configure_tpl.append(f'-DCMAKE_INSTALL_LIBDIR={self.config.rel_libdir}')
        if self.config.distro == Distro.MSYS2:
            # We do not want the MSYS2 CMake because it doesn't support MSVC
            self.config_sh = shutil.which('cmake', path=shell.get_path_minus_msys(self.env['PATH']))

    @modify_environment
    async def configure(self):
        cc = self.env.get('CC', 'gcc')
        cxx = self.env.get('CXX', 'g++')
        cflags = self.env.get('CFLAGS', '')
        cxxflags = self.env.get('CXXFLAGS', '')
        # CMake doesn't support passing "ccache $CC", but we can use
        # the CMAKE_<lang>_COMPILER_LAUNCHER environment variables.
        if self.config.use_ccache:
            cc = cc.replace('ccache', '').strip()
            cxx = cxx.replace('ccache', '').strip()
        cc = cc.split(' ')[0]
        cxx = cxx.split(' ')[0]

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
            if self.config.platform == Platform.WINDOWS and self.config.distro != Distro.MSYS:
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

        if self.config.target_platform in (Platform.DARWIN, Platform.IOS):
            self.configure_options += ['-DCMAKE_OSX_ARCHITECTURES=' + self.config.target_arch]

        # We always need a toolchain file because CMakeLists.txt requires these values to be set.
        # The Android NDK provides one, so we use that as-is.
        # This recipe uses these to decide which cpuinfo implementation to use:
        # https://github.com/libjpeg-turbo/libjpeg-turbo/blob/3.0.3/CMakeLists.txt#L92
        if self.config.target_platform == Platform.ANDROID:
            arch = self.config.target_arch
            if self.config.target_arch == Architecture.ARMv7:
                arch = 'armeabi-v7a'
            elif self.config.target_arch == Architecture.ARM64:
                arch = 'arm64-v8a'
            self.configure_options += [
                f'-DCMAKE_TOOLCHAIN_FILE={self.config.env["ANDROID_NDK_HOME"]}/build/cmake/android.toolchain.cmake',
                f'-DANDROID_ABI={arch}',
                # Required by taglib and svt-av1
                f'-DANDROID_PLATFORM={DistroVersion.get_android_api_version(self.config.target_distro_version)}',
            ]
        # A toolchain file triggers specific cross compiling logic
        # in wavpack and taglib
        elif self.config.cross_compiling():
            with open(f'{self.src_dir}/toolchain.cmake', 'w') as f:
                f.write(f'set(CMAKE_SYSTEM_NAME {system_name})\n')
                f.write(f'set(CMAKE_SYSTEM_PROCESSOR {self.config.target_arch})\n')
                if self.config.variants.mingw:
                    f.write(f'set(CMAKE_SYSROOT {self.config.toolchain_prefix}/x86_64-w64-mingw32/sysroot)\n')
            self.configure_options += [f'-DCMAKE_TOOLCHAIN_FILE={self.src_dir}/toolchain.cmake']
        elif self.config.target_platform == Platform.WINDOWS:
            self.configure_options += [
                f'-DCMAKE_SYSTEM_NAME={system_name}',
                f'-DCMAKE_SYSTEM_PROCESSOR={self.config.target_arch}',
            ]

        # FIXME: Maybe export the sysroot properly instead of doing regexp magic
        if Platform.is_apple(self.config.target_platform):
            r = re.compile(r'.*-isysroot ([^ ]+) .*')
            sysroot = r.match(cflags).group(1)
            self.configure_options += ['-DCMAKE_OSX_SYSROOT=' + sysroot]

        # Supplying these with the Android toolchain file breaks the former
        if self.config.target_platform != Platform.ANDROID:
            self.configure_options += [
                '-DCMAKE_C_COMPILER=' + cc,
                '-DCMAKE_CXX_COMPILER=' + cxx,
            ]
        self.configure_options += [
            '-DCMAKE_C_FLAGS=' + cflags,
            '-DCMAKE_CXX_FLAGS=' + cxxflags,
            '-DLIB_SUFFIX=' + self.config.lib_suffix,
        ]

        static = 'ON' if self.library_type in [LibraryType.STATIC, LibraryType.BOTH] else 'OFF'
        shared = 'ON' if self.library_type in [LibraryType.SHARED, LibraryType.BOTH] else 'OFF'
        self.configure_options += [f'-DBUILD_SHARED_LIBS={shared}', f'-DBUILD_STATIC_LIBS={static}']

        cmake_cache = os.path.join(self.build_dir, 'CMakeCache.txt')
        cmake_files = os.path.join(self.build_dir, 'CMakeFiles')
        if os.path.exists(cmake_cache):
            os.remove(cmake_cache)
        if os.path.exists(cmake_files):
            shutil.rmtree(cmake_files)
        await MakefilesBase.configure(self)


MESON_FILE_TPL = """
[host_machine]
system = '{system}'
cpu_family = '{cpu_family}'
cpu = '{cpu}'
endian = '{endian}'

[constants]
toolchain = '{toolchain}'

[built-in options]
{builtin_options}

[properties]
{extra_properties}

[binaries]
c = {CC}
cpp = {CXX}
objc = {OBJC}
objcpp = {OBJCXX}
ar = {AR}
nasm = {NASM}
pkg-config = {PKG_CONFIG}
{extra_binaries}
"""


class Meson(Build, ModifyEnvBase):
    """
    Build handler for meson project
    """

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
    meson_builddir = 'b'
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
        self.build_dir = os.path.join(self.build_dir, self.meson_builddir)

    @staticmethod
    def _get_option_value(opt_type, value):
        if opt_type == 'feature':
            return 'enabled' if value else 'disabled'
        if opt_type == 'boolean':
            return 'true' if value else 'false'
        raise AssertionError('Invalid option type {!r}'.format(opt_type))

    def _set_option(self, opt_names, variant_name):
        """
        Parse the meson_options.txt file, figure out whether any of the provided option names exist,
        figure out the type, and enable/disable it as per the cerbero configuration.
        """
        # Don't overwrite if it's already set
        if opt_names.intersection(self.meson_options):
            return
        # Error out on invalid usage
        if not os.path.isdir(self.build_dir):
            raise FatalError("Build directory doesn't exist yet?")
        # Check if the option exists, and if so, what the type is
        # https://mesonbuild.com/Build-options.html
        meson_options_files = [
            'meson_options.txt',  # For versions of meson before 1.1
            'meson.options',
        ]
        meson_options = None
        for i in meson_options_files:
            f = os.path.join(self.config_src_dir, i)
            if os.path.isfile(f):
                meson_options = f
        if not meson_options:
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
                    ty = re.search(type_regex, option, re.MULTILINE)
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
        """
        Get the toolchain configuration for the target machine. This will
        either go into a cross file or a native file depending on whether we're
        cross-compiling or not.
        """

        # Override/merge toolchain env with recipe env and return a new dict
        # with values as EnvValue objects
        build_env = self.config.get_build_env(self.env, self.using_msvc())

        cc = build_env.pop('CC')
        cxx = build_env.pop('CXX')
        objc = build_env.pop('OBJC', ['false'])
        objcxx = build_env.pop('OBJCXX', ['false'])
        ar = build_env.pop('AR')
        # We currently don't set the pre-processor or the linker when building with meson
        build_env.pop('CPP', None)
        build_env.pop('LD', None)

        builtins = {}
        builtins['c_args'] = build_env.pop('CFLAGS', [])
        builtins['cpp_args'] = build_env.pop('CXXFLAGS', [])
        builtins['objc_args'] = build_env.pop('OBJCFLAGS', [])
        builtins['objcpp_args'] = build_env.pop('OBJCXXFLAGS', [])
        # Link args
        builtins['c_link_args'] = build_env.pop('LDFLAGS', [])
        builtins['cpp_link_args'] = builtins['c_link_args']
        builtins['objc_link_args'] = build_env.pop('OBJLDFLAGS', builtins['c_link_args'])
        builtins['objcpp_link_args'] = builtins['objc_link_args']
        build_env.pop('CPP', None)  # Meson does not read this
        build_env.pop('CPPFLAGS', None)  # Meson does not read this, and it's duplicated in *FLAGS

        props = {}
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
        if self.config.cargo_home and self.config.variants.rust:
            target_triple = self.config.rust_triple(
                self.config.target_arch, self.config.target_platform, self.using_msvc()
            )
            binaries['rust'] = [self.config.cargo_home + '/bin/rustc', '--target', target_triple]

        # Try to detect build tools in the remaining env vars
        build_tool_paths = build_env['PATH'].get()
        for name, tool in build_env.items():
            # Autoconf env vars, incorrectly detected as a build tool because of 'yes'
            if '_cv_' in name:
                continue
            if name in ('EDITOR', 'SHELL', '_'):
                continue
            # Files are always executable on Windows
            if name in ('HISTFILE', 'GST_REGISTRY_1_0'):
                continue
            if tool and shutil.which(tool[0], path=build_tool_paths):
                binaries[name.lower()] = tool

        builtin_options = ''
        for k, v in builtins.items():
            builtin_options += '{} = {}\n'.format(k, str(v))

        extra_properties = ''
        for k, v in props.items():
            extra_properties += '{} = {}\n'.format(k, str(v))

        # When building cross-macos-universal on arm64, we can use Rosetta to
        # transparently run the x86_64 binaries. Inform Meson about this.
        if (
            self.config.target_platform == Platform.DARWIN
            and self.config.target_arch != self.config.arch
            and self.config.arch == Architecture.ARM64
        ):
            extra_properties += 'needs_exe_wrapper = false\n'
            if self.config.target_arch == Architecture.X86_64:
                tools = ['glib-compile-resources', 'gio-querymodules']
                pytools = ['glib-mkenums', 'glib-genmarshal', 'gdbus-codegen']
                if self.config.variants.gi:
                    tools += ['g-ir-compiler', 'g-ir-generate']
                    pytools += ['g-ir-scanner', 'g-ir-annotation-tool']
                for tool in tools:
                    binaries[tool] = [os.path.join(self.config.prefix, 'bin', tool)]
                for pytool in pytools:
                    binaries[pytool] = [self.config.python_exe, os.path.join(self.config.prefix, 'bin', pytool)]

        extra_binaries = ''
        for k, v in binaries.items():
            extra_binaries += '{} = {}\n'.format(k, str(v))

        contents = MESON_FILE_TPL.format(
            system=self.config.target_platform,
            cpu=self.config.target_arch,
            cpu_family=self._get_target_cpu_family(),
            # Assume all supported target archs are little endian
            endian='little',
            toolchain='',
            CC=cc,
            CXX=cxx,
            OBJC=objc,
            OBJCXX=objcxx,
            AR=ar,
            NASM="'nasm'",
            PKG_CONFIG="'pkg-config'",
            extra_binaries=extra_binaries,
            builtin_options=builtin_options,
            extra_properties=extra_properties,
        )
        return contents

    def _get_meson_native_file_contents(self):
        """
        Get a toolchain configuration that points to the build machine's
        toolchain. On Windows, this is the MinGW toolchain that we ship. On
        Linux and macOS, this is the system-wide compiler.
        When targetting android, we can use the NDK bundled clang compiler
        for this purpose as well.
        """
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
            cc = "toolchain / 'clang'"
            cxx = "toolchain / 'clang++'"
            ar = "toolchain / 'llvm-ar'"
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
            toolchain=self.get_env('ANDROID_NDK_TOOLCHAIN_BIN', ''),
            CC=cc,
            CXX=cxx,
            OBJC=objc,
            OBJCXX=objcxx,
            AR=ar,
            NASM="'nasm'",
            PKG_CONFIG=false,
            extra_binaries=extra_binaries,
            builtin_options='',
            extra_properties='',
        )
        return contents

    def _get_meson_dummy_file_contents(self):
        """
        Get a toolchain configuration that points to `false` for everything.
        This forces Meson to not detect a build-machine (native) compiler when
        cross-compiling.
        """
        # Tell meson to not use a native compiler for anything
        false = ['false']
        # We do not use cmake dependency files, speed up the build by disabling it
        extra_binaries = 'cmake = {}'.format(str(false))
        contents = MESON_FILE_TPL.format(
            system=self.config.platform,
            cpu=self.config.arch,
            cpu_family=self.config.arch,
            endian='little',
            toolchain='',
            CC=false,
            CXX=false,
            OBJC=false,
            OBJCXX=false,
            AR=false,
            NASM=false,
            PKG_CONFIG=false,
            extra_binaries=extra_binaries,
            builtin_options='',
            extra_properties='',
        )
        return contents

    def _write_meson_file(self, contents, fname):
        fpath = os.path.join(self.build_dir, fname)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(contents)
        return fpath

    @modify_environment
    async def configure(self):
        if os.path.exists(self.build_dir):
            # Only remove if it's not empty
            if os.listdir(self.build_dir):
                shutil.rmtree(self.build_dir)
                os.makedirs(self.build_dir)
        else:
            os.makedirs(self.build_dir)
        # Explicitly enable/disable introspection, same as Autotools
        self._set_option({'introspection', 'gir'}, 'gi')
        # Control python support using the variant
        self._set_option({'python'}, 'python')
        # Always disable gtk-doc, same as Autotools
        self._set_option({'gtk_doc'}, None)
        # Automatically disable examples
        self._set_option({'examples'}, None)

        if self.config.variants.noassert and 'b_ndebug' not in self.meson_options:
            self.meson_options['b_ndebug'] = 'true'

        # NOTE: self.tagged_for_release is set in recipes/custom.py
        is_gstreamer_recipe = hasattr(self, 'tagged_for_release')
        if is_gstreamer_recipe:
            # Enable -Werror for gstreamer recipes and when running under CI but let recipes override the value
            if self.config.variants.werror and 'werror' not in self.meson_options:
                self.meson_options['werror'] = 'true'

            if 'glib_assert' not in self.meson_options:
                self._set_option({'glib_assert'}, 'assert')

            if 'glib_checks' not in self.meson_options:
                self._set_option({'glib_checks'}, 'checks')

        debug = 'true' if self.config.variants.debug else 'false'
        opt = get_optimization_from_config(self.config)

        if self.library_type == LibraryType.NONE:
            raise RuntimeError('meson recipes cannot be LibraryType.NONE')

        meson_cmd = [
            self.meson_sh,
            'setup',
            '--prefix=' + self.config.prefix,
            '--libdir=' + self.config.rel_libdir,
            '-Ddebug=' + debug,
            '--default-library=' + self.library_type,
            '-Doptimization=' + opt,
            '--backend=' + self.meson_backend,
            '--wrap-mode=nodownload',
            '-Dpkgconfig.relocatable=true',
        ]

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

        for key, value in self.meson_options.items():
            meson_cmd += ['-D%s=%s' % (key, str(value))]

        # Set the source and build dirs
        meson_cmd += [self.build_dir, self.config_src_dir]

        # We export the target toolchain with env vars, but that confuses Meson
        # when cross-compiling (it will pick the env vars for the build
        # machine). We always set this using the cross file or native file as
        # applicable, so always unset these.
        # FIXME: We need an argument for meson that tells it to not pick up the
        # toolchain from the env.
        # https://gitlab.freedesktop.org/gstreamer/cerbero/issues/48
        self.unset_toolchain_env()

        self.maybe_add_system_libs(step='configure')
        await shell.async_call(meson_cmd, self.build_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def compile(self):
        self.maybe_add_system_libs(step='compile')
        await shell.async_call(self.make, self.build_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='install')
        await shell.async_call(self.make_install, self.build_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def clean(self):
        self.maybe_add_system_libs(step='clean')
        shell.new_call(self.make_clean, self.build_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def check(self):
        self.maybe_add_system_libs(step='check')
        shell.new_call(self.make_check, self.build_dir, logfile=self.logfile, env=self.env)


class Cargo(Build, ModifyEnvBase):
    """
    Cargo build system recipes

    NOTE: Currently only intended for build-tools recipes
    """

    srcdir = '.'
    can_msvc = True
    cargo_features = None
    cargo_packages = None
    workspace_member = None

    def __init__(self):
        self.cargo_features = self.cargo_features or []
        self.cargo_packages = self.cargo_packages or []

        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self.setup_toolchain_env_ops()
        if not self.using_msvc():
            self.setup_buildtype_env_ops()

        self.config_src_dir = os.path.abspath(os.path.join(self.src_dir, self.srcdir))
        self.build_dir = os.path.join(self.build_dir, '_builddir')
        self.cargo = os.path.join(self.config.cargo_home, 'bin', 'cargo' + self.config._get_exe_suffix())

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
            self.target_triple = self.config.rust_triple(
                self.config.target_arch, self.config.target_platform, self.using_msvc()
            )
        except FatalError as e:
            raise InvalidRecipeError(self.name, e.msg)

        self.cargo_args = [
            '--verbose',
            '--offline',
            '--target',
            self.target_triple,
            '--target-dir',
            self.build_dir,
        ]

        jobs = self.num_of_cpus()
        if jobs:
            self.cargo_args += [f'-j{jobs}']

        # https://github.com/lu-zero/cargo-c/issues/278
        if Platform.is_mobile(self.config.target_platform):
            self.library_type = LibraryType.STATIC

    def num_of_cpus(self):
        cpus = self.config.cargo_build_jobs
        if not cpus:
            cpus = self.config.num_of_cpus
        if self.config.allow_parallel_build and getattr(self, 'allow_parallel_build', True):
            return min(default_cargo_build_jobs(), cpus)
        return 1

    def get_cargo_args(self):
        args = self.cargo_args[:]
        if self.cargo_features:
            args += ['--features=' + ','.join(self.cargo_features)]
        for package in self.cargo_packages:
            args += ['-p', package]
        return args

    def append_config_toml(self, s):
        dot_cargo = os.path.join(self.src_dir, '.cargo')
        os.makedirs(dot_cargo, exist_ok=True)
        # Append so we don't overwrite cargo vendor settings
        with open(os.path.join(dot_cargo, 'config.toml'), 'a') as f:
            f.write(s)

    def get_llvm_tool(self, tool: str) -> Path:
        """
        Gets one of the LLVM tools matching the current Rust toolchain.
        """
        root_dir = shell.check_output(['rustc', '--print', 'sysroot'], env=self.env).strip()

        tools = list(Path(root_dir).glob(f'**/{tool}'))

        if len(tools) == 0:
            raise FatalError(f'Rust {tool} tool not found at {root_dir}, try re-running bootstrap')
        return tools[0]

    def get_cargo_toml_version(self):
        tomllib = self.config.find_toml_module()
        if not tomllib:
            raise FatalError('toml module not found, try re-running bootstrap')
        with open(os.path.join(self.src_dir, 'Cargo.toml'), 'r', encoding='utf-8') as f:
            data = tomllib.loads(f.read())
        if 'workspace' in data:
            return data['workspace']['package']['version']
        return data['package']['version']

    async def configure(self):
        if os.path.exists(self.build_dir):
            # Only remove if it's not empty
            if os.listdir(self.build_dir):
                shutil.rmtree(self.build_dir)
                os.makedirs(self.build_dir)
        else:
            os.makedirs(self.build_dir)

        # TODO: Ideally we should strip while packaging, not while linking
        if self.rustc_debuginfo == 'strip':
            s = '\n[profile.release]\nstrip = "debuginfo"\n'
            self.append_config_toml(s)
        else:
            s = '\n[profile.release]\nsplit-debuginfo = "packed"\n'
            self.append_config_toml(s)

        if self.using_msvc() and self.library_type != LibraryType.SHARED:
            # Thin out Rust-generated staticlibs
            self.append_config_toml('opt-level = "s"\n')
            # Thin out embedded debuginfo in the .objs
            self.append_config_toml('debug = 1\n')
            # Trim codegen units to aid in prelinking
            self.append_config_toml('lto = "thin"\n')
            self.append_config_toml('codegen-units = 1\n')

        if self.config.target_platform == Platform.ANDROID:
            # Use the compiler's forwarding
            # See https://android.googlesource.com/platform/ndk/+/master/docs/BuildSystemMaintainers.md#linkers
            linker = self.get_env('RUSTC_LINKER')
            link_args = []
            # We need to extract necessary linker flags from LDFLAGS which is
            # passed to the compiler
            for arg in shlex.split(self.get_env('LDFLAGS', '')):
                link_args += ['-C', f'link-arg={arg}']
            s = f'[target.{self.target_triple}]\nlinker = "{linker}"\nrustflags = {link_args!r}\n'
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
        if self.workspace_member:
            path = os.path.join(self.src_dir, self.workspace_member)
        else:
            path = self.src_dir
        cmd = [
            self.cargo,
            'install',
            '--path',
            path,
            '--root',
            self.config.prefix,
        ] + self.get_cargo_args()
        await self.retry_run(shell.async_call, cmd, logfile=self.logfile, env=self.env)


class CargoC(Cargo):
    """
    Cargo-C build system recipes
    """

    srcdir = '.'

    def __init__(self):
        Cargo.__init__(self)

        # cargo-c ignores config.toml's rustflags, which are necessary for i386
        # cross-build
        self.target_triple = self.config.rust_triple(
            self.config.target_arch, self.config.target_platform, self.using_msvc()
        )
        if self.target_triple == 'i686-pc-windows-gnu':
            tgt = self.target_triple.upper().replace('-', '_')
            self.set_env(f'CARGO_TARGET_{tgt}_LINKER', self.get_env('RUSTC_LINKER'))
            link_args = []
            for arg in shlex.split(self.get_env('RUSTC_LDFLAGS')):
                link_args += ['-C', f'link-arg={arg}']
            self.set_env('RUSTFLAGS', ' '.join(link_args))

    def get_cargoc_args(self):
        cargoc_args = [
            '--release',
            '--frozen',
            '--prefix',
            self.config.prefix,
            '--libdir',
            self.config.libdir,
        ]
        # --library-type args do not override, but are collected
        if self.library_type in (LibraryType.STATIC, LibraryType.BOTH):
            cargoc_args += ['--library-type', 'staticlib']
        if self.library_type in (LibraryType.SHARED, LibraryType.BOTH):
            cargoc_args += ['--library-type', 'cdylib']

        if self.config.variants.noassert:
            cargoc_args += ['--config', 'debug-assertions=false']
        if self.config.variants.nochecks:
            cargoc_args += ['--config', 'overflow-checks=false']

        cargoc_args += self.get_cargo_args()
        return cargoc_args

    @modify_environment
    async def compile(self):
        self.maybe_add_system_libs(step='configure+compile')
        cmd = [self.cargo, 'cbuild'] + self.get_cargoc_args()
        await self.retry_run(shell.async_call, cmd, self.build_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='configure+install')
        cmd = [self.cargo, 'cinstall'] + self.get_cargoc_args()
        await self.retry_run(shell.async_call, cmd, self.build_dir, logfile=self.logfile, env=self.env)


class BuildType(object):
    CUSTOM = CustomBuild
    MAKEFILE = Makefile
    AUTOTOOLS = Autotools
    CMAKE = CMake
    MESON = Meson
    CARGO = Cargo
    CARGO_C = CargoC
