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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_bootstrapper
from cerbero.config import Distro, FatalError
from cerbero.utils import _, shell


class AndroidBootstrapper (BootstrapperBase):

    NDK_BASE_URL = 'http://dl.google.com/android/repository/'
    NDK_VERSION = 'r13b'
    NDK_ZIP = 'android-ndk-' + NDK_VERSION + '-%s-%s.zip'

    def start(self):
        dest = self.config.toolchain_prefix
        ndk_zip = self.NDK_ZIP % (self.config.platform, self.config.arch)
        zip_file = os.path.join(dest, ndk_zip)
        try:
            os.makedirs(dest)
        except:
            pass
        shell.download("%s/%s" % (self.NDK_BASE_URL, ndk_zip), zip_file)
        if not os.path.exists(os.path.join(dest, "ndk-build")):
            try:
                shell.call('unzip %s' % ndk_zip, dest)
                shell.call('mv android-ndk-%s/* .' % self.NDK_VERSION, dest)
            except Exception, ex:
                raise FatalError(_("Error installing Android NDK: %s") % (ex))


def register_all():
    register_bootstrapper(Distro.ANDROID, AndroidBootstrapper)
