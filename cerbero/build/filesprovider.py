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
from pathlib import Path

from cerbero.config import Platform, LibraryType
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.errors import FatalError

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
    if config.msvc_toolchain_env and path.endswith('.lib'):
        lib_exe = shutil.which('lib', path=config.msvc_toolchain_env['PATH'][0])
        if not lib_exe:
            raise FatalError('lib.exe not found, check cerbero configuration')
        try:
            ret = shell.check_output([lib_exe, '-list', path])
        except FatalError:
            return 0
        # The last non-empty line should contain the dllname
        return ret.split('\n')[-2]
    dlltool = os.environ.get('DLLTOOL', None)
    if not dlltool:
        raise FatalError('dlltool not found, check cerbero configuration')
    try:
        return shell.check_output([dlltool, '-I', path])
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
        m.warning("No import libraries found for {!r}".format(libname))
    else:
        implibs = ', '.join(set(implibs) - set(implib_notfound))
        m.warning("No dllname found from implibs: {}".format(implibs))
    # This will trigger an error in _search_libraries()
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
    '''
    List files by categories using class attributes named files_$category and
    platform_files_$category
    '''

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
    _SO_REGEX = r'^lib{}\.so(\.[0-9]+)?(\.[0-9]+)?(\.[0-9]+)?$'
    _DYLIB_REGEX = r'^lib{}(\.[0-9]+)?(\.[0-9]+)?(\.[0-9]+)?\.dylib$'

    # Extension Glob Legend:
    # bext = binary extension
    # sext = shared library matching regex
    # srext = shared library extension (no regex)
    # sdir = shared library directory
    # mext = module (plugin) extension
    # smext = static module (plugin) extension
    # pext = python module extension (.pyd on Windows)
    EXTENSIONS = {
        Platform.WINDOWS: {'bext': '.exe', 'sregex': _DLL_REGEX, 'sdir': 'bin',
            'mext': '.dll', 'smext': '.a', 'pext': '.pyd', 'srext': '.dll'},
        Platform.LINUX: {'bext': '', 'sregex': _SO_REGEX, 'sdir': 'lib',
            'mext': '.so', 'smext': '.a', 'pext': '.so', 'srext': '.so'},
        Platform.ANDROID: {'bext': '', 'sregex': _SO_REGEX, 'sdir': 'lib',
            'mext': '.so', 'smext': '.a', 'pext': '.so', 'srext': '.so'},
        Platform.DARWIN: {'bext': '', 'sregex': _DYLIB_REGEX, 'sdir': 'lib',
            'mext': '.so', 'smext': '.a', 'pext': '.so', 'srext': '.dylib'},
        Platform.IOS: {'bext': '', 'sregex': _DYLIB_REGEX, 'sdir': 'lib',
            'mext': '.so', 'smext': '.a', 'pext': '.so', 'srext': '.dylib'}}

    def __init__(self, config):
        self.config = config
        self.platform = config.target_platform
        self.extensions = self.EXTENSIONS[self.platform].copy()
        if self._dylib_plugins():
            self.extensions['mext'] = '.dylib'
        self.py_prefix = config.py_prefix
        self.add_files_bins_devel()
        self.add_license_files()
        self.categories = self._files_categories()
        self._searchfuncs = {self.LIBS_CAT: self._search_libraries,
                             self.BINS_CAT: self._search_binaries,
                             self.PY_CAT: self._search_pyfiles,
                             self.LANG_CAT: self._search_langfiles,
                             self.TYPELIB_CAT: self._search_typelibfiles,
                             'default': self._search_files}

    def _dylib_plugins(self):
        from cerbero.build.build import BuildType
        if self.btype != BuildType.MESON:
            return False
        if self.platform not in (Platform.DARWIN, Platform.IOS):
            return False
        # gstreamer plugins on macOS and iOS use the .dylib extension when
        # built with Meson but modules that use GModule do not
        if not self.name.startswith('gst') and self.name != 'libnice':
            return False
        return True

    def add_license_files(self):
        '''
        Ensure that all license files are packaged
        '''
        if not hasattr(self, 'files_devel'):
            self.files_devel = []
        if self.licenses or getattr(self, 'licenses_bins', None):
            self.files_devel.append('share/licenses/{}'.format(self.name))

    def add_files_bins_devel(self):
        '''
        When a recipe is built with MSVC, all binaries have a corresponding
        .pdb file that must be included in the devel package. This files list
        is identical to `self.files_bins`, so we duplicate it here into a devel
        category. It will get included via the 'default' search function.
        '''
        if not self.using_msvc():
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

    def devel_files_list(self):
        '''
        Return the list of development files, which consists in the files and
        directories listed in the 'devel' category and the link libraries .a,
        .la and .so from the 'libs' category
        '''
        devfiles = self.files_list_by_category(self.DEVEL_CAT)
        devfiles.extend(self._search_girfiles())
        devfiles.extend(self._search_devel_libraries())

        return sorted(list(set(devfiles)))

    def dist_files_list(self):
        '''
        Return the list of files that should be included in a distribution
        tarball, which include all files except the development files
        '''

        return self.files_list_by_categories(
            [x for x in self.categories if not x.endswith(self.DEVEL_CAT)])

    def files_list(self):
        '''
        Return the complete list of files
        '''
        files = self.dist_files_list()
        files.extend(self.devel_files_list())
        return sorted(list(set(files)))

    def files_list_by_categories(self, categories):
        '''
        Return the list of files in a list categories
        '''
        files = []
        for cat in categories:
            cat_files = self._list_files_by_category(cat)
            # The library search function returns a dict that is a mapping from
            # library name to filenames, but we only want a list of filenames
            if isinstance(cat_files, dict):
                for each in cat_files.values():
                    files.extend(each)
            else:
                files.extend(cat_files)
        return sorted(list(set(files)))

    def files_list_by_category(self, category):
        '''
        Return the list of files in a given category
        '''
        return self.files_list_by_categories([category])

    def libraries(self):
        '''
        Return a dict of the library names and library paths
        '''
        return self._list_files_by_category(self.LIBS_CAT)

    def use_gobject_introspection(self):
        return self.TYPELIB_CAT in self._files_categories()

    def _files_categories(self):
        ''' Get the list of categories available '''
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
        '''
        Get the raw list of files in a category, without pattern match nor
        extensions replacement, which should be done in the search function
        '''
        files = []
        for attr in dir(self):
            if attr.startswith('files_') and attr.endswith('_' + category):
                files.extend(getattr(self, attr))
            if attr.startswith('platform_files_') and \
                    attr.endswith('_' + category):
                files.extend(getattr(self, attr).get(self.platform, []))
        return files

    def _list_files_by_category(self, category):
        search_category = category
        if category.startswith(self.LIBS_CAT + '_'):
            search_category = self.LIBS_CAT
        search = self._searchfuncs.get(search_category,
                                       self._searchfuncs['default'])
        return search(self._get_category_files_list(category))

    def _find_plugin_dll_files(self, f):
        # Plugin template is always libfoo%(mext)s
        if not f.startswith('lib'):
            raise AssertionError('Plugin files must start with "lib": {!r}'.format(f))
        # Plugin DLLs are required to be libfoo.dll (mingw) or foo.dll (msvc)
        if (Path(self.config.prefix) / f).is_file():
            # libfoo.dll
            return [f]
        if self.using_msvc():
            fdir, fname = os.path.split(f)
            fmsvc = '{}/{}'.format(fdir, fname[3:])
            if (Path(self.config.prefix) / fmsvc).is_file():
                # foo.dll, foo.pdb
                return [fmsvc, fmsvc[:-3] + 'pdb']
        raise FatalError('GStreamer plugin {!r} not found'.format(f))

    def _search_files(self, files):
        '''
        Search plugin files and arbitrary files in the prefix, doing the
        extension replacements, globbing, and listing directories
        '''
        # replace extensions
        files_expanded = [f % self.extensions for f in files]
        fs = []
        for f in files_expanded:
            if not f.endswith('.dll'):
                fs.append(f)
                continue
            fs += self._find_plugin_dll_files(f)
        # fill directories
        dirs = [x for x in fs if
                os.path.isdir(os.path.join(self.config.prefix, x))]
        for directory in dirs:
            fs.remove(directory)
            fs.extend(self._ls_dir(os.path.join(self.config.prefix,
                                                directory)))
        # fill paths with pattern expansion *
        paths = [x for x in fs if '*' in x]
        if len(paths) != 0:
            for path in paths:
                fs.remove(path)
            fs.extend(shell.ls_files(paths, self.config.prefix))
        return fs

    def _search_binaries(self, files):
        '''
        Search binaries in the prefix. This function doesn't do any real serach
        like the others, it only preprend the bin/ path and add the binary
        extension to the given list of files
        '''
        binaries = []
        for f in files:
            self.extensions['file'] = f
            binaries.append('bin/%(file)s%(bext)s' % self.extensions)
        return binaries

    def _search_libraries(self, files):
        '''
        Search libraries in the prefix. Unfortunately the filename might vary
        depending on the platform and we need to match the library name and
        it's extension. There is a corner case on windows where the DLL might
        have any name, so we search for the .lib or .dll.a import library
        and get the DLL name from that.

        NOTE: Unlike other searchfuncs which return lists, this returns a dict
              with a mapping from the libname to a list of actual on-disk
              files. We use the libname (the key) in gen_library_file so we
              don't have to guess (incorrectly) based on the dll filename.
        '''
        if self.library_type == LibraryType.STATIC:
            return {}
        libdir = self.extensions['sdir'] + self.config.lib_suffix
        libext = self.extensions['srext']
        libregex = self.extensions['sregex']
        if libregex:
            find_func = find_shlib_regex
        elif self.config.target_platform == Platform.WINDOWS:
            find_func = find_dll_implib
        else:
            raise AssertionError

        libsmatch = {}
        notfound = []
        for f in files:
            libsmatch[f] = find_func(self.config, f[3:], self.config.prefix,
                                     libdir, libext, libregex)
            if not libsmatch[f]:
                notfound.append(f)

        # It's ok if shared libraries aren't found for iOS, we only want the
        # static libraries. In fact, all recipes should only build static on
        # iOS, but most don't.
        if notfound and self.config.target_platform != Platform.IOS:
            msg = "Some libraries weren't found while searching!"
            for each in notfound:
                msg += '\n' + each
            raise FatalError(msg)
        return libsmatch

    def _pyfile_get_name(self, f):
        if os.path.exists(os.path.join(self.config.prefix, f)):
            return f
        else:
            pydir = os.path.basename(os.path.normpath(self.config.py_prefix))
            pyversioname = re.sub("python|\.", '', pydir)
            cpythonname = "cpython-" + pyversioname

            splitedext = os.path.splitext(f)
            for ex in ['', 'm']:
                f = splitedext[0] + '.' + cpythonname + ex + splitedext[1]
                if os.path.exists(os.path.join(self.config.prefix, f)):
                    return f
        return None

    def _pyfile_get_cached(self, f):
        pyfiles = []
        pycachedir = os.path.join(os.path.dirname(f), "__pycache__")
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

    def _search_pyfiles(self, files):
        '''
        Search for python files in the prefix. This function doesn't do any
        real search, it only preprend the lib/Python$PYVERSION/site-packages/
        path to the given list of files
        '''
        pyfiles = []
        files = [f % self.extensions for f in files]
        files = ['%s/%s' % (self.py_prefix, f) for f in files]
        files = self._search_files (files)
        for f in files:
            real_name = self._pyfile_get_name(f)
            if real_name:
                pyfiles.append(real_name)
            else:
                # Adding it so we notice there is a problem in the recipe
                pyfiles.append(f)
            if f.endswith('.py'):
                cached_files = self._pyfile_get_cached(f)
                pyfiles.extend(cached_files)
        return pyfiles

    def _search_langfiles(self, files):
        '''
        Search for translations in share/locale/*/LC_MESSAGES/ '
        '''
        pattern = 'share/locale/*/LC_MESSAGES/%s.mo'
        return shell.ls_files([pattern % x for x in files],
                              self.config.prefix)

    def _search_typelibfiles(self, files):
        '''
        Search for typelibs in lib/girepository-1.0/
        '''
        if not self.config.variants.gi:
            return []

        pattern = 'lib/girepository-1.0/%s.typelib'
        typelibs = shell.ls_files([pattern % x for x in files],
                                  self.config.prefix)
        if not typelibs:
            # Add the architecture for universal builds
            pattern = 'lib/%s/girepository-1.0/%%s.typelib' % \
                self.config.target_arch
            typelibs = shell.ls_files([pattern % x for x in files],
                                      self.config.prefix)
        return typelibs

    def _search_girfiles(self):
        '''
        Search for typelibs in lib/girepository-1.0/
        '''
        if not self.config.variants.gi:
            return []

        girs = []
        if hasattr(self, 'files_' + self.TYPELIB_CAT):
            girs += getattr(self, 'files_' + self.TYPELIB_CAT)
        if hasattr(self, 'platform_files_' + self.TYPELIB_CAT):
            d = getattr(self, 'platform_files_' + self.TYPELIB_CAT)
            girs += d.get(self.config.target_platform, [])

        # Use a * for the arch in universal builds
        pattern = 'share/gir-1.0/%s.gir'
        files = shell.ls_files([pattern % x for x in girs],
                              self.config.prefix)
        if not girs:
            # Add the architecture for universal builds
            pattern = 'share/gir-1.0/%s/%%s.gir' % \
                self.config.target_arch
            files = shell.ls_files([pattern % x for x in girs],
                                      self.config.prefix)
        return files

    def _search_devel_libraries(self):
        if self.runtime_dep:
            return []

        devel_libs = []
        for category in self.categories:
            if category != self.LIBS_CAT and \
               not category.startswith(self.LIBS_CAT + '_'):
                continue

            pattern = ''
            if self.library_type != LibraryType.NONE:
                pattern += 'lib/%(f)s.la '

            if self.library_type in (LibraryType.BOTH, LibraryType.STATIC):
                pattern += 'lib/%(f)s.a '

            if self.library_type in (LibraryType.BOTH, LibraryType.SHARED):
                if self.platform == Platform.LINUX:
                    pattern += 'lib/%(f)s.so '
                elif self.platform == Platform.WINDOWS:
                    pattern += 'lib/%(f)s.dll.a '
                    pattern += 'lib/%(f)s.def '
                    pattern += 'lib/%(fnolib)s.lib '
                elif self.platform in [Platform.DARWIN, Platform.IOS]:
                    pattern += 'lib/%(f)s.dylib '

            libsmatch = []
            for x in self._get_category_files_list(category):
                libsmatch.append(pattern % {'f': x, 'fnolib': x[3:]})
                # PDB names are derived from DLL library names (which are
                # arbitrary), so we must use the same search function for them.
                if self.platform != Platform.WINDOWS or not self.using_msvc():
                    continue
                if self.library_type in (LibraryType.STATIC, LibraryType.NONE):
                    continue
                devel_libs += find_pdb_implib(self.config, x[3:], self.config.prefix)
            devel_libs.extend(shell.ls_files(libsmatch, self.config.prefix))
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

    def __init__(self, config):
        # Override all search functions with an aggregating search function.
        for name in dir(FilesProvider):
            if not name.startswith('_search') or name == '_search_libraries':
                continue
            setattr(self, name, partial(self._aggregate_files_search_func, name))

    def get_arch_file(self, arch, f):
        '''
        Layout is split into separate arch-specific prefixes (android-universal)
        '''
        return '{}/{}'.format(arch, f)

    def _search_libraries(self, *args, **kwargs):
        # This is handled separately, assert that it's not called directly to avoid bugs
        raise AssertionError('Should not be called')

    def _aggregate_files_search_func(self, funcname, *args):
        files = set()
        for r in self._recipes.values():
            searchfunc = getattr(r, funcname)
            for f in searchfunc(*args):
                files.add(self.get_arch_file(r.config.target_arch, f))
        return list(files)

    def _aggregate_libraries(self, category):
        files = {}
        for r in self._recipes.values():
            for name, rfiles in r._list_files_by_category(category).items():
                if name not in files:
                    files[name] = set()
                for f in rfiles:
                    files[name].add(self.get_arch_file(r.config.target_arch, f))
        for name in files:
            files[name] = list(files[name])
        return files

    def _aggregate_files(self, category):
        files = set()
        for r in self._recipes.values():
            for f in r._list_files_by_category(category):
                files.add(self.get_arch_file(r.config.target_arch, f))
        return list(files)

    # This can't be on the UniversalRecipe class because it must override the
    # same method on the FilesProvider class.
    def _list_files_by_category(self, category):
        '''
        Reimplement the files provider base function to aggregate files from
        each target_arch recipe in UniversalRecipe.
        '''
        if category == self.LIBS_CAT:
            return self._aggregate_libraries(category)
        return self._aggregate_files(category)

class UniversalFlatFilesProvider(UniversalFilesProvider):

    def get_arch_file(self, arch, f):
        '''
        Layout is one common prefix will all arch-specific files merged into it
        with `lipo` (ios-universal)
        '''
        return f
