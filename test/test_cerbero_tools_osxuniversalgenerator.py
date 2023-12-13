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

import unittest
import tempfile
import shutil
import os

from cerbero.config import Architecture
from cerbero.utils import shell
from cerbero.tools.osxuniversalgenerator import OSXUniversalGenerator
from cerbero.tools.osxrelocator import OSXRelocator


TEST_APP = """\
#include<stdio.h>

extern int foo1(int r);

int main(int arg_count,char ** arg_values)
{
 printf("Hello World %%d\\n", foo1(1));
 return 0;
}"""


TEST_LIB = """\

int foo1(int r);

int foo1(int r) {
  return r;
}"""


SHARED_LIBRARY = {
    Architecture.X86: 'Mach-O dynamically linked shared library i386',
    Architecture.X86_64: 'Mach-O 64-bit dynamically linked shared library x86_64',
}
EXECUTABLE = {Architecture.X86: 'Mach-O executable i386', Architecture.X86_64: 'Mach-O 64-bit executable x86_64'}


class OSXUniversalGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._create_tree()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _create_tree(self):
        for p in [Architecture.X86, Architecture.X86_64, Architecture.UNIVERSAL]:
            for d in ['bin', 'lib', 'share']:
                os.makedirs(os.path.join(self.tmp, p, d))
        self.tmp_sources = os.path.join(self.tmp, 'tmp')
        os.makedirs(self.tmp_sources)

    def _compile(self, arch):
        main_c = os.path.join(self.tmp_sources, 'main.c')
        foo_c = os.path.join(self.tmp_sources, 'foo.c')

        libdir = os.path.join(self.tmp, arch, 'lib')
        libfoo = os.path.join(libdir, 'libfoo.so')
        test_app = os.path.join(self.tmp, arch, 'bin', 'test_app')
        with open(main_c, 'w') as f:
            f.write(TEST_APP)
        with open(foo_c, 'w') as f:
            f.write(TEST_LIB)
        if arch == Architecture.X86:
            arch = 'i386'
        shell.call('gcc -arch %s -o %s -shared %s' % (arch, libfoo, foo_c))
        shell.call('gcc -arch %s -o %s %s -L%s -lfoo' % (arch, test_app, main_c, libdir))

    def _get_file_type(self, path):
        cmd = 'file -bh %s'
        return shell.check_call(cmd % path)[:-1]

    def _check_compiled_files(self):
        for arch in [Architecture.X86, Architecture.X86_64]:
            res = self._get_file_type(os.path.join(self.tmp, arch, 'lib', 'libfoo.so'))
            self.assertEqual(res, SHARED_LIBRARY[arch])
            res = self._get_file_type(os.path.join(self.tmp, arch, 'bin', 'test_app'))
            self.assertEqual(res, EXECUTABLE[arch])

    def testMergeDirs(self):
        self._compile(Architecture.X86)
        self._compile(Architecture.X86_64)
        self._check_compiled_files()
        gen = OSXUniversalGenerator(os.path.join(self.tmp, Architecture.UNIVERSAL))
        gen.merge_dirs([os.path.join(self.tmp, Architecture.X86), os.path.join(self.tmp, Architecture.X86_64)])

        # bash-3.2$ file libfoo.so
        # libfoo.so: Mach-O universal binary with 2 architectures
        # libfoo.so (for architecture i386):	Mach-O dynamically linked shared library i386
        # libfoo.so (for architecture x86_64):	Mach-O 64-bit dynamically linked shared library x86_64

        ftype = self._get_file_type(os.path.join(self.tmp, Architecture.UNIVERSAL, 'lib', 'libfoo.so'))
        for arch in [Architecture.X86, Architecture.X86_64]:
            self.assertTrue(SHARED_LIBRARY[arch] in ftype)
        ftype = self._get_file_type(os.path.join(self.tmp, Architecture.UNIVERSAL, 'bin', 'test_app'))
        for arch in [Architecture.X86, Architecture.X86_64]:
            self.assertTrue(EXECUTABLE[arch] in ftype)

    def testMergeFiles(self):
        for arch in [Architecture.X86, Architecture.X86_64]:
            with open(os.path.join(self.tmp, arch, 'share', 'test'), 'w') as f:
                f.write('test')
        gen = OSXUniversalGenerator(os.path.join(self.tmp, Architecture.UNIVERSAL))
        gen.merge_files(
            ['share/test'], [os.path.join(self.tmp, Architecture.X86), os.path.join(self.tmp, Architecture.X86_64)]
        )
        self.assertTrue(os.path.exists(os.path.join(self.tmp, Architecture.UNIVERSAL, 'share', 'test')))

    def testMergeCopyAndLink(self):
        for arch in [Architecture.X86, Architecture.X86_64]:
            file1 = os.path.join(self.tmp, arch, 'share', 'test1')
            file2 = os.path.join(self.tmp, arch, 'share', 'test2')
            with open(file1, 'w') as f:
                f.write('test')
            os.symlink(file1, file2)

        gen = OSXUniversalGenerator(os.path.join(self.tmp, Architecture.UNIVERSAL))
        gen.merge_dirs([os.path.join(self.tmp, Architecture.X86), os.path.join(self.tmp, Architecture.X86_64)])

        file1 = os.path.join(self.tmp, Architecture.UNIVERSAL, 'share', 'test1')
        file2 = os.path.join(self.tmp, Architecture.UNIVERSAL, 'share', 'test2')

        self.assertTrue(os.path.exists(file1))
        self.assertTrue(os.path.exists(file2))
        self.assertEqual(os.readlink(file2), file1)

    def testMergePCFiles(self):
        for arch in [Architecture.X86, Architecture.X86_64]:
            pc_file = os.path.join(self.tmp, arch, 'test.pc')
            with open(pc_file, 'w') as f:
                f.write(os.path.join(self.tmp, arch, 'lib', 'test'))
        gen = OSXUniversalGenerator(os.path.join(self.tmp, Architecture.UNIVERSAL))
        gen.merge_files(
            ['test.pc'], [os.path.join(self.tmp, Architecture.X86), os.path.join(self.tmp, Architecture.X86_64)]
        )
        pc_file = os.path.join(self.tmp, Architecture.UNIVERSAL, 'test.pc')
        self.assertEqual(open(pc_file).readline(), os.path.join(self.tmp, Architecture.UNIVERSAL, 'lib', 'test'))

    def testMergedLibraryPaths(self):
        def check_prefix(path):
            if self.tmp not in path:
                return
            self.assertTrue(uni_prefix in path)
            self.assertTrue(x86_prefix not in path)
            self.assertTrue(x86_64_prefix not in path)

        self._compile(Architecture.X86)
        self._compile(Architecture.X86_64)
        self._check_compiled_files()
        uni_prefix = os.path.join(self.tmp, Architecture.UNIVERSAL)
        x86_prefix = os.path.join(self.tmp, Architecture.X86)
        x86_64_prefix = os.path.join(self.tmp, Architecture.X86_64)
        gen = OSXUniversalGenerator(uni_prefix)
        gen.merge_dirs([x86_prefix, x86_64_prefix])
        libfoo = os.path.join(self.tmp, Architecture.UNIVERSAL, 'lib', 'libfoo.so')
        libname = OSXRelocator.library_id_name(libfoo)
        check_prefix(libname)
        for p in OSXRelocator.list_shared_libraries(libfoo):
            check_prefix(p)
