#!/usr/bin/env python3
#
#       findpackagefile.py 
#
# Copyright (c) 2014, Thibault Saunier tsaunier@gnome.org
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
# Boston, MA 02110-1301, USA.


import os
import re
import sys
import shutil
import tempfile

from cerbero.utils import _, N_, ArgparseArgument, shell
from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.build.filesprovider import FilesProvider

class FindProvidedFiles(Command):
    doc = N_('Helper tool to validate a recipe, '
             ' It finds all files a recipe instals '
             'and generates a list of files the recipe actually provides '
             'sorted by categories. '
             'It is just an helper and user should then verify generated '
             'content by hand and add missing files to the recipe. '
             'You should make sure that all the dependencies '
             'are already built as it will only install the recipe '
             'in a temporary prefix without even building it.')
    name = 'validate-recipe'

    def __init__(self):
        Command.__init__(self,[ArgparseArgument('recipe',  nargs=1,
                help=_('The recipe')),
            ArgparseArgument('-o', '--output',  default=None,
                help=_('File where to put generated list content'))])

    def _install(self, config, prefix, recipe):
        cookbook = CookBook(config)
        recipe = cookbook.get_recipe(recipe)
        if not recipe.supports_destdir:
            print "Can not generate provided files as INSTALL_DIR" \
                "environment variable is not supported by the recipe"
            return False

        os.environ["DESTDIR"] = prefix
        recipe.install()

        return True

    def run(self, config, args):
        lprefix = os.path.join(tempfile.gettempdir(), "tmpprefix")
        if not self._install(config, lprefix, args.recipe[0]):
            return False

        found = {"devel" : [],
                 "python" : [],
                 "bins" : [],
                 "FIXME" : [],
                 "lang" : [],
                 "libs" : [],
                 "typelibs" : []
                 }

        prefix = os.path.join(lprefix, config.prefix[1:], "")
        os.path.join(prefix, "") # make it end with /
        python_dir = os.path.join(prefix, config.py_prefix, "")

        bin_dir = os.path.join(prefix, "bin", "")
        lib_dir = os.path.join(prefix, FilesProvider.EXTENSIONS[config.platform]["sdir"], "")

        hdirs = []
        for root, dirs, files in os.walk(prefix):
            for filename in files:
                f = os.path.join(root, filename)
                if python_dir in f:
                    if "__pycache__" in f:
                        continue
                    found['python'].append(re.sub(r".pyc$|.pyo$", r".py", f.replace(python_dir, "")))
                elif re.findall("\.pc$|\.h$|\.a$|\.la$", f):
                    if f.endswith('.h'):
                        if root in hdirs:
                            continue
                        else:
                            hdirs.append(root)
                            found['devel'].append(f.replace(prefix, "").replace(os.path.basename(f), '*.h'))
                    else:
                        found['devel'].append(f.replace(prefix, ""))
                elif re.findall(".typelib$", f):
                    found['typelibs'].append(os.path.basename(f).replace(".typelib", ""))
                elif bin_dir in f:
                    ext = FilesProvider.EXTENSIONS[config.platform]["bext"]
                    if f.endswith(ext) or not ext:
                        found['bins'].append(f.replace(bin_dir, "").replace(ext, ""))
                    else:
                        ext = FilesProvider.EXTENSIONS[config.platform]["sext"]
                        found['libs'].append(f.replace(bin_dir, "").replace(ext, ""))
                elif lib_dir in f:
                    ext = FilesProvider.EXTENSIONS[config.platform]["sext"]
                    found['libs'].append(re.sub('%s.*$' % ext, '', os.path.basename(f)))
                elif f.endswith(".mo"):
                    found['lang'].append(filename.replace(".mo", ""))
                else:
                    found['FIXME'].append(f.replace(prefix, ""))


        if args.output:
            o = open(args.output, 'w+')
        else:
            print "\n==== Provided files: ===="
            o = sys.stderr
        blank = '    '
        for ftype in found:
            if found[ftype]:
                line = 2 * blank
                o.write("%sfiles_%s = [\n" % (blank, ftype))

                for f in set(found[ftype]):
                    if len(line + f) > 60:
                        o.write("%s\n" % line)
                        line = 2 * blank
                    line += " '%s'," %f

                if line != 2 * blank:
                    o.write("%s\n" % line)
                o.write(blank + "]\n\n")
        if args.output:
            o.close()
        else:
            print "==== Done listing files ====\n"

        shutil.rmtree(lprefix)


register_command(FindProvidedFiles)
