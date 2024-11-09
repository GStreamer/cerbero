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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_toolchain_bootstrapper
from cerbero.config import Distro

NDK_VERSION = 'r27'
NDK_BASE_URL = 'https://dl.google.com/android/repository/android-ndk-%s-%s.zip'
NDK_CHECKSUMS = {
    'android-ndk-r27-linux.zip': '2f17eb8bcbfdc40201c0b36e9a70826fcd2524ab7a2a235e2c71186c302da1dc',
    # doesn't ship as a zip file anymore
    'android-ndk-r27-darwin.dmg': 'fedc21f8ec973e5d41630536b5a5ac1d2888632cafb6e1f2aa79f0db3eaeda75',
    'android-ndk-r27-windows.zip': '342ceafd7581ae26a0bd650a5e0bbcd0aa2ee15eadfd7508b3dedeb1372d7596',
}


class AndroidBootstrapper(BootstrapperBase):
    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline, 'android')
        self.prefix = self.config.toolchain_prefix
        url = NDK_BASE_URL % (NDK_VERSION, self.config.platform)
        self.fetch_urls.append((url, None, NDK_CHECKSUMS[os.path.basename(url)]))
        self.extract_steps.append((url, True, self.prefix))

    async def start(self, jobs=0):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)
        ndkdir = os.path.join(self.prefix, 'android-ndk-' + NDK_VERSION)
        if not os.path.isdir(ndkdir):
            return
        # Android NDK extracts to android-ndk-$NDK_VERSION, so move its
        # contents to self.prefix
        for d in os.listdir(ndkdir):
            dest = os.path.join(self.prefix, d)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.move(os.path.join(ndkdir, d), self.prefix)
        os.rmdir(ndkdir)


def register_all():
    register_toolchain_bootstrapper(Distro.ANDROID, AndroidBootstrapper)
