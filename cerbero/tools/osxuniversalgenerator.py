#!/usr/bin/env python
# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Thiago Santos <thiago.sousa.santos@collabora.com>
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
import subprocess
import shutil
import tempfile

from cerbero.utils import shell
from cerbero.tools.osxrelocator import OSXRelocator


file_types = [
    ('Mach-O', 'merge'),
    ('ar archive', 'merge'),
    ('libtool archive', 'skip'),
    ('libtool library', 'copy-la'),
    ('symbolic link', 'link'),
    ('data', 'copy'),
    ('text', 'copy'),
    ('document', 'copy'),
    ('catalog', 'copy'),
    ('python', 'copy'),
    ('image', 'copy'),
    ('icon', 'copy'),
    ('FORTRAN', 'copy'),
    ('LaTeX', 'copy'),
    ('Zip', 'copy'),
    ('empty', 'copy'),
    ('data', 'copy'),
]

class OSXUniversalGenerator(object):
    '''
    Wrapper for OS X's lipo command to help generating universal binaries
    from single arch binaries.

    It takes multiple input directories and parses through them. For every
    file it finds, it looks at file type and compare with the file types
    of the other input directories, in case the file is a single arch executable
    or dynamic library, it will be merged into a universal binary and copied to
    the output directory. All the other files (text/headers/scripts) are just
    copied directly.

    This tool assumes that the input roots have the same structures and files
    as they should be results from building the same project to different
    architectures

    '''

    LIPO_CMD = 'lipo'
    FILE_CMD = 'file'

    def __init__(self, output_root):
        '''
        @output_root: the output directory where the result will be generated

        '''
        self.output_root = output_root
        if self.output_root.endswith('/'):
            self.output_root = self.output_root[:-1]
        self.missing = []

    def merge_files(self, filelist, dirs):
        if len(filelist) == 0:
            return
        for f in filelist:
            self.do_merge(f, dirs)

    def merge_dirs(self, input_roots):
        if not os.path.exists(self.output_root):
            os.mkdir(self.output_root)
        self.parse_dirs(input_roots)

    def create_universal_file(self, output, inputlist, dirs):
        tmp_inputs = []
        # relocate all files with the prefix of the merged file.
        # which must be done before merging them.
        for f in inputlist:
            # keep the filename in the suffix to preserve the filename extension
            tmp = tempfile.NamedTemporaryFile(suffix=os.path.basename(f))
            tmp_inputs.append(tmp)
            shutil.copy(f, tmp.name)
            prefix_to_replace = [d for d in dirs if d in f][0]
            relocator = OSXRelocator (self.output_root, prefix_to_replace, self.output_root,
                                      False)
            # since we are using a temporary file, we must force the library id
            # name to real one and not based on the filename
            relocator.relocate_file(tmp.name,
                    id=f.replace(prefix_to_replace, self.output_root))
        cmd = '%s -create %s -output %s' % (self.LIPO_CMD,
            ' '.join([f.name for f in tmp_inputs]), output)
        self._call(cmd)

    def get_file_type(self, filepath):
        cmd = '%s -bh "%s"' % (self.FILE_CMD, filepath)
        return self._call(cmd)[0:-1] #remove trailing \n

    def _detect_merge_action(self, files_list):
        actions = []
        for f in files_list:
            if not os.path.exists(f):
                continue #TODO what can we do here? fontconfig has
                         #some random generated filenames it seems
            ftype = self.get_file_type(f)
            action = ''
            for ft in file_types:
                if ft[0] in ftype:
                    if ft[0] == 'text' and f.endswith('.pc'):
                        action = 'copy-pc'
                    else:
                        action = ft[1]
                    break
            if not action:
                raise Exception, 'Unexpected file type %s %s' % (str(ftype), f)
            actions.append(action)
        if len(actions) == 0:
            return 'skip' #we should skip this one, the file doesn't exist
        all_same = all(x == actions[0] for x in actions)
        if not all_same:
            raise Exception, 'Different file types found: %s : %s' \
                             % (str(ftype), str(files_list))
        return actions[0]

    def do_merge(self, filepath, dirs):
        full_filepaths = [os.path.join(d, filepath) for d in dirs]
        action = self._detect_merge_action(full_filepaths)

        #pick the first file as the base one in case of copying/linking
        current_file = full_filepaths[0]
        output_file = os.path.join(self.output_root, filepath)
        output_dir = os.path.dirname(output_file)

        if action == 'copy':
            self._copy(current_file, output_file)
        elif action == 'copy-la' or action == 'copy-pc':
            self._copy_and_replace_paths(current_file, output_file, dirs)
        elif action == 'link':
            self._link(current_file, output_file, filepath)
        elif action == 'merge':
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            self.create_universal_file(output_file, full_filepaths, dirs)
        elif action == 'skip':
            pass #just pass
        else:
            raise Exception, 'unexpected action %s' % action

    def parse_dirs(self, dirs, filters=None):
        self.missing = []

        dir_path = dirs[0]
        if dir_path.endswith('/'):
            dir_path = dir_path[:-1]
        for dirpath, dirnames, filenames in os.walk(dir_path):
            current_dir = ''
            token = ' '
            remaining_dirpath = dirpath
            while remaining_dirpath != dir_path or token == '':
                remaining_dirpath, token = os.path.split(remaining_dirpath)
                current_dir = os.path.join(token, current_dir)

            for f in filenames:
                if filters is not None and os.path.splitext(f)[1] not in filters:
                    continue
                current_file = os.path.join(current_dir, f)
                self.do_merge(current_file, dirs)

    def _copy(self, src, dest):
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        shutil.copy(src, dest)

    def _copy_and_replace_paths(self, src, dest, dirs):
        self._copy(src, dest)
        replacements = {}
        for d in dirs:
            replacements[d]=self.output_root
        shell.replace(dest, replacements)

    def _link(self, src, dest, filepath):
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        if os.path.lexists(dest):
            return #link exists, skip it

        # read the link, and extract the relative filepath
        target = os.readlink(src)

        # if it's a relative path use it directly
        if not os.path.isabs(target):
            os.symlink(target, dest)
            return

        # if it's an absolute path, make it relative for sanity
        rel_path = os.path.relpath(os.path.dirname(target), os.path.dirname(dest))
        dest_target = os.path.join(rel_path, os.path.basename(target))
        os.symlink(dest_target, dest)

    def _call(self, cmd, cwd=None):
        cmd = cmd or self.root
        process = subprocess.Popen(cmd, cwd=cwd,
            stdout=subprocess.PIPE, shell=True)
        output, unused_err = process.communicate()
        return output


class Main(object):

    def run(self):
        # We use OptionParser instead of ArgumentsParse because this script might
        # be run in OS X 10.6 or older, which do not provide the argparse module
        import optparse
        usage = "usage: %prog [options] outputdir inputdir1 inputdir2 ..."
        description='Merges multiple architecture build trees into a single '\
                    'universal binary build tree'
        parser = optparse.OptionParser(usage=usage, description=description)
        options, args = parser.parse_args()
        if len(args) < 3:
            parser.print_usage()
            exit(1)
        generator = OSXUniversalGenerator(args[0])
        generator.merge_dirs(args[1:])
        exit(0)

if __name__ == "__main__":
    main = Main()
    main.run()
