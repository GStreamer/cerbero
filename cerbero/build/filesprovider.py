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
import shutil
import inspect
from functools import partial
import shlex
from pathlib import Path

from cerbero.config import Platform, LibraryType
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.errors import FatalError
from cerbero.build.build import BuildType


def find_shlib_regex(config, libname, prefix, libdir, ext, regex):
    # Use globbing to find all files that look like they might match
    # this library to narrow down our exact search
    fpath = os.path.join(libdir, '*{0}*{1}*'.format(libname, ext))
    found = glob.glob(os.path.join(prefix, fpath))
    # Find which of those actually match via an exact regex
    # Ideally Python should provide a function for regex file 'globbing'
    matches = []
    for each in found:
        fname = os.path.basename(each)
        if re.match(regex.format(re.escape(libname)), fname):
            matches.append(os.path.join(libdir, fname))
    return matches


def get_implib_dllname(config, path):
    if config.msvc_env_for_toolchain and path.endswith('.lib'):
        lib_exe = shutil.which('lib', path=config.msvc_env_for_toolchain['PATH'].get())
        if not lib_exe:
            raise FatalError('lib.exe not found, check cerbero configuration')
        try:
            ret = shell.check_output([lib_exe, '-list', path], env=config.env)
        except FatalError:
            return 0
        # The last non-empty line should contain the dllname
        return ret.split('\n')[-2]
    dlltool = config.env.get('DLLTOOL', None)
    if not dlltool:
        raise FatalError('dlltool not found, check cerbero configuration')
    try:
        return shell.check_output(shlex.split(dlltool) + ['-I', path], env=config.env)
    except FatalError:
        return 0


def find_dll_implib(config, libname, prefix, libdir, ext, regex):
    implibdir = 'lib'
    implibs = ['lib{}.dll.a'.format(libname), libname + '.lib', 'lib{}.lib'.format(libname)]
    implib_notfound = []
    for implib in implibs:
        path = os.path.join(prefix, implibdir, implib)
        if not os.path.exists(path):
            implib_notfound.append(implib)
            continue
        dllname = get_implib_dllname(config, path)
        if dllname == 0:
            continue
        dllname = dllname.strip()
        if dllname == '':
            continue
        return [os.path.join(libdir, dllname)]
    # If import libraries aren't found, look for a DLL by exactly the specified
    # name. This is to cover cases like libgcc_s_sjlj-1.dll which don't have an
    # import library since they're only used at runtime.
    dllname = 'lib{}.dll'.format(libname)
    path = os.path.join(prefix, libdir, dllname)
    if os.path.exists(path):
        return [os.path.join(libdir, dllname)]
    if len(implib_notfound) == len(implibs):
        m.warning('No import libraries found for {!r}'.format(libname))
    else:
        implibs = ', '.join(set(implibs) - set(implib_notfound))
        m.warning('No dllname found from implibs: {}'.format(implibs))
    # This will trigger an error in _list_libraries()
    return []


def find_pdb_implib(config, libname, prefix):
    dlls = find_dll_implib(config, libname, prefix, 'bin', None, None)
    pdbs = []
    for dll in dlls:
        pdb = dll[:-3] + 'pdb'
        if os.path.exists(os.path.join(prefix, pdb)):
            pdbs.append(pdb)
    return pdbs


