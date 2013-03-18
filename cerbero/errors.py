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


from gettext import gettext as _


class CerberoException(Exception):
    header = ''
    msg = ''

    def __init__(self, msg=''):
        self.msg = msg
        Exception.__init__(self, self.header + msg)


class ConfigurationError(CerberoException):
    header = 'Configuration Error: '


class UsageError(CerberoException):
    header = 'Usage Error: '


class FatalError(CerberoException):
    header = 'Fatal Error: '


class CommandError(CerberoException):
    header = 'Command Error: '


class BuildStepError(CerberoException):

    def __init__(self, recipe, step, trace=''):
        CerberoException.__init__(self, _("Recipe '%s' failed at the build "
            "step '%s'\n%s") % (recipe, step, trace))


class RecipeNotFoundError(CerberoException):

    def __init__(self, recipe):
        CerberoException.__init__(self, _("Recipe '%s' not found") % recipe)


class PackageNotFoundError(CerberoException):

    def __init__(self, package):
        CerberoException.__init__(self, _("Package '%s' not found") % package)


class EmptyPackageError(CerberoException):

    def __init__(self, package):
        CerberoException.__init__(self, _("Package '%s' is empty") % package)


class MissingPackageFilesError(CerberoException):

    def __init__(self, files):
        CerberoException.__init__(self, _("The following files required by "
            "this package are missing:\n %s") % '\n'.join(files))


class InvalidRecipeError(CerberoException):
    pass
