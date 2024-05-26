import unittest

from cerbero.build import recipe, build, source
from test.test_common import DummyConfig


class Recipe(recipe.Recipe):
    pass


class TestRecipeMetaClass(unittest.TestCase):
    def setUp(self):
        self.config = DummyConfig()
        self.config.local_sources = ''
        self.config.sources = ''
        self.t = Recipe(self.config, {})

    def testReceiptBases(self):
        r = Recipe(self.config, {})
        bases = r.__class__.mro()
        self.assertTrue(build.BuildType.AUTOTOOLS in bases)
        self.assertTrue(source.SourceType.GIT_TARBALL in bases)
