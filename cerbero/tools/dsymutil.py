# SPDX-FileCopyrightText: 2024 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later
import functools
import glob
import os
from pathlib import Path

from cerbero.enums import Platform
from cerbero.utils import shell


def symbolicable_files(files_list, prefix, target_platform: Platform):
    @functools.lru_cache()
    def can_be_symbolicable(fp: str):
        p = Path(fp)
        return p.parts[0] in ['lib', 'lib64', 'bin', 'libexec'] and p.suffix not in [
            '.a',
            '.pc',
            '.la',
            '.debuginfo',
            '.pdb',
            '.dSYM',
        ]

    @functools.lru_cache()
    def is_macho_file(fp: Path) -> bool:
        if fp.suffix in ['.so', '.dylib']:
            return True

        filedesc = shell.check_output(['file', '-bh', fp.resolve().as_posix()])
        # gst-ptp-helper is setuid
        return filedesc.removeprefix('setuid ').startswith('Mach-O')

    @functools.lru_cache()
    def is_windows_executable(fp: Path) -> bool:
        return fp.suffix in ['.pyd', '.dll', '.exe']

    @functools.lru_cache()
    def is_elf_file(fp: Path) -> bool:
        filedesc = shell.check_output(['file', '-bh', fp.resolve().as_posix()])
        return filedesc.startswith('ELF ')

    files = []
    for f in files_list:
        # First resolve links
        if '*' in f:
            fs = glob.glob(os.path.join(prefix, f), recursive=True)
            files.extend(os.path.relpath(f, start=prefix) for f in fs)
        else:
            files.append(f)
    files = set(Path(prefix, fp).resolve() for fp in files if can_be_symbolicable(fp))

    if Platform.is_apple(target_platform):
        return list(filter(is_macho_file, files))
    elif target_platform == Platform.WINDOWS:
        return list(filter(is_windows_executable, files))
    else:
        return list(filter(is_elf_file, files))


def symbolicate_macho_files(files, logfile=None, env=None):
    for f in files:
        abspath = f.resolve()
        if '.dSYM' in str(abspath):
            raise RuntimeError('Cannot symbolicate symbols')
        shell.new_call(['dsymutil', abspath], cmd_dir=abspath.parent, logfile=logfile, env=env)


def symbolicate_gnu_files(files, logfile=None, env=None):
    objcopy_cmd = env.get('OBJCOPY', 'objcopy') if env else 'objcopy'
    compress_flags = []
    test_flags_output = shell.check_output([objcopy_cmd, '--help'], env=env)
    if '--compress-debug-sections' in test_flags_output:
        compress_flags = ['--compress-debug-sections']
    for f in files:
        if f.suffix == '.debuginfo':
            raise RuntimeError('Cannot symbolicate symbols')
        elif f.suffix == '.exe':  # emulate GNU
            dwp = f.with_suffix('.debuginfo')
        else:
            dwp = f.with_suffix(f.suffix + '.debuginfo')
        shell.new_call(
            [objcopy_cmd, *compress_flags, '--only-keep-debug', f.name, dwp.name],
            cmd_dir=f.parent.as_posix(),
            logfile=logfile,
            env=env,
        )
        # I don't like adding the gnu-debuginfo section *after*
        # generating the stripped binary, but if I do it the
        # other way around, Windows refuses to execute the binary.
        tmpfile = f.with_suffix('.tmp-cerbero-sym')
        shell.new_call(
            [objcopy_cmd, '--strip-debug', f.name, tmpfile.name], cmd_dir=f.parent.as_posix(), logfile=logfile, env=env
        )
        shell.new_call(
            [objcopy_cmd, f'--add-gnu-debuglink={dwp.name}', tmpfile.name],
            cmd_dir=f.parent.as_posix(),
            logfile=logfile,
            env=env,
        )
        os.replace(tmpfile, f)
