from collections import namedtuple
import xml.etree.ElementTree as ET

from cerbero.utils import _
from cerbero.errors import FatalError


class Manifest(object):
    """
    Parse and store the content of a manifest file
    """

    remotes = {}
    projects = {}
    default_remote = 'origin'
    default_revision = 'refs/heads/master'

    def __init__(self, manifest_path):
        self.manifest_path = manifest_path

    def parse(self):
        try:
            tree = ET.parse(self.manifest_path)
        except Exception as ex:
            raise FatalError(_('Error loading manifest in file %s') % ex)

        root = tree.getroot()

        for child in root:
            if child.tag == 'remote':
                self.remotes[child.attrib['name']] = child.attrib['fetch']
            if child.tag == 'default':
                self.default_remote = child.attrib['remote'] or self.default_remote
                self.default_revision = child.attrib['revision'] or self.default_revision
            if child.tag == 'project':
                project = namedtuple('Project', ['name', 'remote', 'revision', 'fetch_uri'])

                project.name = child.attrib['name']
                if project.name.endswith('.git'):
                    project.name = project.name[:-4]
                project.remote = child.attrib.get('remote') or self.default_remote
                project.revision = child.attrib.get('revision') or self.default_revision
                project.fetch_uri = self.remotes[project.remote] + project.name + '.git'

                self.projects[project.name] = project

    def find_project(self, name):
        try:
            return self.projects[name]
        except KeyError:
            raise FatalError(_('Could not find project %s in manifes') % name)

    def get_fetch_uri(self, project, remote):
        fetch = self.remotes[remote]
        return fetch + project.name + '.git'
