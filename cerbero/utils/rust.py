# cerbero - a multi-platform build system for Open Source software
# SPDX-FileCopyrightText: 2026 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later

import os
from pathlib import Path
import re
import shutil
import tempfile

from cerbero.config import Config
from cerbero.errors import FatalError
from cerbero.utils import messages as m
from cerbero.utils import shell


class Prelink:
    """
    With Xcode 26.0 onwards, linking one or more Rust
    libraries will cause the following error:

    ```
    ld: Too many personality routines for compact unwind to encode. Found routines:
      '_rust_eh_personality'
      '_rust_eh_personality'
      '___gxx_personality_v0'
      '___objc_personality_v0'
    Move one or more unique personality routine users to a separate dynamic library.
    ```

    Apple allows you to do prelinking, but this localizes
    the Rust personality function to the object being linked.
    This requires -no-compact-unwind from Xcode 26 onwards; alternatively,
    these errors can be avoided by passing `-ld_classic`, or
    `-fuse-ld=<path to your rustup folder>/toolchains/stable-aarch64-apple-darwin/lib/rustlib/aarch64-apple-darwin/bin/gcc-ld/ld64.lld`
    in Build Settings -> Linking - General -> Other Linker flags or to
    your build system's linker flags configuration.

    This class implements both steps.

    rdar://FB22126725

    https://bugzilla.mozilla.org/show_bug.cgi?id=1188030
    """

    def __init__(self, config: Config, env: dict, logfile=None):
        self.config = config
        self.env = env
        self.logfile = logfile

    def patch_pkgconfig(self, f):
        """
        Insert `-no_compact_unwind` into the specified pkg-config file.
        """
        if os.path.isabs(f):
            source = Path(f)
        else:
            source = Path(self.config.prefix) / f
        shell.replace(source, {'Libs.private: ': 'Libs.private: -no_compact_unwind '})

    def get_llvm_tool(self, tool: str) -> Path:
        """
        Gets one of the LLVM tools matching the current Rust toolchain.

        Context: on Apple platforms, compiler_builtins (and any other
        crate mistakenly built with LTO enabled) will contain LLVM
        bitcode, causing usages of eg. stock (pre Xcode 16) nm to emit
        spam like:

        /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/nm: error: /tmp/GStreamer(libgstrsworkspace_a-compiler_builtins-3ec2bc050946f0ab.compiler_builtins.f12b8f9133eedb91-cgu.012.rcgu.o): Unknown attribute kind (91) (Producer: 'LLVM20.1.7-rust-1.89.0-stable' Reader: 'LLVM APPLE_1_1600.0.26.3_0')

        /Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/nm: error: /tmp/GStreamer(libgstrsworkspace_a-compiler_builtins-3ec2bc050946f0ab.compiler_builtins.f12b8f9133eedb91-cgu.069.rcgu.o): Invalid attribute group entry (Producer: 'LLVM20.1.7-rust-1.89.0-stable' Reader: 'LLVM APPLE_1_1600.0.26.3_0')

        This can be avoided by parsing all libraries involving Rust code with
        the Rust-provided LLVM tools component.
        """
        root_dir = shell.check_output(['rustc', '--print', 'sysroot'], env=self.env).strip()

        tools = list(Path(root_dir).glob(f'**/{tool}'))

        if len(tools) == 0:
            raise FatalError(f'Rust {tool} tool not found at {root_dir}, try re-running bootstrap')
        return tools[0]

    def prelink(self, f, symbol_pattern):
        # Apple wants you to do Single-Object Prelink
        if os.path.isabs(f):
            source = Path(f)
        else:
            source = Path(self.config.prefix) / f

        # Only global symbols
        # Only symbol names
        # Use portable output format
        # Skip undefined symbols
        # Write pathname of the object file
        manifest = shell.check_output(
            [self.get_llvm_tool('llvm-nm'), '-gjPUA', '--quiet', source.absolute()],
            env=self.env,
        )

        # Now we need to match the symbols to the pattern

        # Here's the catch: Apple strip is silly enough to be unable to
        # -undefined suppress a .o because of the -two_level_namespace being
        # the default post-10.1. So we need to determine which objects have
        # matching symbols. The rest can be safely stripped.

        # The symbol listing format is as follows:
        #  ./libgstrswebrtc.a[gstrswebrtc-3a8116aacab254c2.2u9b7sba8k2fvc9v.rcgu.o]: _gst_plugin_rswebrtc_get_desc T 500 0
        # Field 1 has the object name between brackets.
        # Field 2 is the symbol name.
        symbol_pattern = re.compile(symbol_pattern)

        with tempfile.TemporaryDirectory(prefix='cerbero', dir=self.config.home_dir) as tmp:
            # List those symbols that will be kept
            symbols_to_keep = set()

            for line in manifest.splitlines():
                data = line.split(sep=' ')
                symbol = data[1]

                if symbol_pattern.match(symbol):
                    symbols_to_keep.add(symbol)

            module = (Path(tmp) / source.name).with_suffix('.symbols')

            with module.open('w', encoding='utf-8') as f:
                f.write('# Stripped by Cerbero\n')

                for symbol in symbols_to_keep:
                    f.write(f'{symbol}\n')

            m.log(f'Symbols to preserve in {source.absolute()}:', self.logfile)
            for symbol in symbols_to_keep:
                m.log(f'\t{symbol}', self.logfile)

            # Unpack archive
            m.log(f'Unpacking {source.absolute()} with ar', self.logfile)
            shell.new_call([shutil.which('ar'), 'xv', source.absolute()], cmd_dir=tmp, logfile=self.logfile)

            # Now everything is flat in the pwd
            m.log('Performing Single-Object Prelinking', self.logfile)
            prelinked_obj = (Path(tmp) / source.name).with_suffix('.prelinked.o')

            ld = shutil.which('ld')

            if ld is None:
                raise FatalError('ld not found')

            # DO NOT split this into an array unless
            # you wrap this into a 'sh -c' call.
            # It needs the glob to be parsed by the shell!
            shell.new_call(
                ' '.join(
                    [
                        ld,
                        '-r',
                        '-exported_symbols_list',
                        str(module.absolute()),
                        '-o',
                        str(prelinked_obj.absolute()),
                        '*.o',
                    ]
                ),
                cmd_dir=tmp,
                logfile=self.logfile,
            )

            # With the stripping done, all files now need to be rearchived
            dest = Path(tmp) / source.name
            m.log(f'Repacking library to {dest.absolute()}', self.logfile)

            libtool = shutil.which('libtool')

            if libtool is None:
                raise FatalError('libtool not found')

            shell.new_call(
                [
                    libtool,
                    '-static',
                    prelinked_obj.absolute(),
                    '-o',
                    dest.absolute(),
                ],
                cmd_dir=tmp,
                logfile=self.logfile,
            )

            # And now we paper over
            os.replace(dest.absolute(), source.absolute())
