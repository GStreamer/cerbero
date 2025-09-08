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
from pathlib import Path
import pickle
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
    RUSTUP_VERSION = '1.28.1'
    RUST_VERSION = '1.89.0'
    RUSTUP_URL_TPL = '{server}/rustup/archive/{version}/{triple}/rustup-init{exe_suffix}'
    RUSTUP_NAME_TPL = 'rustup-init-{version}-{triple}{exe_suffix}'
    CHANNEL_URL_TPL = '{server}/dist/channel-rust-{version}.toml'
    COMPONENTS = ('cargo', 'rustc', 'rust-std', 'llvm-tools-preview')
    # Update from https://pypi.org/project/tomli/#files
    TOMLI_URL = 'https://files.pythonhosted.org/packages/c0/3f/d7af728f075fb08564c5949a9c95e44352e23dee646869fa104a3b2060a3/tomli-2.0.1.tar.gz'
    DOWNLOAD_CHECKSUMS = {
        # Rust packages metadata
        'channel-rust-1.89.0.toml': 'fbd1662e100e7b305908ece23b441cb7534eadfa6336c5f173ff08d1cec174a1',
        # Tomli Python module
        'tomli-2.0.1.tar.gz': 'de526c12914f0c550d15924c62d72abc48d6fe7364aa87328337a31007fe8a4f',
        # Rustup
        'rustup-init-1.28.1-x86_64-unknown-linux-gnu': 'a3339fb004c3d0bb9862ba0bce001861fe5cbde9c10d16591eb3f39ee6cd3e7f',
        'rustup-init-1.28.1-aarch64-unknown-linux-gnu': 'c64b33db2c6b9385817ec0e49a84bcfe018ed6e328fe755c3c809580cc70ce7a',
        'rustup-init-1.28.1-x86_64-apple-darwin': 'e4b1f9ec613861232247e0cb6361c9bb1a86525d628ecd4b9feadc9ef9e0c228',
        'rustup-init-1.28.1-aarch64-apple-darwin': '966892cda29f0152315f5b4add9b865944c97d5573ae33855b8fc2c0d592ca5a',
        'rustup-init-1.28.1-x86_64-pc-windows-gnu.exe': 'f47cee05c484fb4dc89267e25f9f2f64e18ac5c03a72bec04d01d3b903a27c9b',
        'rustup-init-1.28.1-x86_64-pc-windows-msvc.exe': '7b83039a1b9305b0c50f23b2e2f03319b8d7859b28106e49ba82c06d81289df6',
        'rustup-init-1.28.1-aarch64-pc-windows-msvc.exe': '9054ad509637940709107920176f14cee334bc5cfe50bc0a24a3dc59b6f4d458',
    }
    # The triple for the build platform/arch
    build_triple = None
    # The triples for the target platform/archs for the current cerbero config.
    # There will be more than one when doing universal builds.
    target_triples = None
    # Downloaded rustup path
    rustup = None
    # Downloaded rust channel
    channel = None

    def __init__(self, config, offline):
        super().__init__(config, offline, 'rust')

        self.manifest = {}
        self.manifest_path = Path(self.config.rustup_home) / 'cerbero.rustup'

        # Not yet processed
        self.installed = False
        self.offline = offline
        self.build_triple = self.config.rust_build_triple
        self.target_triples = set(self.config.rust_target_triples)
        if self.config.platform == Platform.WINDOWS:
            tgt = set()
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
            self.target_triples.update(tgt)
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
        # Get the existing targets
        self.load_manifest()

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

        # Then maybe also rust-std for the existing + new targets
        installed_targets = self.manifest.get('targets', set())
        required_targets = self.target_triples.union(installed_targets)
        for triple in required_targets:
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
        await self.install_rustup()
        return ([], None)

    def get_rustup_env(self):
        rustup_env = self.config.env.copy()
        rustup_env['CARGO_HOME'] = self.config.env['CARGO_HOME']
        rustup_env['RUSTUP_HOME'] = self.config.env['RUSTUP_HOME']
        # Set to local file:// URLs to support offline mode
        rustup_env['RUSTUP_UPDATE_ROOT'] = 'file://{}/rustup'.format(self.config.local_sources)
        rustup_env['RUSTUP_DIST_SERVER'] = 'file://{}'.format(self.config.local_sources)
        return rustup_env

    def load_manifest(self):
        """
        Read Rust toolchain install state
        """
        if self.manifest_path.exists() and not self.manifest:
            with self.manifest_path.open('rb') as f:
                try:
                    self.manifest = pickle.load(f)
                except Exception:
                    m.warning('Could not recover Rust toolchain status, assuming installation from scratch')

    def save_manifest(self):
        """
        Save updates and newly installed targets (if any)
        """
        with self.manifest_path.open('wb') as f:
            try:
                pickle.dump(self.manifest, f)
            except IOError as ex:
                m.warning('Could not save Rust toolchain status: %s' % ex)

    async def install_rustup(self):
        """
        Install Rustup and the specified targets
        (with the ability to skip components)
        """
        if self.installed:
            return

        self.load_manifest()
        await self.install_toolchain()
        await self.install_targets()
        self.save_manifest()
        self.installed = True

    async def install_toolchain(self):
        """
        Run rustup to install the downloaded toolchain. We pretend that
        RUST_VERSION is the latest stable release. That way when we upgrade the
        toolchain, rustup will automatically remove the older toolchain, which
        it wouldn't do if we installed a specific version.
        """
        rust_version = self.manifest.get('rust_version', None)
        if rust_version == self.RUST_VERSION:
            m.action(f'Skipping Rust host toolchain deploy ({rust_version} installed)')
            return

        # Update is required, ZAP
        if os.path.exists(self.config.rustup_home):
            shutil.rmtree(self.config.rustup_home)

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
        rustup_env = self.get_rustup_env()
        for suffix in ('', '.asc', '.sha256'):
            stable_channel = f'{os.path.dirname(self.channel)}/channel-rust-stable.toml'
            shutil.copyfile(self.channel + suffix, stable_channel + suffix)
        # Use async_call_output to discard stdout which contains messages that will confuse the user
        await shell.async_call_output(rustup_args, cpu_bound=False, env=rustup_env)
        m.message('Rust toolchain v{} installed at {}'.format(self.RUST_VERSION, self.config.rust_prefix))

        cargo_bin = Path(self.config.cargo_home) / 'bin'
        cargo = cargo_bin / f'cargo{self.config._get_exe_suffix()}'

        if self.config.platform == Platform.WINDOWS and cargo.is_symlink():
            # Workaround for https://github.com/rust-lang/rustup/issues/4291
            try:
                import subprocess

                subprocess.check_output([str(cargo), '--version'], env=rustup_env)
            except FileNotFoundError:
                m.warning('Found broken symbolic link support: https://github.com/rust-lang/rustup/issues/4291')
                symlinks = [f for f in cargo_bin.glob('*') if f.is_symlink()]
                for f in symlinks:
                    src = f.resolve()
                    f.unlink()
                    shutil.copy(src, f)

        self.manifest['rust_version'] = self.RUST_VERSION
        # Update the target triples so that install_targets will reinstall them
        installed_targets = self.manifest.get('targets', set())
        self.target_triples = self.target_triples.union(installed_targets)
        self.manifest['targets'] = set()

    async def install_targets(self):
        """
        Install Rust toolchain with rustup-init
        """
        installed_targets = self.manifest.get('targets', set())
        if self.target_triples.issubset(installed_targets):
            m.action(f'Skipping target components deploy, {installed_targets} installed')
            return
        cargo_bin = Path(self.config.cargo_home) / 'bin'
        rustup = cargo_bin / f'rustup{self.config._get_exe_suffix()}'
        rustup_args = [rustup, 'target', 'add', *self.target_triples]
        # Use async_call_output to discard stdout which contains messages that
        # will confuse the user
        await shell.async_call_output(rustup_args, cpu_bound=False, env=self.get_rustup_env())

        installed_targets.update(self.target_triples)
        self.manifest['targets'] = installed_targets

    async def start(self, jobs=0):
        await self.install_rustup()


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
