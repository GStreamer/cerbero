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

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.build.source import SourceType
from cerbero.utils import _, N_, ArgparseArgument, git
from cerbero.utils import messages as m


class Tag(Command):
    doc = N_('Tag a git recipe or all git recipes using their '
            'sdk-$version branch')
    name = 'tag'

    def __init__(self):
        args = [
            ArgparseArgument('recipe',
                help=_('name of the recipe to tag or "all" to '
                        'tag all recipes')),
            ArgparseArgument('tagname',
                help=_('name of the tag to use')),
            ArgparseArgument('tagdescription',
                help=_('description of the tag')),
            ArgparseArgument('-f', '--force', action='store_true',
                default=False, help=_('Replace tag if existing'))]
        Command.__init__(self, args)

    def run(self, config, args):
        cookbook = CookBook(config)
        if args.recipe == 'all':
            recipes = cookbook.get_recipes_list()
        else:
            recipes = [cookbook.get_recipe(args.recipe)]
        if len(recipes) == 0:
            m.message(_("No recipes found"))
        tagname = args.tagname
        tagdescription = args.tagdescription
        force = args.force
        for recipe in recipes:
            try:
                if recipe.stype != SourceType.GIT and \
                   recipe.stype != SourceType.GIT_TARBALL:
                    m.message(_("Recipe '%s' has a custom source repository, "
                            "skipping") % recipe.name)
                    continue

                recipe.fetch(checkout=False)

                tags = git.list_tags(recipe.repo_dir)
                exists = (tagname in tags)
                if exists:
                    if not force:
                        m.warning(_("Recipe '%s' tag '%s' already exists, "
                                "not updating" % (recipe.name, tagname)))
                        continue
                    git.delete_tag(recipe.repo_dir, tagname)

                commit = 'origin/sdk-%s' % recipe.version
                git.create_tag(recipe.repo_dir, tagname, tagdescription,
                        commit)
            except:
                m.warning(_("Error tagging recipe %s" % recipe.name))


register_command(Tag)
