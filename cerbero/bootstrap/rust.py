# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2022 Nirbheek Chauhan <nirbheek@centricular.com>
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
import sys
import stat
import shutil
import subprocess
from urllib.parse import urlparse

from cerbero.bootstrap import BootstrapperBase
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.enums import Platform, Architecture


class RustBootstrapper(BootstrapperBase):
    '''
    A class for installing a self-contained Rust and Cargo installation inside
    Cerbero's home dir
    '''

    SERVER = 'https://static.rust-lang.org'
    RUSTUP_VERSION = '1.26.0'
    RUST_VERSION = '1.74.0'
    RUSTUP_URL_TPL = '{server}/rustup/archive/{version}/{triple}/rustup-init{exe_suffix}'
    RUSTUP_NAME_TPL = 'rustup-init-{version}-{triple}{exe_suffix}'
    CHANNEL_URL_TPL = '{server}/dist/channel-rust-{version}.toml'
    COMPONENTS = ('cargo', 'rustc', 'rust-std', 'llvm-tools-preview')
    # Update from https://pypi.org/project/tomli/#files
    TOMLI_URL = 'https://files.pythonhosted.org/packages/c0/3f/d7af728f075fb08564c5949a9c95e44352e23dee646869fa104a3b2060a3/tomli-2.0.1.tar.gz'
    DOWNLOAD_CHECKSUMS = {
        # Rust packages metadata
        'channel-rust-1.74.0.toml': '536c9fb9e1688491e389feda9e6241e6f65ba4fec6e9b2021f866c8edb9f4685',
        # Tomli Python module
        'tomli-2.0.1.tar.gz': 'de526c12914f0c550d15924c62d72abc48d6fe7364aa87328337a31007fe8a4f',
        # Rustup
        'rustup-init-1.26.0-aarch64-unknown-linux-gnu': '673e336c81c65e6b16dcdede33f4cc9ed0f08bde1dbe7a935f113605292dc800',
        'rustup-init-1.26.0-x86_64-unknown-linux-gnu': '0b2f6c8f85a3d02fde2efc0ced4657869d73fccfce59defb4e8d29233116e6db',
        'rustup-init-1.26.0-aarch64-apple-darwin': 'ed299a8fe762dc28161a99a03cf62836977524ad557ad70e13882d2f375d3983',
        'rustup-init-1.26.0-x86_64-apple-darwin': 'f6d1a9fac1a0d0802d87c254f02369a79973bc8c55aa0016d34af4fcdbd67822',
        'rustup-init-1.26.0-i686-pc-windows-msvc.exe': '3fcfaf0018c12b96c49dc7e13e8638bd8de686ab27dd14238c3f11d0a936c003',
        'rustup-init-1.26.0-x86_64-pc-windows-msvc.exe': '365d072ac4ef47f8774f4d2094108035e2291a0073702db25fa7797a30861fc9',
        'rustup-init-1.26.0-i686-pc-windows-gnu.exe': 'f2cb7bb1e662a74bd9fa071cc0799dc4c814b3a56af979d6eba1169c3d98338b',
        'rustup-init-1.26.0-x86_64-pc-windows-gnu.exe': '32e9128a82ac130043012463ca5f9cb507c349a3f16e3c2b98a3f7a32e294e59',
    }
    # The triple for the build platform/arch
    build_triple = None
    # The triples for the target platform/archs for the current cerbero config.
    # There will be more than one when doing universal builds.
    target_triples = None
    # Downloaded rustup path
    rustup = None
    # Downloadad rust channel
    channel = None

    def __init__(self, config, offline):
        super().__init__(config, offline)
        self.offline = offline
        self.build_triple = self.config.rust_build_triple
        self.target_triples = self.config.rust_target_triples
        if self.config.platform == Platform.WINDOWS:
            # On Windows, build-tools always use MSVC so we need to always
            # bootstrap $arch-windows-msvc
            bs_triple = self.config.rust_triple(self.config.arch, self.config.platform, True)
            if bs_triple not in self.target_triples:
                self.target_triples.append(bs_triple)
            # rustup-init wants to always install both 64-bit and 32-bit
            # toolchains, so ensure that we fetch and install both
            archs = {Architecture.X86_64, Architecture.X86}
            other_arch = (archs - {self.config.arch}).pop()
            arch_triple = self.config.rust_triple(other_arch, self.config.platform,
                                                  self.config.variants.visualstudio)
            if arch_triple not in self.target_triples:
                self.target_triples.append(arch_triple)
        self.fetch_urls = self.get_fetch_urls()
        self.fetch_urls_func = self.get_more_fetch_urls
        self.extract_steps = []
        # Need to extract our own toml library if the system doesn't provide
        # one already
        if not self.config.find_toml_module(system_only=True):
            self.extract_steps += [(self.TOMLI_URL, True, self.config.rust_prefix)]

    def get_fetch_urls(self):
        '''Get Rustup and Rust channel URLs'''
        urls = []
        m = {'server': self.SERVER, 'version': self.RUSTUP_VERSION,
             'triple': self.build_triple, 'exe_suffix': self.config.exe_suffix}
        # Rustup
        url = self.RUSTUP_URL_TPL.format(**m)
        name = self.RUSTUP_NAME_TPL.format(**m)
        checksum = self.DOWNLOAD_CHECKSUMS[name]
        urls.append((url, name, checksum))
        self.rustup = os.path.join(self.config.local_sources, name)
        # Rust channel
        m['version'] = self.RUST_VERSION
        url = self.CHANNEL_URL_TPL.format(**m)
        # We download channel-rust-{version}.toml and rename it to
        # channel-rust-stable.toml to fool rustup into thinking that this is
        # the latest stable release. That way when we upgrade the toolchain,
        # rustup will automatically remove the older toolchain, which it
        # wouldn't do if we installed a specific version.
        path = urlparse(url).path
        f = os.path.basename(path)
        self.channel = os.path.join(self.config.local_sources, path[1:])
        checksum = self.DOWNLOAD_CHECKSUMS[f]
        urls.append((url, path[1:], checksum))
        for each in ('.sha256', '.asc'):
            urls.append((url + each, path[1:] + each, False))
        if not self.config.find_toml_module(system_only=True):
            # Need the tomli python module to be able to parse the channel TOML file
            checksum = self.DOWNLOAD_CHECKSUMS[os.path.basename(self.TOMLI_URL)]
            urls.append((self.TOMLI_URL, None, checksum))
        return urls

    async def get_more_fetch_urls(self):
        # Extract tomli (if specified) and cargo-c, remove them from extract steps
        # We need tomli now, and we need cargo-c in the function we call next
        await self.extract()
        self.extract_steps = []

        if not self.config.find_toml_module(system_only=True):
            # tomli-<version>.tar.gz
            basename = os.path.basename(self.TOMLI_URL)
            # tomli-<version>.tar
            basename = os.path.splitext(basename)[0]
            # tomli-<version>
            basename = os.path.splitext(basename)[0]
            extracted_path = os.path.join(self.config.rust_prefix, basename)
            if os.path.exists(self.config.tomllib_path):
                shutil.rmtree(self.config.tomllib_path)
            os.replace(extracted_path, self.config.tomllib_path)

        tomllib = self.config.find_toml_module()

        with open(self.channel, 'r', encoding='utf-8') as f:
            channel_data = tomllib.loads(f.read())

        def get_entry_urls(entry):
            url = entry['xz_url']
            name = urlparse(url).path[1:]
            sha = entry['xz_hash']
            yield (url, name, sha)
            yield (url + '.sha256', name + '.sha256', False)
            yield (url + '.asc', name + '.asc', False)

        urls = []

        # Need the toolchain for the build machine first
        entry = channel_data['pkg']['rust']['target'][self.build_triple]
        urls += list(get_entry_urls(entry))

        # Components for build machine
        for c in self.COMPONENTS:
            entry = channel_data['pkg'][c]['target'][self.build_triple]
            urls += list(get_entry_urls(entry))

        # And then maybe also rust-std for the target machine
        for triple in self.target_triples:
            if triple != self.build_triple:
                entry = channel_data['pkg']['rust-std']['target'][triple]
                urls += list(get_entry_urls(entry))

        return (urls, self.install_toolchain_for_cargoc_fetch)

    async def install_toolchain_for_cargoc_fetch(self):
        m.action('Installing Rust toolchain so cargo-c.recipe can fetch deps')
        await self.install_toolchain()
        return ([], None)

    def get_rustup_env(self):
        rustup_env = self.config.env.copy()
        rustup_env['CARGO_HOME'] = self.config.env['CARGO_HOME']
        rustup_env['RUSTUP_HOME'] = self.config.env['RUSTUP_HOME']
        # Set to local file:// URLs to support offline mode
        rustup_env['RUSTUP_UPDATE_ROOT'] = 'file://{}/rustup'.format(self.config.local_sources)
        rustup_env['RUSTUP_DIST_SERVER'] = 'file://{}'.format(self.config.local_sources)
        return rustup_env

    async def install_toolchain(self):
        '''
        Run rustup to install the downloaded toolchain. We pretend that
        RUST_VERSION is the latest stable release. That way when we upgrade the
        toolchain, rustup will automatically remove the older toolchain, which
        it wouldn't do if we installed a specific version.
        '''
        # Install Rust toolchain with rustup-init
        st = os.stat(self.rustup)
        os.chmod(self.rustup, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        rustup_args = [self.rustup, '-y', '-v', '--no-modify-path',
                '--default-host', self.build_triple, '--profile', 'minimal',
                '--component', 'llvm-tools-preview']
        for triple in self.target_triples:
            rustup_args += ['--target', triple]
        rustup_env = self.get_rustup_env()
        for suffix in ('', '.asc', '.sha256'):
            stable_channel = f'{os.path.dirname(self.channel)}/channel-rust-stable.toml'
            shutil.copyfile(self.channel + suffix, stable_channel + suffix)
        # Use async_call_output to discard stdout which contains messages that will confuse the user
        await shell.async_call_output(rustup_args, cpu_bound=False, env=rustup_env)
        m.message('Rust toolchain v{} installed at {}'.format(self.RUST_VERSION, self.config.rust_prefix))

    async def start(self, jobs=0):
        await self.install_toolchain()
