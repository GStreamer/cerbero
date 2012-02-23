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

from cerbero.errors import FatalError
from cerbero.utils import shell, _


def get_handler (recipe, config):
    '''
    Returns a L{cerbero.build.Build} for a L{cerbero.recipe.Recipe}

    @param config: cerbero's configuration
    @type: L{cerbero.config.Config}
    @param recipe: the recipe to fetch
    @type: L{cerbero.recipe.Recipe}
    '''
    try:
        build = recipe.btype(recipe, config)
    except Exception:
        import traceback; traceback.print_exc()
        raise FatalError(_("Could not find a build handler for %s"),
                         recipe.btype)
    return build


class Build (object):
    '''
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    _properties_keys = []

    def __init__(self, recipe, config):
        self.recipe = recipe
        self.config = config
        for conf in self._properties_keys:
            if hasattr(recipe, conf):
                setattr(self, conf, getattr(recipe, conf))

    def do_configure (self):
        '''
        Configures the module
        '''
        raise NotImplemented ("'configure' must be implemented by subclasses")

    def do_make (self):
        '''
        Compiles the module
        '''
        raise NotImplemented ("'make' must be implemented by subclasses")

    def do_install (self):
        '''
        Installs the module
        '''
        raise NotImplemented ("'install' must be implemented by subclasses")


class Autotools (Build):
    '''
    Build handler for autotools project
    '''

    config_sh = './configure'
    configure_tpl = "%(config-sh)s --prefix %(prefix)s "\
                    "--libdir %(libdir)s %(options)s"
    configure_options = ''
    make = 'make'
    install = 'make install'
    clean = 'clean'

    _properties_keys = ['config_sh', 'configure_tpl', 'configure_options',
                        'make', 'make_install', 'clean']

    def __init__(self, recipe, config):
        Build.__init__(self, recipe, config)
        self.build_dir = os.path.join(config.sources,
                                      self.recipe.package_name)

    def do_configure (self):
        configure_tpl = self.configure_tpl
        if self.config.host is not None:
            configure_tpl += ' --host=%(host)s'
        if self.config.build is not None:
            configure_tpl += ' --build=%(build)s'
        if self.config.target is not None:
            configure_tpl += ' --target=%(target)s'
        shell.call (configure_tpl % {'config-sh': self.config_sh,
                                     'prefix': self.config.prefix,
                                     'libdir': self.config.libdir,
                                     'host': self.config.host,
                                     'target': self.config.target,
                                     'build': self.config.build,
                                     'options': self.configure_options},
                    self.build_dir)

    def do_make (self):
        shell.call (self.make, self.build_dir)

    def do_install (self):
        shell.call (self.install, self.build_dir)

    def do_clean (self):
        shell.call (self.clean, self.build_dir)


class BuildType (object):

    AUTOTOOLS = Autotools
