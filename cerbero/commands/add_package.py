# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Collabora Ltd. <http://www.collabora.co.uk/>
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

from cerbero.enums import License, LicenseDescription
from cerbero.commands import Command, register_command
from cerbero.errors import FatalError, UsageError
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m
from cerbero.packages.packagesstore import PackagesStore


# TODO: Add option to create metapackages

RECEIPT_TPL =\
'''# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python


class Package(package.Package):

    name = '%(name)s'
    shortdesc = '%(shortdesc)s'
    version = '%(version)s'
'''

CODENAME_TPL = \
'''    codename = '%(codename)s'
'''

VENDOR_TPL = \
'''    vendor = '%(vendor)s'
'''

URL_TPL = \
'''    url = '%(url)s'
'''

LICENSE_TPL = \
'''    license = %(license)s
'''

DEPS_TPL = \
'''    deps = %(deps)s
'''

FILES_TPL = '''
    files = %(files)s
'''

FILES_DEVEL_TPL = \
'''    files_devel = %(files_devel)s
'''

PLATFORM_FILES_TPL = '''
    platform_files = {%(platform_files)s}
'''

PLATFORM_FILES_DEVEL_TPL = \
'''    platform_files_devel = {%(platform_files_devel)s}
'''


class AddPackage(Command):
    doc = N_('Adds a new package')
    name = 'add-package'

    def __init__(self):
        self.supported_licenses = {}
        l = License
        for name in l.__dict__:
            attr = getattr(l, name)
            if not isinstance(attr, LicenseDescription):
                continue
            self.supported_licenses[attr.acronym] = name

        self.supported_platforms = {
            'linux': 'Platform.LINUX',
            'windows': 'Platform.WINDOWS',
            'darwin': 'Platform.DARWIN'}

        Command.__init__(self,
            [ArgparseArgument('name', nargs=1,
                             help=_('name of the package')),
            ArgparseArgument('version', nargs=1,
                             help=_('version of the package')),
            ArgparseArgument('-s', '--short-desc', default='',
                             help=_('a short description of the package')),
            ArgparseArgument('-c', '--codename', default='',
                             help=_('a codename for the package')),
            ArgparseArgument('-v', '--vendor', default='',
                             help=_('the package vendor')),
            ArgparseArgument('-u', '--url', default='',
                             help=_('the package url')),
            ArgparseArgument('-l', '--license', default='',
                             help=_('license of the package. '
                                    'Supported licenses: %s') %
                                    ', '.join(self.supported_licenses.keys())),
            ArgparseArgument('-d', '--deps', default='',
                             help=_('comma separated list of the package '
                                    'dependencies')),
            ArgparseArgument('-i', '--includes', default='',
                             help=_('comma separated list of packages to '
                                    'include in this package. All files '
                                    'from the packages passed as param '
                                    'will be added to this package.')),
            ArgparseArgument('--files', default='',
                             help=_('comma separated list of recipe files to '
                                    'add to the runtime package '
                                    '(e.g.: recipe1:category1:category2,'
                                    'recipe2)')),
            ArgparseArgument('--files-devel', default='',
                             help=_('comma separated list of recipe files to '
                                    'add to the devel package '
                                    '(e.g.: recipe1:category1:category2,'
                                    'recipe2)')),
            ArgparseArgument('--platform-files', default='',
                             help=_('comma separated list of platform:recipe '
                                    'files to add to the runtime package '
                                    '(e.g.: linux:recipe1:category1:category2,'
                                    'windows:recipe2) '
                                    'Supported platforms: %s') %
                                    ', '.join(
                                        self.supported_platforms.keys())),
            ArgparseArgument('--platform-files-devel', default='',
                             help=_('comma separated list of platform:recipe '
                                    'files to add to the devel package '
                                    '(e.g.: linux:recipe1:category1:category2,'
                                    'windows:recipe2) '
                                    'Supported platforms: %s') %
                                    ', '.join(
                                        self.supported_platforms.keys())),
            ArgparseArgument('-f', '--force', action='store_true',
                default=False, help=_('Replace package if existing'))])

    def run(self, config, args):
        name = args.name[0]
        version = args.version[0]
        store = PackagesStore(config)
        filename = os.path.join(config.packages_dir, '%s.package' % name)
        if not args.force and os.path.exists(filename):
            m.warning(_("Package '%s' (%s) already exists, "
                "use -f to replace" % (name, filename)))
            return

        template_args = {}

        template = RECEIPT_TPL
        template_args['name'] = name
        template_args['version'] = version

        if args.short_desc:
            template_args['shortdesc'] = args.short_desc
        else:
            template_args['shortdesc'] = name

        if args.codename:
            template += CODENAME_TPL
            template_args['codename'] = args.codename

        if args.vendor:
            template += VENDOR_TPL
            template_args['vendor'] = args.vendor

        if args.url:
            template += URL_TPL
            template_args['url'] = args.url

        if args.license:
            self.validate_licenses([args.license])
            template += LICENSE_TPL
            template_args['license'] = \
                'License.' + self.supported_licenses[args.license]

        deps = []
        if args.deps:
            template += DEPS_TPL
            deps = args.deps.split(',')
            for dname in deps:
                try:
                    package = store.get_package(dname)
                except Exception, ex:
                    raise UsageError(_("Error creating package: "
                            "dependant package %s does not exist") % dname)
            template_args['deps'] = deps

        include_files = []
        include_files_devel = []
        platform_include_files = {}
        platform_include_files_devel = {}
        if args.includes:
            includes = args.includes.split(',')
            if list(set(deps) & set(includes)):
                raise UsageError(_("Error creating package: "
                        "param --deps intersects with --includes"))
            for pname in includes:
                try:
                    package = store.get_package(pname)
                except Exception, ex:
                    raise UsageError(_("Error creating package: "
                            "included package %s does not exist") % pname)
                include_files.extend(package.files)
                include_files_devel.extend(package.files_devel)
                platform_include_files = self.merge_dict(
                        platform_include_files,
                        package.platform_files)
                platform_include_files_devel = self.merge_dict(
                        platform_include_files_devel,
                        package.platform_files_devel)

        include_files = list(set(include_files))
        include_files_devel = list(set(include_files_devel))

        if args.files or include_files:
            template += FILES_TPL
            files = []
            if args.files:
                files = args.files.split(',')
            if include_files:
                files.extend(include_files)
            template_args['files'] = files

        if args.files_devel or include_files_devel:
            template += FILES_DEVEL_TPL
            files_devel = []
            if args.files_devel:
                files_devel = args.files_devel.split(',')
            if include_files_devel:
                files_devel.extend(include_files_devel)
            template_args['files_devel'] = files_devel

        if args.platform_files or platform_include_files:
            template += PLATFORM_FILES_TPL
            platform_files = self.parse_platform_files(
                    args.platform_files, platform_include_files)
            template_args['platform_files'] = platform_files

        if args.platform_files_devel or platform_include_files_devel:
            template += PLATFORM_FILES_DEVEL_TPL
            platform_files_devel = self.parse_platform_files(
                    args.platform_files_devel,
                    platform_include_files_devel)
            template_args['platform_files_devel'] = platform_files_devel

        try:
            f = open(filename, 'w')
            f.write(template % template_args)
            f.close()

            m.action(_("Package '%s' successfully created in %s") %
                    (name, filename))
        except IOError, ex:
            raise FatalError(_("Error creating package: %s") % ex)

    def merge_dict(self, d1, d2):
        ret = d1
        for k, v in d2.iteritems():
            if k in ret:
                ret[k].extend(v)
            else:
                ret[k] = v
        return ret

    def validate_licenses(self, licenses):
        for l in licenses:
            if l and not l in self.supported_licenses:
                raise UsageError(_("Error creating package: "
                    "invalid license '%s'") % l)

    def validate_platform_files(self, platform_files):
        for f in platform_files:
            platform = f[:f.index(':')]
            if not platform in self.supported_platforms:
                raise UsageError(_("Error creating package: "
                    "invalid platform '%s'") % platform)

    def parse_platform_files(self, platform_files, extra_files):
        if not platform_files and not extra_files:
            return ''

        if platform_files:
            unparsed_files = platform_files.split(',')
            self.validate_platform_files(unparsed_files)

            parsed_files = {}
            for desc in unparsed_files:
                platform_index = desc.index(':')
                platform = desc[:platform_index]
                files = desc[platform_index + 1:]
                if not platform in parsed_files:
                    parsed_files[platform] = [files]
                else:
                    parsed_files[platform].append(files)

            if extra_files:
                parsed_files = self.merge_dict(parsed_files, extra_files)
        else:
            parsed_files = extra_files

        template_arg = []
        for platform, files in parsed_files.iteritems():
            template_arg.append(
                self.supported_platforms[platform] + ': [' + \
                    ', '.join(['\'' + recipe_files + '\'' \
                        for recipe_files in files]) + \
                    ']')
        return ', '.join(template_arg)


register_command(AddPackage)
