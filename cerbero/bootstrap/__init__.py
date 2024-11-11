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
import shutil
from cerbero.build.source import BaseTarball, Source


class BootstrapTarball(BaseTarball, Source):
    def __init__(self, config, offline, name, url, checksum, download_dir, tarball_name=None):
        self.config = config
        self.offline = offline
        self.name = name
        self.url = url
        self.download_dir = download_dir
        self.tarball_name = tarball_name
        self.tarball_checksum = checksum
        BaseTarball.__init__(self)

    def verify(self, fname, fatal=True):
        if self.tarball_checksum is False:
            return True
        return super().verify(fname, fatal)


class BootstrapperBase(object):
    # List of URLs to be fetched
    fetch_urls = None
    # A function that returns more URLs to fetch and a function to call that
    # can return more URLs to fetch. This continues recursively till the func
    # returned is None.
    fetch_urls_func = None
    # List of extract steps to be performed
    extract_steps = None

    def __init__(self, config, offline, name):
        self.config = config
        self.offline = offline
        self.name = name
        self.fetch_urls = []
        self.extract_steps = []
        self.sources = {}

    async def start(self):
        raise NotImplementedError("'start' must be implemented by subclasses")

    async def fetch_urls_impl(self, urls):
        for url, tarball_name, checksum in urls:
            source = BootstrapTarball(
                self.config,
                self.offline,
                self.name,
                url,
                checksum,
                self.config.local_sources,
                tarball_name=tarball_name,
            )
            self.sources[url] = source
            await source.fetch()

    async def fetch(self):
        "Fetch bootstrap binaries"
        await self.fetch_urls_impl(self.fetch_urls)
        next_func = self.fetch_urls_func
        while next_func:
            (more_urls, next_func) = await next_func()
            await self.fetch_urls_impl(more_urls)

    async def fetch_recipes(self, jobs):
        "Fetch build-tools recipes; only called by fetch-bootstrap"
        pass

    async def extract(self):
        for url, unpack, unpack_dir in self.extract_steps:
            if unpack:
                await self.sources[url].extract_tarball(unpack_dir)
            else:
                # Just copy the file as-is
                fname = os.path.basename(url)
                fpath = os.path.join(self.config.local_sources, fname)
                shutil.copy(fpath, unpack_dir)