class FilesProvider(object):
    """
    List files by categories using class attributes named files_$category and
    platform_files_$category
    """

    LIBS_CAT = 'libs'
    BINS_CAT = 'bins'
    PY_CAT = 'python'
    # devel is implemented as "all files that aren't in any other category"
    DEVEL_CAT = 'devel'
    LANG_CAT = 'lang'
    TYPELIB_CAT = 'typelibs'
    # DLLs can be named anything, there may not be any correlation between that
    # and the import library (which is actually used while linking), so don't
    # try to use a regex. Instead, get the dll name from the import library.
    _DLL_REGEX = None
    # UNIX shared libraries can have between 0 and 3 version components:
    # major, minor, micro. We don't use {m,n} here because we want to capture
    # all the matches.
    _ANDROID_SO_REGEX = r'^lib{}\.so(\.[0-9]+)?(\.[0-9]+)?(\.[0-9]+)?$'
    # Like _ANDROID_SO_REGEX but only libs with version number.
    _LINUX_SO_REGEX = r'^lib{}\.so(\.[0-9]+)(\.[0-9]+)?(\.[0-9]+)?$'
    _DYLIB_REGEX = r'^lib{}(\.[0-9]+)?(\.[0-9]+)?(\.[0-9]+)?\.dylib$'

    # Extension Glob Legend:
    # bext = binary extension
    # sext = shared library matching regex
    # srext = shared library extension (no regex)
    # sdir = shared library directory
    # mext = module (plugin) extension
    # smext = static module (plugin) extension
    # pext = python module extension (.pyd on Windows)
    # libdir = relative libdir path (lib, lib64, lib/i386-linux-gnu)
    EXTENSIONS = {
        Platform.WINDOWS: {
            'bext': '.exe',
            'sregex': _DLL_REGEX,
            'mext': '.dll',
            'smext': '.a',
            'pext': '.pyd',
            'srext': '.dll',
        },
        Platform.LINUX: {
            'bext': '',
            'sregex': _LINUX_SO_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.so',
        },
        Platform.ANDROID: {
            'bext': '',
            'sregex': _ANDROID_SO_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.so',
        },
        Platform.DARWIN: {
            'bext': '',
            'sregex': _DYLIB_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.dylib',
        },
        Platform.IOS: {
            'bext': '',
            'sregex': _DYLIB_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.dylib',
        },
    }

    # Match static gstreamer plugins, GIO modules, etc.
    _FILES_STATIC_PLUGIN_REGEX = re.compile(r'lib/.+/lib(gst|)([^/.]+)\.a')

    def __init__(self, config):
        self.config = config
        self.platform = config.target_platform
        self.extensions = self.EXTENSIONS[self.platform].copy()
        self.extensions['pydir'] = config.py_prefix
        self.extensions['pyplatdir'] = config.py_plat_prefix
        self.extensions['libdir'] = self.config.rel_libdir
        if self.platform == Platform.WINDOWS:
            self.extensions['sdir'] = 'bin'
        else:
            self.extensions['sdir'] = self.extensions['libdir']
        if self._dylib_plugins():
            self.extensions['mext'] = '.dylib'
        self._findlibfunc = None
        if self.extensions['sregex']:
            self._findlibfunc = find_shlib_regex
        elif self.config.target_platform == Platform.WINDOWS:
            self._findlibfunc = find_dll_implib
        else:
            raise AssertionError
        self.py_prefixes = config.py_prefixes
        self.add_files_bins_devel()
        self.add_license_files()
        self.update_categories()
        self._listfuncs = {
            self.LIBS_CAT: self._list_libraries,
            self.BINS_CAT: self._list_binaries,
            self.PY_CAT: self._list_pyfiles,
            self.LANG_CAT: self._list_langfiles,
            self.TYPELIB_CAT: self._list_typelibfiles,
            'default': self._list_files,
        }

    def _search_file(self, file):
        """
        Search for arbitrary files doing the extension replacements, globbing, and listing
        directories
        """
        # fill directories
        if os.path.isdir(os.path.join(self.config.prefix, file)):
            found = self._ls_dir(os.path.join(self.config.prefix, file))
        else:
            found = shell.ls_files([file], self.config.prefix)
        return found

    def _search_library(self, file):
        """
        Search libraries in the prefix. Unfortunately the filename might vary
        depending on the platform and we need to match the library name and
        it's extension. There is a corner case on windows where the DLL might
        have any name, so we search for the .lib or .dll.a import library
        and get the DLL name from that.
        """
        libdir = self.extensions['sdir']
        libext = self.extensions['srext']
        libregex = self.extensions['sregex']
        f = os.path.basename(file)
        # Extract the libname again. This might be redundant, but it is done
        # like this to avoid changing all the library search implementations
        pattern = r'\*?(?P<libname>[^\*]*)\*?{}\*?'.format(libext)
        m = re.match(pattern, f)
        f = m.group('libname')
        libsmatch = self._findlibfunc(self.config, f[3:], self.config.prefix, libdir, libext, libregex)
        return libsmatch

    def _search_library_pdb(self, file):
        f = os.path.basename(file)
        pdbs = find_pdb_implib(self.config, f[:-4], self.config.prefix)
        return pdbs

    def _validate_existing(self, files, only_existing=True):
        if not only_existing:
            nonvalidated = []
            for each in files:
                nonvalidated.append(each)
            return nonvalidated

        # Validate all the files with the ones in the prefix
        vfs = []
        for f, searchfunc in files.items():
            if not searchfunc:
                searchfunc = self._search_file
            validated = searchfunc(f)
            # Warn about missing files
            if not validated:
                m.warning('Missing on-disk files for {} with search function {}'.format(f, searchfunc.__name__))
            else:
                vfs.extend(validated)
        return vfs

    def _dylib_plugins(self):
        if self.btype not in (BuildType.MESON, BuildType.CARGO_C):
            return False
        if self.platform not in (Platform.DARWIN, Platform.IOS):
            return False
        # gstreamer plugins on macOS and iOS use the .dylib extension when
        # built with Meson but modules that use GModule do not
        if not self.name.startswith('gst') and self.name != 'libnice':
            return False
        return True

    def have_pdbs(self):
        if not self.using_msvc():
            return False
        if self.config.variants.nodebug:
            return False
        if self.library_type in (LibraryType.STATIC, LibraryType.NONE):
            return False
        # https://github.com/lu-zero/cargo-c/issues/279
        if issubclass(self.btype, BuildType.CARGO):
            return False
        return True

    def add_license_files(self):
        """
        Ensure that all license files are packaged
        """
        if not hasattr(self, 'files_devel'):
            self.files_devel = []
        if self.licenses or getattr(self, 'licenses_bins', None):
            self.files_devel.append('share/licenses/{}'.format(self.name))

    def add_files_bins_devel(self):
        """
        When a recipe is built with MSVC, all binaries have a corresponding
        .pdb file that must be included in the devel package. This files list
        is identical to `self.files_bins`, so we duplicate it here into a devel
        category. It will get included via the 'default' search function.
        """
        if not self.have_pdbs():
            return
        pdbs = []
        if hasattr(self, 'files_bins'):
            for f in self.files_bins:
                pdbs.append('bin/{}.pdb'.format(f))
        if hasattr(self, 'platform_files_bins'):
            for f in self.platform_files_bins.get(self.config.target_platform, []):
                pdbs.append('bin/{}.pdb'.format(f))
        if not hasattr(self, 'files_bins_devel'):
            self.files_bins_devel = []
        self.files_bins_devel += pdbs

    def devel_files_list(self, only_existing=True):
        """
        Return the list of development files, which consists in the files and
        directories listed in the 'devel' category and the link libraries .a,
        .la and .so from the 'libs' category
        """
        devfiles = {}
        devfiles.update(self._list_files_by_category(self.DEVEL_CAT))
        devfiles.update(self._list_girfiles())
        devfiles.update(self._list_devel_libraries())
        devfiles = self._validate_existing(devfiles, only_existing)
        return sorted(list(set(devfiles)))

    def dist_files_list(self, only_existing=True):
        """
        Return the list of files that should be included in a distribution
        tarball, which include all files except the development files
        """

        distfiles = {}
        for x in self.categories:
            if x.endswith(self.DEVEL_CAT):
                continue
            distfiles.update(self._list_files_by_category(x))
        distfiles = self._validate_existing(distfiles, only_existing)
        return sorted(list(set(distfiles)))

    def files_list(self, only_existing=True):
        """
        Return the complete list of files
        """
        files = self.dist_files_list(only_existing)
        files.extend(self.devel_files_list(only_existing))
        return sorted(list(set(files)))

    def files_list_by_categories(self, categories, only_existing=True):
        """
        Return the list of files in a list categories
        """
        files = {}
        for cat in categories:
            cat_files = self._list_files_by_category(cat)
            files.update(cat_files)
        files = self._validate_existing(files, only_existing)
        return sorted(list(set(files)))

    def files_list_by_category(self, category, only_existing=True):
        """
        Return the list of files in a given category
        """
        return self.files_list_by_categories([category], only_existing)

    def libraries(self):
        """
        Return a dict of the library names and library paths
        """
        libraries = {}
        files = self._list_files_by_category(self.LIBS_CAT)
        for f, searchfunc in files.items():
            if not searchfunc:
                searchfunc = self._search_file
            start = len(self.extensions['sdir']) + 1 + 3
            end = len(self.extensions['srext'])
            if self.extensions['sregex']:
                start += 1
                end += 2
            libname = f[start:-end]
            libraries[libname] = searchfunc(f)
        return libraries

    def use_gobject_introspection(self):
        return self.TYPELIB_CAT in self._files_categories()

    def update_categories(self):
        self.categories = self._files_categories()

    def _files_categories(self):
        """Get the list of categories available"""
        categories = []
        for name, value in inspect.getmembers(self):
            if not isinstance(value, (dict, list)):
                continue
            if name.startswith('files_'):
                categories.append(name.split('files_')[1])
            if name.startswith('platform_files_'):
                categories.append(name.split('platform_files_')[1])
        return sorted(list(set(categories)))

    def _get_category_files_list(self, category):
        """
        Get the raw list of files in a category, without pattern match nor
        extensions replacement, which should be done in the search function
        """
        files = []
        for attr in dir(self):
            if attr.startswith('files_') and attr.endswith('_' + category):
                files.extend(getattr(self, attr))
            if attr.startswith('platform_files_') and attr.endswith('_' + category):
                files.extend(getattr(self, attr).get(self.platform, []))
        return files

    def _list_files_by_category(self, category):
        search_category = category
        if category.startswith(self.LIBS_CAT + '_'):
            search_category = self.LIBS_CAT
        search = self._listfuncs.get(search_category, self._listfuncs['default'])
        return search(self._get_category_files_list(category))

    @staticmethod
    def _get_msvc_dll(f):
        f = Path(f)
        return str(f.with_name(f.name[3:]))

    @staticmethod
    def _get_plugin_pc(f):
        f = Path(f)
        return str(f.parent / 'pkgconfig' / (f.name[3:-3] + '.pc'))

    def _list_files(self, files):
        """
        List plugin files and arbitrary files in the prefix

        FIXME: Curently plugins are also searched using this, but there should
        be a separate system for those.
        """
        # replace extensions
        files_expanded = []
        for f in files:
            # Don't add shared plugin files when building only static plugins
            if '%(mext)s' in f and self.library_type == LibraryType.STATIC:
                continue
            files_expanded.append(f % self.extensions)
        fs = {}
        for f in files_expanded:
            if f.endswith('.dll') and self.using_msvc():
                fs[self._get_msvc_dll(f)] = None
            else:
                fs[f] = None
            # Look for a PDB file and add it
            if self.have_pdbs():
                # We try to find a pdb file corresponding to the plugin's .a
                # file instead of the .dll because we want it to go into the
                # devel package, not the runtime package.
                m = self._FILES_STATIC_PLUGIN_REGEX.match(f)
                if m:
                    # Plugin DLLs are required to be foo.dll when the recipe uses MSVC, and
                    # will be in the same directory as the .a static plugin/library
                    fdir = os.path.dirname(f)
                    pdb = '{}/{}.pdb'.format(fdir, ''.join(m.groups()))
                    fs[pdb] = None
            # For plugins, the .la file is generated using the .pc file, but we
            # don't add the .pc to files_devel. It has the same name, so we can
            # add it using the .la entry.
            if f.startswith(self.extensions['libdir'] + '/gstreamer-1.0/') and f.endswith('.la'):
                fs[self._get_plugin_pc(f)] = None

        return fs

    def _list_binaries(self, files):
        """
        List binaries in the prefix. This function preprends the bin/ path and add the binary
        extension to the given list of files
        """
        binaries = {}
        for f in files:
            b = 'bin/%(file)s%(bext)s' % {'file': f, **self.extensions}
            binaries[b] = None
        return binaries

    def _list_libraries(self, files):
        if self.library_type == LibraryType.STATIC:
            return {}
        libs = {}
        for f in files:
            if self.extensions['sregex']:
                pattern = '%(sdir)s/*%(file)s*%(srext)s*'
            else:
                pattern = '%(sdir)s/%(file)s%(srext)s'
            pattern = pattern % {'file': f, **self.extensions}
            libs[pattern] = self._search_library
        return libs

    def _pyfile_get_name(self, f):
        if os.path.exists(os.path.join(self.config.prefix, f)):
            return f
        for py_prefix in self.py_prefixes:
            pydir = os.path.basename(os.path.normpath(py_prefix))
            pyversioname = re.sub(r'python|\.', '', pydir)
            cpythonname = 'cpython-' + pyversioname

            splitedext = os.path.splitext(f)
            for ex in ['', 'm']:
                f = splitedext[0] + '.' + cpythonname + ex + splitedext[1]
                if os.path.exists(os.path.join(self.config.prefix, f)):
                    return f
        return None

    def _pyfile_get_cached(self, f):
        pyfiles = []
        pycachedir = os.path.join(os.path.dirname(f), '__pycache__')
        for e in ['o', 'c']:
            fe = self._pyfile_get_name(f + e)
            if fe:
                pyfiles.append(fe)
            else:
                cached = os.path.join(pycachedir, os.path.basename(f))
                fe = self._pyfile_get_name(os.path.join(self.config.prefix, cached))
                if fe:
                    pyfiles.append(fe)

        return pyfiles

    def _list_pyfiles(self, files):
        """
        List python files in the prefix. This function preprends the
        lib/Python$PYVERSION/site-packages/ path to the given list of files
        """
        pyfiles = {}
        files_exts = [f % self.extensions for f in files]
        files = self._list_files(files_exts)
        for f in files:
            real_name = self._pyfile_get_name(f)
            if real_name:
                pyfiles[real_name] = None
            else:
                # Adding it so we notice there is a problem in the recipe
                pyfiles[f] = None
            if f.endswith('.py'):
                cached_files = self._pyfile_get_cached(f)
                for cached_file in cached_files:
                    pyfiles[cached_file] = None
        return pyfiles

    def _list_langfiles(self, files):
        """
        List translations in share/locale/*/LC_MESSAGES/ '
        """
        pattern = 'share/locale/*/LC_MESSAGES/%s.mo'
        langfiles = {}
        for x in files:
            f = pattern % x
            langfiles[f] = None
        return langfiles

    def _list_typelibfiles(self, files):
        """
        List typelibs in lib/girepository-1.0/
        """
        if not self.config.variants.gi:
            return {}

        pattern = '{}/girepository-1.0/%s.typelib'.format(self.extensions['libdir'])
        typelibs = {}
        for x in files:
            file = pattern % x
            typelibs[file] = None
        return typelibs

    def _list_girfiles(self):
        """
        List gir files in share/gir-1.0/
        """
        if not self.config.variants.gi:
            return {}

        girs = []
        if hasattr(self, 'files_' + self.TYPELIB_CAT):
            girs += getattr(self, 'files_' + self.TYPELIB_CAT)
        if hasattr(self, 'platform_files_' + self.TYPELIB_CAT):
            d = getattr(self, 'platform_files_' + self.TYPELIB_CAT)
            girs += d.get(self.config.target_platform, [])

        files = {}
        # Use a * for the arch in universal builds
        pattern = 'share/gir-1.0/%s.gir'
        for gir in girs:
            file = pattern % gir
            files[file] = None
        return files

    def _list_devel_libraries(self):
        if self.runtime_dep:
            return {}

        devel_libs = {}
        for category in self.categories:
            if category != self.LIBS_CAT and not category.startswith(self.LIBS_CAT + '_'):
                continue

            patterns = []
            if self.library_type != LibraryType.NONE:
                patterns.append('%(libdir)s/%(f)s.la')

            if self.library_type in (LibraryType.BOTH, LibraryType.STATIC):
                patterns.append('%(libdir)s/%(f)s.a')

            if self.library_type in (LibraryType.BOTH, LibraryType.SHARED):
                if self.platform == Platform.LINUX:
                    patterns.append('%(libdir)s/%(f)s.so')
                elif self.platform == Platform.WINDOWS:
                    patterns.append('%(libdir)s/%(f)s.dll.a')
                    patterns.append('%(libdir)s/%(fnolib)s.def')
                    patterns.append('%(libdir)s/%(fnolib)s.lib')
                elif self.platform in [Platform.DARWIN, Platform.IOS]:
                    patterns.append('%(libdir)s/%(f)s.dylib')

            for x in self._get_category_files_list(category):
                for pattern in patterns:
                    file = pattern % {'f': x, 'fnolib': x[3:], 'libdir': self.extensions['libdir']}
                    devel_libs[file] = None
                # PDB names are derived from DLL library names (which are
                # arbitrary), so we must use the same search function for them.
                if self.have_pdbs():
                    pdb = '%(sdir)s/%(f)s.pdb' % {'f': x[3:], **self.extensions}
                    devel_libs[pdb] = self._search_library_pdb

        return devel_libs

    def _ls_dir(self, dirpath):
        files = []
        for root, dirnames, filenames in os.walk(dirpath):
            _root = root.split(self.config.prefix)[1]
            if _root[0] == '/':
                _root = _root[1:]
            files.extend([os.path.join(_root, x) for x in filenames])
        return files


class UniversalFilesProvider(FilesProvider):
    wrapped_list_funcs = ['devel_files_list', 'dist_files_list', 'files_list_by_categories']

    def __init__(self, config):
        # Override all public functions that return a list of files.
        for name in dir(FilesProvider):
            if name not in self.wrapped_list_funcs:
                continue
            setattr(self, name, partial(self._aggregate_files_list_func, name))
        self.config = config

    def _aggregate_files_list_func(self, funcname, *args):
        files = []
        for r in self._recipes.values():
            func = getattr(r, funcname)
            rfiles = func(*args)
            for rf in rfiles:
                f = self.get_arch_file(r.config.target_arch, rf)
                files.append(f)
        return files

    def get_arch_file(self, arch, f):
        """
        Layout is split into separate arch-specific prefixes (android-universal)
        """
        return '{}/{}'.format(arch, f)


class UniversalMergedFilesProvider(UniversalFilesProvider):
    def get_arch_file(self, arch, f):
        """
        Layout is one common prefix will all arch-specific files merged into it
        with `lipo` (ios-universal)
        """
        return f
