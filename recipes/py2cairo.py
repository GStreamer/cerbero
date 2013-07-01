# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python


class Recipe(recipe.Recipe):
    name = 'py2cairo'
    version = '1.10.0'
    licenses = [License.GPLv2]
    stype = SourceType.TARBALL
    url = 'http://cairographics.org/releases/py2cairo-1.10.0.tar.bz2'
    deps = ['cairo']

    files_python = ['site-packages/cairo/_cairo%(pext)s',
                    'site-packages/cairo/__init__.py',
                   ]
