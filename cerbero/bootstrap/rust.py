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
from urllib.parse import urlparse

if __name__ == '__main__':
    # Add cerbero dir to path when invoked as a script so
    # that the cerbero imports below resolve correctly.
    parent = os.path.dirname(__file__)
    parent = os.path.dirname(parent)
    parent = os.path.dirname(parent)
    sys.path.append(parent)

from cerbero.bootstrap import BootstrapperBase
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.enums import Platform, Architecture


class RustBootstrapper(BootstrapperBase):
    """
    A class for installing a self-contained Rust and Cargo installation inside
    Cerbero's home dir
    """

    SERVER = 'https://static.rust-lang.org'
    RUSTUP_VERSION = '1.27.1'
    RUST_VERSION = '1.82.0'
    RUSTUP_URL_TPL = '{server}/rustup/archive/{version}/{triple}/rustup-init{exe_suffix}'
    RUSTUP_NAME_TPL = 'rustup-init-{version}-{triple}{exe_suffix}'
    CHANNEL_URL_TPL = '{server}/dist/channel-rust-{version}.toml'
    COMPONENTS = ('cargo', 'rustc', 'rust-std', 'llvm-tools-preview')
    # Update from https://pypi.org/project/tomli/#files
    TOMLI_URL = 'https://files.pythonhosted.org/packages/c0/3f/d7af728f075fb08564c5949a9c95e44352e23dee646869fa104a3b2060a3/tomli-2.0.1.tar.gz'
    DOWNLOAD_CHECKSUMS = {
        # Rust packages metadata
        'channel-rust-1.82.0.toml': 'c8cb926f97903cefdb1eff8171ffd44bc2d531b7ff1bfd0c49f88fc018623e99',
        # Tomli Python module
        'tomli-2.0.1.tar.gz': 'de526c12914f0c550d15924c62d72abc48d6fe7364aa87328337a31007fe8a4f',
        # Rustup
        'rustup-init-1.27.1-x86_64-unknown-linux-gnu': '6aeece6993e902708983b209d04c0d1dbb14ebb405ddb87def578d41f920f56d',
        'rustup-init-1.27.1-aarch64-unknown-linux-gnu': '1cffbf51e63e634c746f741de50649bbbcbd9dbe1de363c9ecef64e278dba2b2',
        'rustup-init-1.27.1-x86_64-apple-darwin': 'f547d77c32d50d82b8228899b936bf2b3c72ce0a70fb3b364e7fba8891eba781',
        'rustup-init-1.27.1-aarch64-apple-darwin': '760b18611021deee1a859c345d17200e0087d47f68dfe58278c57abe3a0d3dd0',
        'rustup-init-1.27.1-x86_64-pc-windows-gnu.exe': 'b272587f5bf4b8be1396353d22829245955873425110398f110959c866296b2b',
        'rustup-init-1.27.1-x86_64-pc-windows-msvc.exe': '193d6c727e18734edbf7303180657e96e9d5a08432002b4e6c5bbe77c60cb3e8',
        'rustup-init-1.27.1-aarch64-pc-windows-msvc.exe': '5f4697ee3ea5d4592bffdbe9dc32d6a8865762821b14fdd1cf870e585083a2f0',
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
            tgt = set(self.target_triples)
            # On Windows, build tools must be built using MSVC. However,
            # the current variant determines the default target.
            # So we need to always bootstrap $arch-windows-msvc,
            # and override the build triple accordingly
            self.build_triple = self.config.rust_triple(self.config.arch, self.config.platform, True)
            tgt.add(self.build_triple)
            # rustup-init wants to always install both 64-bit and 32-bit
            # toolchains, so ensure that we fetch and install both
            archs = {Architecture.X86_64, Architecture.X86}
            other_arch = (archs - {self.config.arch}).pop()
            # in both MSVC and MinGW ABIs
            tgt.add(self.config.rust_triple(other_arch, self.config.platform, True))
            tgt.add(self.config.rust_triple(other_arch, self.config.platform, False))
            self.target_triples = list(tgt)
        self.fetch_urls = self.get_fetch_urls()
        self.fetch_urls_func = self.get_more_fetch_urls
        self.extract_steps = []
        # Need to extract our own toml library if the system doesn't provide
        # one already
        if not self.config.find_toml_module(system_only=True):
            self.extract_steps += [(self.TOMLI_URL, True, self.config.rust_prefix)]

    def get_fetch_urls(self):
        """Get Rustup and Rust channel URLs"""
        urls = []
        m = {
            'server': self.SERVER,
            'version': self.RUSTUP_VERSION,
            'triple': self.build_triple,
            'exe_suffix': self.config.exe_suffix,
        }
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

        # Then maybe also rust-std for the target machine
        for triple in self.target_triples:
            if triple != self.build_triple:
                entry = channel_data['pkg']['rust-std']['target'][triple]
                urls += list(get_entry_urls(entry))
            # And rust-mingw for any MinGW targets
            if 'windows-gnu' in triple:
                entry = channel_data['pkg']['rust-mingw']['target'][triple]
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
        """
        Run rustup to install the downloaded toolchain. We pretend that
        RUST_VERSION is the latest stable release. That way when we upgrade the
        toolchain, rustup will automatically remove the older toolchain, which
        it wouldn't do if we installed a specific version.
        """
        # Install Rust toolchain with rustup-init
        st = os.stat(self.rustup)
        os.chmod(self.rustup, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        rustup_args = [
            self.rustup,
            '-y',
            '-v',
            '--no-modify-path',
            '--default-host',
            self.build_triple,
            '--profile',
            'minimal',
            '--component',
            'llvm-tools-preview',
        ]
        for triple in self.target_triples:
            rustup_args += ['--target', triple]
        rustup_env = self.get_rustup_env()
        for suffix in ('', '.asc', '.sha256'):
            stable_channel = f'{os.path.dirname(self.channel)}/channel-rust-stable.toml'
            shutil.copyfile(self.channel + suffix, stable_channel + suffix)
        if os.path.exists(self.config.rustup_home):
            shutil.rmtree(self.config.rustup_home)
        # Use async_call_output to discard stdout which contains messages that will confuse the user
        await shell.async_call_output(rustup_args, cpu_bound=False, env=rustup_env)
        m.message('Rust toolchain v{} installed at {}'.format(self.RUST_VERSION, self.config.rust_prefix))

    async def start(self, jobs=0):
        await self.install_toolchain()


if __name__ == '__main__':
    import re
    import argparse
    import urllib.request
    from hashlib import sha256
    from cerbero.config import RUST_TRIPLE_MAPPING

    parser = argparse.ArgumentParser()
    parser.add_argument('rust_version', nargs='?', help='Rust version to update to')
    parser.add_argument('rustup_version', nargs='?', help='Rustup version to update to')
    args = parser.parse_args()

    def get_rustup_version():
        d = urllib.request.urlopen('https://sh.rustup.rs', timeout=20)
        s = d.read().decode('utf-8')
        m = re.search('rustup-init ([0-9.]+)', s)
        return m.groups(0)[0]

    def get_tomllib():
        import importlib

        if sys.version_info >= (3, 11, 0):
            return importlib.import_module('tomllib')
        for mod in ('tomli', 'toml', 'tomlkit'):
            try:
                return importlib.import_module(mod)
            except ModuleNotFoundError:
                continue
        raise RuntimeError('No toml python module available')

    def get_rust_version():
        d = urllib.request.urlopen('https://static.rust-lang.org/dist/channel-rust-stable.toml', timeout=20)
        tomllib = get_tomllib()
        data = tomllib.loads(d.read().decode('utf-8'))
        return data['pkg']['rust']['version'].split()[0]

    def get_checksum(url):
        print(url + ' ', end='', flush=True)
        d = urllib.request.urlopen(url, timeout=20)
        h = sha256()
        while True:
            chunk = d.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            print('.', end='', flush=True)
        print('')
        return h.hexdigest()

    cls = RustBootstrapper
    kwargs = {'server': cls.SERVER}
    checksums = {}

    rust_version = args.rust_version
    if not rust_version:
        rust_version = get_rust_version()
    if rust_version != cls.RUST_VERSION:
        kwargs['version'] = rust_version
        name = f'channel-rust-{rust_version}.toml'
        checksums[name] = get_checksum(cls.CHANNEL_URL_TPL.format(**kwargs))

    rustup_version = args.rustup_version
    if not rustup_version:
        rustup_version = get_rustup_version()
    if rustup_version != cls.RUSTUP_VERSION:
        kwargs['version'] = rustup_version
        kwargs['exe_suffix'] = ''
        for platform in (Platform.LINUX, Platform.DARWIN):
            for arch in (Architecture.X86_64, Architecture.ARM64):
                kwargs['triple'] = RUST_TRIPLE_MAPPING[(platform, arch)]
                name = cls.RUSTUP_NAME_TPL.format(**kwargs)
                checksums[name] = get_checksum(cls.RUSTUP_URL_TPL.format(**kwargs))

        platform = Platform.WINDOWS
        kwargs['exe_suffix'] = '.exe'
        for toolchain in ('gnu', 'msvc'):
            for arch in (Architecture.X86_64, Architecture.ARM64):
                if toolchain == 'gnu' and arch == Architecture.ARM64:
                    continue
                kwargs['triple'] = RUST_TRIPLE_MAPPING[(platform, arch, toolchain)]
                name = cls.RUSTUP_NAME_TPL.format(**kwargs)
                checksums[name] = get_checksum(cls.RUSTUP_URL_TPL.format(**kwargs))

    for key, value in checksums.items():
        print(' ' * 8, end='')
        print(f"'{key}': '{value}',")
    if rustup_version != cls.RUSTUP_VERSION:
        print(f"RUSTUP_VERSION = '{rustup_version}'")
    if rust_version != cls.RUST_VERSION:
        print(f"RUST_VERSION = '{rust_version}'")
